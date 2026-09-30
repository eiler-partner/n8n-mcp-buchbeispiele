"""Transaktional versionierter, vor jeder Ausgabe gefilterter Chunk-Index."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from .core import ContractError, load_policy, source_hash, structural_chunks


def day(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ContractError("invalid_date")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ContractError("invalid_date") from exc


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS versions (
                version_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                document_id TEXT NOT NULL, valid_from TEXT NOT NULL,
                valid_until TEXT, source_sha256 TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY, version_id TEXT NOT NULL,
                section_order INTEGER NOT NULL, ordinal INTEGER NOT NULL,
                audience TEXT NOT NULL, record_json TEXT NOT NULL,
                FOREIGN KEY(version_id) REFERENCES versions(version_id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
                document_id TEXT PRIMARY KEY, effective_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS chunks_version ON chunks(version_id, section_order, ordinal)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def publish(self, version_id: str, *, fail_after_close: bool = False) -> dict:
        policy = load_policy(version_id)
        chunks = structural_chunks(policy)
        sha = source_hash(policy)
        start = day(policy["valid_from"])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT source_sha256 FROM versions WHERE version_id=?",
                                  (version_id,)).fetchone()
            if existing:
                if existing[0] != sha:
                    raise ContractError("source_changed")
                return {"status": "published", "version_id": version_id,
                        "duplicate": True, "chunk_count": len(chunks), "source_sha256": sha}
            if db.execute("SELECT 1 FROM withdrawals").fetchone():
                raise ContractError("document_withdrawn")
            latest = db.execute("SELECT version_id, valid_from FROM versions ORDER BY valid_from DESC LIMIT 1").fetchone()
            expected = policy["previous_version"]
            if (latest[0] if latest else None) != expected:
                raise ContractError("predecessor_required")
            if latest:
                if start <= latest[1]:
                    raise ContractError("non_monotonic_validity")
                db.execute("UPDATE versions SET valid_until=? WHERE version_id=?", (start, latest[0]))
            if fail_after_close:
                raise ContractError("injected_failure")
            db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, NULL, ?)",
                       (version_id, policy["source_id"], policy["document_id"], start, sha))
            db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)", [
                (row["chunk_id"], version_id, row["section_order"], row["ordinal"],
                 row["audience"], json.dumps(row, ensure_ascii=False)) for row in chunks])
        return {"status": "published", "version_id": version_id, "duplicate": False,
                "chunk_count": len(chunks), "source_sha256": sha}

    def withdraw(self, effective_at: str) -> dict:
        effective_at = day(effective_at)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute("SELECT document_id, valid_from FROM versions ORDER BY valid_from DESC LIMIT 1").fetchone()
            if not latest:
                raise ContractError("nothing_published")
            if effective_at <= latest[1]:
                raise ContractError("withdrawal_before_latest")
            existing = db.execute("SELECT effective_at FROM withdrawals WHERE document_id=?",
                                  (latest[0],)).fetchone()
            if existing:
                if existing[0] != effective_at:
                    raise ContractError("withdrawal_conflict")
                return {"status": "withdrawn", "effective_at": effective_at, "duplicate": True}
            db.execute("INSERT INTO withdrawals VALUES (?, ?)", (latest[0], effective_at))
        return {"status": "withdrawn", "effective_at": effective_at, "duplicate": False}

    def visible(self, as_of: str, role: str) -> dict:
        as_of = day(as_of)
        if role not in {"employee", "hr"}:
            raise ContractError("unknown_role")
        with self._connect() as db:
            withdrawal = db.execute("SELECT effective_at FROM withdrawals LIMIT 1").fetchone()
            if withdrawal and as_of >= withdrawal[0]:
                rows = []
            else:
                rows = db.execute("""SELECT c.record_json, v.valid_from, v.valid_until,
                                         v.source_sha256 FROM chunks c JOIN versions v
                                  ON c.version_id=v.version_id
                                  WHERE v.valid_from<=? AND (v.valid_until IS NULL OR ?<v.valid_until)
                                    AND (c.audience='all' OR (?='hr' AND c.audience='hr'))
                                  ORDER BY c.section_order, c.ordinal""",
                                  (as_of, as_of, role)).fetchall()
        chunks = [json.loads(raw) | {"valid_from": start, "valid_until": end,
                                    "source_sha256": sha}
                  for raw, start, end, sha in rows]
        return {"as_of": as_of, "role": role, "count": len(chunks), "chunks": chunks}

    def history(self) -> dict:
        with self._connect() as db:
            versions = db.execute("SELECT version_id, valid_from, valid_until, source_sha256 FROM versions ORDER BY valid_from").fetchall()
            withdrawal = db.execute("SELECT effective_at FROM withdrawals LIMIT 1").fetchone()
        return {"versions": [dict(zip(("version_id", "valid_from", "valid_until", "source_sha256"), row))
                             for row in versions],
                "withdrawn_from": withdrawal[0] if withdrawal else None}
