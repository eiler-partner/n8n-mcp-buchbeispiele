"""Pruefbarer Lehrvertrag fuer Snapshot und Restore-Preflight."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


class BackupInvalid(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(archive: bytes, instance_key: bytes, *, source_image: str, snapshot_at: str) -> dict:
    if not archive or not instance_key:
        raise BackupInvalid("archive_or_key_missing")
    datetime.fromisoformat(snapshot_at.replace("Z", "+00:00"))
    return {"format": "pg_dump-custom", "archive_sha256": sha256(archive),
            "instance_key_sha256": sha256(instance_key), "source_image": source_image,
            "snapshot_at_utc": snapshot_at, "schema": 1}


def preflight(archive: bytes, instance_key: bytes, record: dict, *, target_image: str) -> None:
    if not archive:
        raise BackupInvalid("archive_missing")
    if not instance_key:
        raise BackupInvalid("instance_key_missing")
    if record.get("schema") != 1 or record.get("format") != "pg_dump-custom":
        raise BackupInvalid("manifest_unsupported")
    if not hmac.compare_digest(sha256(archive), str(record.get("archive_sha256", ""))):
        raise BackupInvalid("archive_digest_mismatch")
    if not hmac.compare_digest(sha256(instance_key), str(record.get("instance_key_sha256", ""))):
        raise BackupInvalid("instance_key_mismatch")
    if target_image != record.get("source_image"):
        raise BackupInvalid("target_image_not_tested")
    try:
        date = datetime.fromisoformat(str(record["snapshot_at_utc"]).replace("Z", "+00:00"))
        if date.tzinfo is None or date > datetime.now(timezone.utc):
            raise ValueError("bad snapshot time")
    except (KeyError, ValueError, TypeError) as exc:
        raise BackupInvalid("snapshot_time_invalid") from exc


def goals(snapshot_at: datetime, incident_at: datetime, restore_seconds: float,
          *, rpo_target_seconds: float, rto_target_seconds: float) -> dict:
    if snapshot_at.tzinfo is None or incident_at.tzinfo is None or incident_at < snapshot_at:
        raise ValueError("invalid timeline")
    rpo = (incident_at - snapshot_at).total_seconds()
    return {"observed_rpo_seconds": round(rpo, 3),
            "observed_rto_seconds": round(restore_seconds, 3),
            "rpo_target_seconds": rpo_target_seconds,
            "rto_target_seconds": rto_target_seconds,
            "rpo_met": rpo <= rpo_target_seconds,
            "rto_met": restore_seconds <= rto_target_seconds}
