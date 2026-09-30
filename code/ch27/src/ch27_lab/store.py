"""Expliziter Agentenzustand mit transaktionaler, lokaler Toolwirkung.

Das SQLite-`effects`-Ledger und der Run werden in EINER Transaktion geändert.
Das ist keine Exactly-once-Zusage für beliebige externe Systeme.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class LabError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(code)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise LabError("invalid_identifier", 422)
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 240:
        raise LabError("invalid_text", 422)
    return value.strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Eindeutig ist das Paar (run_id, effect_key): Ein Lauf darf mehrere
# verschiedene Aktionen haben, jede Aktion aber nur eine Wirkung.
EFFECTS_TABLE = """
    CREATE TABLE effects (
      run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
      tenant_id TEXT NOT NULL,
      effect_key TEXT NOT NULL,
      note_text TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (run_id, effect_key)
    )
"""


def _effects_key(db: sqlite3.Connection) -> list[str]:
    columns = [row for row in db.execute("PRAGMA table_info(effects)") if row["pk"] > 0]
    return [row["name"] for row in sorted(columns, key=lambda row: row["pk"])]


def _ensure_effects_table(db: sqlite3.Connection) -> None:
    """Legt `effects` an oder baut die alte Form einmalig um.

    Die alte Form hatte `run_id` allein als Primärschlüssel und damit höchstens
    eine Wirkung je Lauf. Ein Volume aus einem früheren Live-Lauf wird hier in
    einer Transaktion und ohne Datenverlust auf (run_id, effect_key) umgestellt.
    """
    if _effects_key(db) == ["run_id", "effect_key"]:
        return
    with db:
        db.execute("BEGIN IMMEDIATE")
        old_key = _effects_key(db)
        if old_key == ["run_id", "effect_key"]:
            return
        if old_key:
            db.execute("ALTER TABLE effects RENAME TO effects_old")
        db.execute(EFFECTS_TABLE)
        if old_key:
            db.execute("""INSERT INTO effects
                (run_id,tenant_id,effect_key,note_text,created_at)
                SELECT run_id,tenant_id,effect_key,note_text,created_at
                FROM effects_old""")
            db.execute("DROP TABLE effects_old")


def insert_effect_once(db: sqlite3.Connection, run_id: str, tenant_id: str,
                       effect_key: str, note: str, timestamp: str) -> bool:
    """Schreibt die Wirkung einer Aktion höchstens einmal.

    Liefert True für den ersten Eintrag und False, wenn dieselbe Aktion
    desselben Laufs schon gespeichert ist (Replay, keine zweite Wirkung).
    Läuft innerhalb der Transaktion des Aufrufers.
    """
    cursor = db.execute("""INSERT INTO effects
        (run_id,tenant_id,effect_key,note_text,created_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(run_id, effect_key) DO NOTHING""",
        (run_id, tenant_id, effect_key, note, timestamp))
    return cursor.rowcount == 1


class RunStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  request_text TEXT NOT NULL,
                  proposed_note TEXT NOT NULL,
                  state TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  step_count INTEGER NOT NULL,
                  max_steps INTEGER NOT NULL,
                  prompt_version TEXT NOT NULL,
                  resume_key TEXT,
                  decision TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY,
                  tenant_id TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tombstones (
                  run_id TEXT PRIMARY KEY,
                  deleted_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session
                  ON messages(tenant_id, session_id);
            """)
            _ensure_effects_table(db)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _view(db: sqlite3.Connection, row: sqlite3.Row, replay: bool = False) -> dict:
        effect_count = db.execute(
            "SELECT COUNT(*) FROM effects WHERE run_id = ?", (row["run_id"],)
        ).fetchone()[0]
        message_count = db.execute(
            "SELECT COUNT(*) FROM messages WHERE tenant_id = ? AND session_id = ?",
            (row["tenant_id"], row["session_id"]),
        ).fetchone()[0]
        return {
            "run_id": row["run_id"], "tenant_id": row["tenant_id"],
            "session_id": row["session_id"], "state": row["state"],
            "revision": row["revision"], "step_count": row["step_count"],
            "max_steps": row["max_steps"], "prompt_version": row["prompt_version"],
            "effect_count": effect_count, "message_count": message_count,
            "replay": replay,
        }

    def start(self, payload: dict) -> dict:
        run_id = _identifier(payload.get("run_id"))
        tenant = _identifier(payload.get("tenant_id"))
        session = _identifier(payload.get("session_id"))
        request = _text(payload.get("text"))
        note = _text(payload.get("proposed_note"))
        budget = payload.get("max_steps", 2)
        if type(budget) is not int or not 1 <= budget <= 10:
            raise LabError("invalid_budget", 422)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tombstones WHERE run_id = ?", (run_id,)).fetchone():
                raise LabError("deleted_run_id", 410)
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row:
                if row["tenant_id"] != tenant:
                    raise LabError("not_found", 404)
                if (row["tenant_id"], row["session_id"], row["request_text"],
                    row["proposed_note"], row["max_steps"]) != (
                    tenant, session, request, note, budget
                ):
                    raise LabError("run_id_conflict")
                return self._view(db, row, replay=True)
            state = "awaiting_resume" if budget >= 2 else "budget_exhausted"
            timestamp = _now()
            db.execute("""INSERT INTO runs VALUES
                (?, ?, ?, ?, ?, ?, 1, 1, ?, 'fixture-v1', NULL, NULL, ?, ?)""",
                (run_id, tenant, session, request, note, state, budget,
                 timestamp, timestamp))
            db.execute("""INSERT INTO messages
                (tenant_id,session_id,run_id,role,content,created_at)
                VALUES (?,?,?,?,?,?)""",
                (tenant, session, run_id, "user", request, timestamp))
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return self._view(db, row)

    def resume(self, payload: dict) -> dict:
        run_id = _identifier(payload.get("run_id"))
        tenant = _identifier(payload.get("tenant_id"))
        resume_key = _identifier(payload.get("resume_key"))
        revision = payload.get("expected_revision")
        decision = payload.get("decision")
        if type(revision) is not int or revision < 1:
            raise LabError("invalid_revision", 422)
        if decision not in ("continue", "stop"):
            raise LabError("invalid_decision", 422)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE run_id = ? AND tenant_id = ?",
                             (run_id, tenant)).fetchone()
            if not row:
                raise LabError("not_found", 404)
            if row["state"] in ("completed", "stopped"):
                if row["resume_key"] == resume_key and row["decision"] == decision:
                    return self._view(db, row, replay=True)
                raise LabError("already_final")
            if row["state"] != "awaiting_resume":
                raise LabError("not_resumable")
            if row["revision"] != revision:
                raise LabError("stale_revision")
            if row["step_count"] >= row["max_steps"]:
                raise LabError("budget_exhausted")
            timestamp = _now()
            if decision == "continue":
                # Ein stabiler Schlüssel und der Laufzustand werden atomar committed.
                insert_effect_once(db, run_id, tenant,
                                   f"{tenant}:{run_id}:record_note",
                                   row["proposed_note"], timestamp)
                state = "completed"
                db.execute("""INSERT INTO messages
                    (tenant_id,session_id,run_id,role,content,created_at)
                    VALUES (?,?,?,?,?,?)""",
                    (tenant, row["session_id"], run_id, "tool",
                     "synthetic_note_recorded", timestamp))
            else:
                state = "stopped"
            db.execute("""UPDATE runs SET state=?, revision=revision+1,
                step_count=step_count+1, resume_key=?, decision=?, updated_at=?
                WHERE run_id=?""",
                (state, resume_key, decision, timestamp, run_id))
            row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return self._view(db, row)

    def status(self, run_id: str, tenant_id: str) -> dict:
        run_id, tenant_id = _identifier(run_id), _identifier(tenant_id)
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=? AND tenant_id=?",
                             (run_id, tenant_id)).fetchone()
            if not row:
                raise LabError("not_found", 404)
            return self._view(db, row)

    def forget_session(self, payload: dict) -> dict:
        tenant = _identifier(payload.get("tenant_id"))
        session = _identifier(payload.get("session_id"))
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            ids = [r[0] for r in db.execute(
                "SELECT run_id FROM runs WHERE tenant_id=? AND session_id=?",
                (tenant, session))]
            timestamp = _now()
            db.executemany("INSERT OR IGNORE INTO tombstones VALUES (?,?)",
                           [(run_id, timestamp) for run_id in ids])
            db.execute("DELETE FROM runs WHERE tenant_id=? AND session_id=?",
                       (tenant, session))
            return {"deleted_runs": len(ids), "tombstones": len(ids)}
