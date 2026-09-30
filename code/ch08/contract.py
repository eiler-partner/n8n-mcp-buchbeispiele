"""Pure chapter-8 contracts: signed delivery, pagination and idempotency."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


RECORDS = [
    {"id": f"R-{number:03d}", "label": label}
    for number, label in enumerate(
        ("Aster", "Birke", "Cedar", "Dahlie", "Eiche", "Fichte", "Ginster"), 1
    )
]
EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}\Z")
MAX_BODY = 16_384
WINDOW_SECONDS = 300


def page(number: int, base_url: str) -> dict:
    if number < 1 or number > 3:
        raise ValueError("page must be 1..3")
    start = (number - 1) * 3
    return {
        "data": RECORDS[start : start + 3],
        "next": f"{base_url}/records?page={number + 1}" if number < 3 else None,
    }


def signature(secret: str, timestamp: str, delivery_id: str, raw: bytes) -> str:
    signed = timestamp.encode("ascii") + b"." + delivery_id.encode("ascii") + b"." + raw
    return "v1=" + hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def validate(raw: bytes, headers: dict, secret: str, now: int | None = None) -> tuple[dict, str]:
    if not raw or len(raw) > MAX_BODY:
        raise ValueError("invalid_body_size")
    timestamp = headers.get("x-lab-timestamp", "")
    delivery_id = headers.get("x-lab-delivery", "")
    supplied = headers.get("x-lab-signature", "")
    if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 12:
        raise PermissionError("invalid_timestamp")
    if not EVENT_ID.fullmatch(delivery_id):
        raise PermissionError("invalid_delivery_id")
    if abs((now if now is not None else int(time.time())) - int(timestamp)) > WINDOW_SECONDS:
        raise PermissionError("stale_delivery")
    if not re.fullmatch(r"v1=[0-9a-f]{64}", supplied):
        raise PermissionError("invalid_signature")
    expected = signature(secret, timestamp, delivery_id, raw)
    if not hmac.compare_digest(expected, supplied):
        raise PermissionError("invalid_signature")
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid_json") from error
    if not isinstance(event, dict) or set(event) != {"event_id", "customer", "amount_cents"}:
        raise ValueError("invalid_event")
    if not isinstance(event["event_id"], str) or not EVENT_ID.fullmatch(event["event_id"]):
        raise ValueError("invalid_event_id")
    if not isinstance(event["customer"], str) or not 1 <= len(event["customer"]) <= 80:
        raise ValueError("invalid_customer")
    if type(event["amount_cents"]) is not int or not 1 <= event["amount_cents"] <= 1_000_000:
        raise ValueError("invalid_amount")
    return event, delivery_id


def ingest(database: Path, event: dict, delivery_id: str, raw: bytes) -> tuple[int, dict]:
    """One SQLite transaction is the business write and the duplicate gate."""
    fingerprint = hashlib.sha256(raw).hexdigest()
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS orders ("
            "event_id TEXT PRIMARY KEY, delivery_id TEXT UNIQUE NOT NULL, "
            "fingerprint TEXT NOT NULL, customer TEXT NOT NULL, amount_cents INTEGER NOT NULL)"
        )
        existing = connection.execute(
            "SELECT event_id, fingerprint FROM orders WHERE event_id=? OR delivery_id=?",
            (event["event_id"], delivery_id),
        ).fetchone()
        if existing:
            if existing != (event["event_id"], fingerprint):
                return 409, {"accepted": False, "error": "idempotency_conflict"}
            return 200, {"accepted": True, "duplicate": True, "event_id": event["event_id"]}
        connection.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            (event["event_id"], delivery_id, fingerprint, event["customer"], event["amount_cents"]),
        )
    return 201, {"accepted": True, "duplicate": False, "event_id": event["event_id"]}


def order_count(database: Path) -> int:
    if not database.exists():
        return 0
    with sqlite3.connect(database) as connection:
        try:
            return connection.execute("SELECT count(*) FROM orders").fetchone()[0]
        except sqlite3.OperationalError:
            return 0


def retry_after_seconds(value: str, now: datetime | None = None, cap: int = 60) -> int:
    """Parse the two RFC 9110 forms, clamp to a local retry budget."""
    if value.isdecimal():
        seconds = int(value)
    else:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                raise ValueError("timezone required")
            seconds = max(0, int((date - (now or datetime.now(timezone.utc))).total_seconds()))
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("invalid Retry-After") from error
    return min(seconds, cap)
