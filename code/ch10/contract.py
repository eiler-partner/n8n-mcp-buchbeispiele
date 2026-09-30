"""Durable, synthetic document contract for the chapter-10 fault lab."""

import re
import sqlite3
from pathlib import Path


SCENARIOS = {"clean", "transient", "permanent", "always_transient", "timeout_after_commit", "unexpected"}
DOCUMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    publish_count INTEGER NOT NULL DEFAULT 0,
                    approval_url TEXT,
                    reason TEXT
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    UNIQUE (workflow_id, execution_id)
                );
                CREATE TABLE IF NOT EXISTS publish_attempts (
                    doc_id TEXT PRIMARY KEY,
                    count INTEGER NOT NULL
                );
                """
            )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _valid_document(data):
        if not isinstance(data, dict):
            return False
        doc_id = data.get("doc_id")
        content = data.get("content")
        scenario = data.get("scenario")
        return (
            isinstance(doc_id, str)
            and DOCUMENT_ID.fullmatch(doc_id) is not None
            and isinstance(content, str)
            and 1 <= len(content) <= 2_000
            and scenario in SCENARIOS
        )

    def analyze(self, data):
        if not self._valid_document(data):
            return 400, {"code": "invalid_document"}
        doc_id, content, scenario = (data[key] for key in ("doc_id", "content", "scenario"))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO documents (doc_id, content, scenario, state) VALUES (?, ?, ?, 'received')",
                    (doc_id, content, scenario),
                )
                attempts = 1
            else:
                if row["content"] != content or row["scenario"] != scenario:
                    return 409, {"code": "idempotency_conflict", "doc_id": doc_id}
                if row["state"] in {"quarantined", "denied", "published"}:
                    return 409, {"code": "terminal_state", "state": row["state"]}
                attempts = row["attempts"] + 1
            db.execute("UPDATE documents SET attempts = ? WHERE doc_id = ?", (attempts, doc_id))
            if scenario == "permanent":
                return 422, {"code": "schema_invalid", "doc_id": doc_id, "attempt": attempts}
            if scenario == "unexpected":
                return 500, {"code": "unexpected_failure", "doc_id": doc_id, "attempt": attempts}
            if scenario == "always_transient" or (scenario == "transient" and attempts == 1):
                return 503, {"code": "temporary_failure", "doc_id": doc_id, "attempt": attempts}
            db.execute("UPDATE documents SET state = 'prepared' WHERE doc_id = ?", (doc_id,))
            return 200, {"code": "prepared", "doc_id": doc_id, "attempt": attempts}

    def quarantine(self, doc_id, reason):
        if not isinstance(doc_id, str) or not DOCUMENT_ID.fullmatch(doc_id):
            return 400, {"code": "invalid_document_id"}
        if not isinstance(reason, str) or not reason or len(reason) > 120:
            return 400, {"code": "invalid_reason"}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None:
                return 404, {"code": "not_found"}
            if row["state"] == "published":
                return 409, {"code": "already_published"}
            db.execute(
                "UPDATE documents SET state = 'quarantined', reason = ? WHERE doc_id = ?",
                (reason, doc_id),
            )
            return 200, {"doc_id": doc_id, "state": "quarantined", "reason": reason}

    def approval_link(self, doc_id, url):
        if not isinstance(doc_id, str) or not DOCUMENT_ID.fullmatch(doc_id):
            return 400, {"code": "invalid_document_id"}
        if not isinstance(url, str) or not url.startswith("http://127.0.0.1:15684/"):
            return 400, {"code": "invalid_approval_url"}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None or row["state"] != "prepared":
                return 409, {"code": "not_prepared"}
            db.execute(
                "UPDATE documents SET state = 'awaiting_approval', approval_url = ? WHERE doc_id = ?",
                (url, doc_id),
            )
            return 200, {"doc_id": doc_id, "state": "awaiting_approval"}

    def approve(self, doc_id):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None or row["state"] not in {"awaiting_approval", "approved"}:
                return 409, {"code": "not_awaiting_approval"}
            db.execute("UPDATE documents SET state = 'approved', approval_url = NULL WHERE doc_id = ?", (doc_id,))
            return 200, {"doc_id": doc_id, "state": "approved"}

    def deny(self, doc_id):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None or row["state"] not in {"awaiting_approval", "denied"}:
                return 409, {"code": "not_awaiting_approval"}
            db.execute("UPDATE documents SET state = 'denied', approval_url = NULL WHERE doc_id = ?", (doc_id,))
            return 200, {"doc_id": doc_id, "state": "denied"}

    def publish(self, doc_id):
        if not isinstance(doc_id, str) or not DOCUMENT_ID.fullmatch(doc_id):
            return 400, {"code": "invalid_document_id"}, False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state, scenario FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row is None or row["state"] not in {"approved", "published"}:
                return 409, {"code": "not_approved"}, False
            db.execute(
                "INSERT INTO publish_attempts (doc_id, count) VALUES (?, 1) "
                "ON CONFLICT(doc_id) DO UPDATE SET count = count + 1",
                (doc_id,),
            )
            if row["state"] == "published":
                return 200, {"doc_id": doc_id, "state": "published", "duplicate": True}, False
            db.execute(
                "UPDATE documents SET state = 'published', publish_count = 1, approval_url = NULL WHERE doc_id = ?",
                (doc_id,),
            )
            simulate_lost_response = row["scenario"] == "timeout_after_commit"
            return 201, {"doc_id": doc_id, "state": "published", "duplicate": False}, simulate_lost_response

    def alert(self, workflow_id, execution_id, message):
        if not all(isinstance(v, str) and v and len(v) <= 200 for v in (workflow_id, execution_id, message)):
            return 400, {"code": "invalid_alert"}
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO alerts (workflow_id, execution_id, message) VALUES (?, ?, ?)",
                (workflow_id, execution_id, message),
            )
            return 200, {"state": "recorded"}

    def state(self, doc_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT d.doc_id, d.scenario, d.state, d.attempts, d.publish_count, "
                "COALESCE(p.count, 0) AS publish_attempts, d.approval_url, d.reason "
                "FROM documents d LEFT JOIN publish_attempts p ON p.doc_id = d.doc_id "
                "WHERE d.doc_id = ?",
                (doc_id,),
            ).fetchone()
            return dict(row) if row else None

    def alert_count(self):
        with self._connect() as db:
            return db.execute("SELECT count(*) FROM alerts").fetchone()[0]
