"""Didaktisches Write-Gate: keine produktive Identitaets- oder Rechtspruefung."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from pathlib import Path


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sign(claims: dict, key: bytes) -> str:
    payload = base64.urlsafe_b64encode(canonical(claims)).decode().rstrip("=")
    mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + mac


def verify(token: str, key: bytes) -> dict | None:
    try:
        payload, mac = token.split(".")
        expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(value, dict) or int(value.get("exp", 0)) <= time.time():
            return None
        return value
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def proposal(body: dict) -> dict:
    return {key: body.get(key) for key in ("request_id", "tenant", "case_id", "finding_code", "note")}


class Gate:
    def __init__(self, database: str | Path, actor_key: bytes, approval_key: bytes):
        self.database = str(database)
        self.actor_key = actor_key
        self.approval_key = approval_key
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS findings (
                  request_id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
                  case_id TEXT NOT NULL, finding_code TEXT NOT NULL,
                  proposal_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approvals (jti TEXT PRIMARY KEY, request_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT,
                  actor TEXT, tenant TEXT, decision TEXT NOT NULL,
                  reason TEXT NOT NULL, proposal_hash TEXT NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def review(self, body: dict) -> dict:
        p = proposal(body)
        fingerprint = digest(p)
        actor = verify(str(body.get("actor_token", "")), self.actor_key)
        approval = verify(str(body.get("approval_token", "")), self.approval_key)
        reason = "approved"
        if not all(isinstance(v, str) and 1 <= len(v) <= 240 for v in p.values()):
            reason = "invalid_proposal"
        elif not actor or actor.get("aud") != "ch41-gate" or "finding:write" not in actor.get("scopes", []):
            reason = "actor_not_authorized"
        elif actor.get("tenant") != p["tenant"]:
            reason = "tenant_mismatch"
        elif not approval or approval.get("aud") != "ch41-gate" or approval.get("scope") != "finding:approve":
            reason = "approval_invalid"
        elif approval.get("tenant") != p["tenant"] or approval.get("proposal_hash") != fingerprint:
            reason = "approval_not_bound"
        elif approval.get("reviewer") == actor.get("sub") or not approval.get("reviewer") or not approval.get("jti"):
            reason = "four_eyes_failed"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT proposal_hash FROM findings WHERE request_id=?", (p["request_id"],)).fetchone() if isinstance(p["request_id"], str) else None
            if reason == "approved" and existing:
                reason = "idempotent" if existing["proposal_hash"] == fingerprint else "request_id_conflict"
            if reason == "approved":
                used = db.execute("SELECT request_id FROM approvals WHERE jti=?", (approval["jti"],)).fetchone()
                if used:
                    reason = "approval_replayed"
                else:
                    db.execute("INSERT INTO approvals VALUES (?,?)", (approval["jti"], p["request_id"]))
                    db.execute("INSERT INTO findings VALUES (?,?,?,?,?)", (p["request_id"], p["tenant"], p["case_id"], p["finding_code"], fingerprint))
            db.execute("INSERT INTO audit (request_id,actor,tenant,decision,reason,proposal_hash) VALUES (?,?,?,?,?,?)",
                       (p["request_id"] if isinstance(p["request_id"], str) else None,
                        actor.get("sub") if actor else None, p["tenant"] if isinstance(p["tenant"], str) else None,
                        "allow" if reason in ("approved", "idempotent") else "deny", reason, fingerprint))
        return {"decision": "allow" if reason in ("approved", "idempotent") else "deny",
                "reason": reason, "request_id": p["request_id"], "proposal_hash": fingerprint}

    def evidence(self) -> dict:
        with self.connect() as db:
            findings = [dict(row) for row in db.execute("SELECT * FROM findings ORDER BY request_id")]
            audit = [dict(row) for row in db.execute("SELECT * FROM audit ORDER BY id")]
        return {"findings": findings, "audit": audit}
