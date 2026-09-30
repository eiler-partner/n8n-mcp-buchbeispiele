"""Human-gated synthetic document review with explicit, replay-safe state."""
from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core import CATALOG_FILES, build_report, canonical, digest, load_documents, resource_uris

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CH45_DB_PATH", "/state/ch45.sqlite"))
AUDIENCE = "ch45-review"


class Refused(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def key() -> bytes:
    value = os.environ.get("CH45_SIGNING_KEY", "")
    if len(value) < 32:
        raise RuntimeError("CH45_SIGNING_KEY must be at least 32 characters")
    return value.encode("utf-8")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(subject: str, role: str, ttl_seconds: int = 300) -> str:
    if role not in {"requester", "reviewer"} or not subject or ttl_seconds > 3600:
        raise ValueError("invalid_token_claims")
    payload = {"sub": subject, "role": role, "aud": AUDIENCE,
               "exp": int(time.time()) + ttl_seconds}
    body = b64(canonical(payload))
    signature = b64(hmac.digest(key(), body.encode(), "sha256"))
    return body + "." + signature


def verify_token(token: str, role: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = b64(hmac.digest(key(), body.encode(), "sha256"))
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        claims = json.loads(unb64(body))
        if (claims.get("aud") != AUDIENCE or claims.get("role") != role
                or not isinstance(claims.get("sub"), str)
                or not claims["sub"] or int(claims.get("exp", 0)) <= time.time()):
            raise ValueError
        return claims
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        raise Refused("invalid_or_expired_token") from None


def mcp_request(method: str, params: dict) -> dict:
    envelope = {"jsonrpc": "2.0", "id": 1, "method": method,
                "params": {**params, "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientInfo": {"name": "ch45-gateway", "version": "0.1.0"}}}}
    proc = subprocess.run([sys.executable, str(ROOT / "mcp_stdio.py")],
                          input=json.dumps(envelope) + "\n", text=True,
                          capture_output=True, timeout=10, check=True)
    answer = json.loads(proc.stdout)
    if "error" in answer:
        raise Refused(answer["error"]["message"])
    return answer["result"]


def current_report(catalog_uri: str) -> dict:
    listed = {row["uri"] for row in mcp_request("resources/list", {})["resources"]}
    if catalog_uri not in CATALOG_FILES or set(resource_uris()) != listed:
        raise Refused("resource_inventory_mismatch")

    def read(uri: str) -> dict:
        result = mcp_request("resources/read", {"uri": uri})
        if len(result["contents"]) != 1 or result["contents"][0]["uri"] != uri:
            raise Refused("resource_response_mismatch")
        return json.loads(result["contents"][0]["text"])

    catalog = read(catalog_uri)
    sources = {"sources": [read(uri) for uri in sorted(listed)
                            if uri.startswith("regulation://")]}
    return build_report(catalog, sources, load_documents())


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY, requester TEXT NOT NULL, catalog_uri TEXT NOT NULL,
        report_json TEXT NOT NULL, status TEXT NOT NULL, decision_json TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS audit (
        case_id TEXT NOT NULL, seq INTEGER NOT NULL, event_json TEXT NOT NULL,
        prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
        PRIMARY KEY(case_id, seq), FOREIGN KEY(case_id) REFERENCES cases(id))""")
    db.commit()
    return db


def append_audit(db: sqlite3.Connection, case_id: str, kind: str, actor: str,
                 details: dict) -> str:
    previous = db.execute("SELECT seq, event_hash FROM audit WHERE case_id=? ORDER BY seq DESC LIMIT 1",
                          (case_id,)).fetchone()
    seq = 1 if previous is None else previous["seq"] + 1
    prev_hash = "0" * 64 if previous is None else previous["event_hash"]
    event = {"kind": kind, "actor": actor, "details": details, "at_utc": now()}
    event_json = canonical(event).decode()
    event_hash = hmac.digest(key(), (prev_hash + event_json).encode(), "sha256").hex()
    db.execute("INSERT INTO audit VALUES (?,?,?,?,?)",
               (case_id, seq, event_json, prev_hash, event_hash))
    return event_hash


def verify_audit(db: sqlite3.Connection, case_id: str) -> str:
    rows = db.execute("SELECT * FROM audit WHERE case_id=? ORDER BY seq", (case_id,)).fetchall()
    if not rows:
        raise Refused("audit_missing")
    previous = "0" * 64
    for index, row in enumerate(rows, 1):
        expected = hmac.digest(key(), (previous + row["event_json"]).encode(), "sha256").hex()
        if row["seq"] != index or row["prev_hash"] != previous or not hmac.compare_digest(row["event_hash"], expected):
            raise Refused("audit_integrity_failed")
        previous = row["event_hash"]
    return previous


def get_case(db: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if row is None:
        raise Refused("case_not_found")
    return row


def unchanged(row: sqlite3.Row) -> dict:
    report = json.loads(row["report_json"])
    current = current_report(row["catalog_uri"])
    supplied_digest = report.get("report_sha256")
    body = {field: value for field, value in report.items() if field != "report_sha256"}
    if (supplied_digest != digest(canonical(body))
            or canonical(current) != canonical(report)):
        raise Refused("catalog_or_document_changed")
    return report


def dispatch(payload: dict, db: sqlite3.Connection) -> dict:
    action = payload.get("action")
    if action == "start":
        actor = verify_token(payload.get("requester_token"), "requester")["sub"]
        catalog_uri = payload.get("catalog_uri", "catalog://supplier-review/v1")
        if catalog_uri not in CATALOG_FILES:
            raise Refused("catalog_not_allowlisted")
        report = current_report(catalog_uri)
        case_id = str(uuid.uuid4())
        with db:
            db.execute("INSERT INTO cases VALUES (?,?,?,?,?,NULL)",
                       (case_id, actor, catalog_uri, canonical(report).decode(), "draft"))
            append_audit(db, case_id, "draft_created", actor,
                         {"report_sha256": report["report_sha256"]})
        return {"ok": True, "case_id": case_id, "status": "draft", "report": report}
    if action not in {"inspect", "review", "export"}:
        raise Refused("action_not_allowlisted")
    case_id = payload.get("case_id")
    if not isinstance(case_id, str):
        raise Refused("case_id_required")
    row = get_case(db, case_id)
    head = verify_audit(db, case_id)
    if action == "inspect":
        requester = verify_token(payload.get("requester_token"), "requester")["sub"]
        if requester != row["requester"]:
            raise Refused("wrong_requester")
        return {"ok": True, "case_id": case_id, "status": row["status"],
                "report": json.loads(row["report_json"]), "audit_head": head}
    if action == "review":
        reviewer = verify_token(payload.get("reviewer_token"), "reviewer")["sub"]
        if reviewer == row["requester"]:
            raise Refused("self_approval_forbidden")
        if row["status"] != "draft":
            raise Refused("review_already_decided")
        report = unchanged(row)
        if (payload.get("report_sha256") != report["report_sha256"]
                or payload.get("catalog_sha256") != report["catalog_sha256"]
                or payload.get("document_set_sha256") != report["document_set_sha256"]):
            raise Refused("stale_review_basis")
        decision = payload.get("decision")
        if decision not in {"approve", "reject"}:
            raise Refused("decision_invalid")
        comment = payload.get("comment", "")
        if not isinstance(comment, str) or not (10 <= len(comment) <= 500):
            raise Refused("reason_required")
        accepted = payload.get("accepted_open_ids", [])
        if (not isinstance(accepted, list) or len(set(accepted)) != len(accepted)
                or (decision == "approve" and set(accepted) != set(report["open_control_ids"]))
                or (decision == "reject" and accepted)):
            raise Refused("open_findings_not_acknowledged")
        decision_record = {"decision": decision, "reviewer": reviewer,
                           "comment": comment, "accepted_open_ids": accepted,
                           "report_sha256": report["report_sha256"], "at_utc": now()}
        new_status = "approved" if decision == "approve" else "rejected"
        with db:
            changed = db.execute("UPDATE cases SET status=?, decision_json=? WHERE id=? AND status='draft'",
                                 (new_status, canonical(decision_record).decode(), case_id))
            if changed.rowcount != 1:
                raise Refused("review_already_decided")
            append_audit(db, case_id, "review_" + decision, reviewer,
                         {"decision_sha256": digest(canonical(decision_record))})
        return {"ok": True, "case_id": case_id, "status": new_status,
                "decision": decision_record}
    requester = verify_token(payload.get("requester_token"), "requester")["sub"]
    if requester != row["requester"]:
        raise Refused("wrong_requester")
    if row["status"] != "approved":
        raise Refused("export_requires_approval")
    report = unchanged(row)
    decision_record = json.loads(row["decision_json"])
    if decision_record["report_sha256"] != report["report_sha256"]:
        raise Refused("approval_report_mismatch")
    with db:
        changed = db.execute("UPDATE cases SET status='exported' WHERE id=? AND status='approved'", (case_id,))
        if changed.rowcount != 1:
            raise Refused("export_requires_approval")
        head = append_audit(db, case_id, "exported", requester,
                            {"report_sha256": report["report_sha256"]})
    artifact = {"kind": "human_reviewed_synthetic_assessment_not_legal_certificate",
                "case_id": case_id, "report": report, "approval": decision_record,
                "audit_head_hmac": head, "exported_at_utc": now()}
    artifact["artifact_sha256"] = digest(canonical(artifact))
    return {"ok": True, "case_id": case_id, "status": "exported", "artifact": artifact}


def safe_dispatch(payload: dict, db: sqlite3.Connection) -> dict:
    try:
        if not isinstance(payload, dict):
            raise Refused("request_object_required")
        return dispatch(payload, db)
    except (Refused, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "code": str(exc) if isinstance(exc, Refused) else "invalid_request"}
