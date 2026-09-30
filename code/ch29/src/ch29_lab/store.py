"""Persistenter Freigabeautomat; keine Authentifizierungs- oder Modellinstanz."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASES = {row["case_id"]: row for row in json.loads((ROOT / "data/cases.json").read_text())}
REQUEST_ID = re.compile(r"^[a-zA-Z0-9_-]{4,64}$")
ACTOR_ID = re.compile(r"^[a-zA-Z0-9_-]{3,40}$")


class PolicyError(Exception):
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code = code
        self.status = status


def _fields(data: object, expected: set[str]) -> dict:
    if type(data) is not dict or set(data) != expected:
        raise PolicyError("input_contract")
    return data


def _digest(action: dict) -> str:
    canonical = json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Store:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    request_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    draft TEXT NOT NULL,
                    proposal_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner_actor TEXT,
                    second_actor TEXT,
                    deadline_at REAL NOT NULL,
                    review_timeout_seconds INTEGER NOT NULL,
                    tool_calls INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    request_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    draft TEXT NOT NULL,
                    proposal_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor_id TEXT,
                    at_utc TEXT NOT NULL,
                    proposal_hash TEXT NOT NULL
                );
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
            db.commit()
        except PolicyError:
            # Ein abgelaufener Zustand bleibt bestehen, auch wenn der spaete
            # Entscheidungs- oder Commit-Aufruf mit einem Vertragsfehler endet.
            db.commit()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _now(self) -> float:
        return float(self.clock())

    def _event(self, db, row, event: str, actor: str | None = None):
        stamp = datetime.fromtimestamp(self._now(), timezone.utc).isoformat()
        db.execute(
            "INSERT INTO audit(request_id,event,actor_id,at_utc,proposal_hash) VALUES(?,?,?,?,?)",
            (row["request_id"], event, actor, stamp, row["proposal_hash"]),
        )

    @staticmethod
    def _row(db, request_id: object, tenant_id: object):
        if type(request_id) is not str or not REQUEST_ID.fullmatch(request_id):
            raise PolicyError("request_id_invalid")
        row = db.execute("SELECT * FROM proposals WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise PolicyError("unknown_proposal", 404)
        if type(tenant_id) is not str or row["tenant_id"] != tenant_id:
            raise PolicyError("tenant_mismatch", 403)
        return row

    def _expire(self, db, row):
        if row["state"] not in {"awaiting_owner", "awaiting_reviewer", "ready", "escalated"}:
            return row
        if self._now() < row["deadline_at"]:
            return row
        new_state = "escalated" if row["state"] == "awaiting_reviewer" else "expired"
        new_deadline = self._now() + 60 if new_state == "escalated" else row["deadline_at"]
        db.execute("UPDATE proposals SET state=?,deadline_at=? WHERE request_id=?",
                   (new_state, new_deadline, row["request_id"]))
        self._event(db, row, "review_timeout_escalated" if new_state == "escalated" else "expired")
        return db.execute("SELECT * FROM proposals WHERE request_id=?", (row["request_id"],)).fetchone()

    def _snapshot(self, db, row):
        outbox_count = db.execute("SELECT COUNT(*) FROM outbox WHERE request_id=?",
                                  (row["request_id"],)).fetchone()[0]
        return {
            "request_id": row["request_id"], "case_id": row["case_id"],
            "tenant_id": row["tenant_id"], "state": row["state"],
            "proposal_hash": row["proposal_hash"], "target": row["target"],
            "evidence_id": row["evidence_id"], "draft": row["draft"],
            "owner_actor": row["owner_actor"], "second_actor": row["second_actor"],
            "deadline_at_utc": datetime.fromtimestamp(row["deadline_at"], timezone.utc).isoformat(),
            "tool_calls": row["tool_calls"], "outbox_count": outbox_count,
        }

    def propose(self, data: object) -> dict:
        data = _fields(data, {"request_id", "case_id", "tenant_id", "draft"})
        request_id = data["request_id"]
        if type(request_id) is not str or not REQUEST_ID.fullmatch(request_id):
            raise PolicyError("request_id_invalid")
        case_id = data["case_id"]
        if type(case_id) is not str or case_id not in CASES:
            raise PolicyError("unknown_case", 404)
        case = CASES[case_id]
        if type(data["tenant_id"]) is not str or data["tenant_id"] != case["tenant_id"]:
            raise PolicyError("tenant_mismatch", 403)
        if type(data["draft"]) is not str or data["draft"] != case["draft"]:
            raise PolicyError("draft_guardrail")
        action = {"request_id": request_id, "case_id": case_id,
                  "tenant_id": case["tenant_id"], "target": case["target"],
                  "evidence_id": case["evidence_id"], "draft": case["draft"]}
        digest = _digest(action)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM proposals WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old["proposal_hash"] != digest:
                    raise PolicyError("request_id_conflict", 409)
                return self._snapshot(db, old)
            db.execute("""INSERT INTO proposals
                (request_id,case_id,tenant_id,target,evidence_id,draft,proposal_hash,state,
                 deadline_at,review_timeout_seconds)
                VALUES(?,?,?,?,?,?,?,'awaiting_owner',?,?)""",
                (request_id, case_id, case["tenant_id"], case["target"], case["evidence_id"],
                 case["draft"], digest, self._now() + 120, case["review_timeout_seconds"]),
            )
            row = db.execute("SELECT * FROM proposals WHERE request_id=?", (request_id,)).fetchone()
            self._event(db, row, "proposed")
            return self._snapshot(db, row)

    def decide(self, data: object) -> dict:
        data = _fields(data, {"request_id", "tenant_id", "role", "actor_id", "decision", "proposal_hash"})
        if type(data["actor_id"]) is not str or not ACTOR_ID.fullmatch(data["actor_id"]):
            raise PolicyError("actor_invalid")
        if type(data["role"]) is not str or data["role"] not in {"owner", "reviewer", "escalation"}:
            raise PolicyError("role_invalid")
        if type(data["decision"]) is not str or data["decision"] not in {"Approve", "Deny"}:
            raise PolicyError("decision_invalid")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._expire(db, self._row(db, data["request_id"], data["tenant_id"]))
            if type(data["proposal_hash"]) is not str or data["proposal_hash"] != row["proposal_hash"]:
                raise PolicyError("proposal_changed", 409)
            expected = {"owner": "awaiting_owner", "reviewer": "awaiting_reviewer",
                        "escalation": "escalated"}[data["role"]]
            if row["state"] != expected:
                raise PolicyError("wrong_stage", 409)
            if data["role"] != "owner" and data["actor_id"] == row["owner_actor"]:
                raise PolicyError("same_actor_forbidden")
            if data["decision"] == "Deny":
                new_state, event, deadline = "rejected", f"{data['role']}_denied", row["deadline_at"]
            elif data["role"] == "owner":
                new_state, event = "awaiting_reviewer", "owner_approved"
                deadline = self._now() + row["review_timeout_seconds"]
            else:
                new_state, event, deadline = "ready", f"{data['role']}_approved", self._now() + 60
            column = "owner_actor" if data["role"] == "owner" else "second_actor"
            db.execute(f"UPDATE proposals SET state=?,deadline_at=?,{column}=? WHERE request_id=?",
                       (new_state, deadline, data["actor_id"], data["request_id"]))
            self._event(db, row, event, data["actor_id"])
            return self._snapshot(db, db.execute("SELECT * FROM proposals WHERE request_id=?",
                                                  (data["request_id"],)).fetchone())

    def tick(self, data: object) -> dict:
        data = _fields(data, {"request_id", "tenant_id"})
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._expire(db, self._row(db, data["request_id"], data["tenant_id"]))
            return self._snapshot(db, row)

    def commit(self, data: object) -> dict:
        data = _fields(data, {"request_id", "tenant_id", "proposal_hash"})
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._expire(db, self._row(db, data["request_id"], data["tenant_id"]))
            if type(data["proposal_hash"]) is not str or data["proposal_hash"] != row["proposal_hash"]:
                raise PolicyError("proposal_changed", 409)
            if row["state"] == "committed":
                return self._snapshot(db, row)
            if row["state"] != "ready" or not row["owner_actor"] or not row["second_actor"]:
                raise PolicyError("not_approved", 409)
            if row["owner_actor"] == row["second_actor"] or row["tool_calls"] != 0:
                raise PolicyError("write_budget_exhausted", 409)
            stamp = datetime.fromtimestamp(self._now(), timezone.utc).isoformat()
            db.execute("INSERT INTO outbox VALUES(?,?,?,?,?)",
                       (row["request_id"], row["tenant_id"], row["draft"], row["proposal_hash"], stamp))
            db.execute("UPDATE proposals SET state='committed',tool_calls=1 WHERE request_id=?",
                       (row["request_id"],))
            self._event(db, row, "outbox_written")
            return self._snapshot(db, db.execute("SELECT * FROM proposals WHERE request_id=?",
                                                  (row["request_id"],)).fetchone())

    def state(self, request_id: str) -> dict:
        with self._db() as db:
            row = db.execute("SELECT * FROM proposals WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise PolicyError("unknown_proposal", 404)
            result = self._snapshot(db, row)
            result["audit"] = [dict(event) for event in db.execute(
                "SELECT seq,event,actor_id,at_utc,proposal_hash FROM audit WHERE request_id=? ORDER BY seq",
                (request_id,),
            )]
            return result
