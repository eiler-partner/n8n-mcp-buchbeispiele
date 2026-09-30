"""n8n/PostgreSQL-Restore in eigene Testinstanz, ohne fremde Volumes anzufassen."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backup_contract import BackupInvalid, goals, manifest, preflight, sha256

ROOT = Path(__file__).resolve().parent
IMAGE = "n8nio/n8n:2.40.7"


def compose(env: dict, *args: str, input_bytes: bytes | None = None, check=True):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args],
                          cwd=ROOT, env=env, input=input_bytes, capture_output=True,
                          check=check, timeout=300)


def sql(env: dict, service: str, statement: str) -> str:
    result = compose(env, "--profile", "restore", "exec", "-T", service,
                     "psql", "-U", "n8n", "-d", "n8n", "-v", "ON_ERROR_STOP=1",
                     "-At", "-c", statement)
    return result.stdout.decode().strip()


def webhook(port: int, challenge: str) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/webhook/ch42-proof",
        data=json.dumps({"challenge": challenge}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="buch-ch42-secrets-") as directory:
        secret_dir = Path(directory)
        for name in ("db_password", "n8n_key"):
            path = secret_dir / name
            path.write_text(secrets.token_urlsafe(48), encoding="ascii")
            path.chmod(0o600)
        key = (secret_dir / "n8n_key").read_bytes()
        env = dict(os.environ, CH42_SECRETS_DIR=directory,
                   COMPOSE_PROJECT_NAME="buch-ch42-" + secrets.token_hex(4))
        try:
            config = compose(env, "config").stdout.decode()
            assert all((secret_dir / name).read_text() not in config
                       for name in ("db_password", "n8n_key"))
            compose(env, "up", "-d", "--wait", "source_n8n")
            challenge = secrets.token_hex(8)
            assert webhook(15746, challenge) == {"lab": "ch42", "version": "v1", "challenge": challenge}
            sql(env, "source_db", "CREATE TABLE IF NOT EXISTS lab_records (record_id text PRIMARY KEY, payload text NOT NULL)")
            sql(env, "source_db", "INSERT INTO lab_records VALUES ('before-backup','synthetic-a')")
            snapshot_at = datetime.now(timezone.utc)
            archive = compose(env, "exec", "-T", "source_db", "pg_dump", "-U", "n8n",
                              "-d", "n8n", "-Fc").stdout
            record = manifest(archive, key, source_image=IMAGE, snapshot_at=snapshot_at.isoformat())
            preflight(archive, key, record, target_image=IMAGE)
            sql(env, "source_db", "INSERT INTO lab_records VALUES ('after-backup','synthetic-b')")
            incident_at = datetime.now(timezone.utc)
            negatives = []
            for name, bad_archive, bad_key in (
                ("missing_key", archive, b""),
                ("wrong_key", archive, b"wrong-key"),
                ("corrupt_archive", archive[:-32], key),
            ):
                try:
                    preflight(bad_archive, bad_key, record, target_image=IMAGE)
                except BackupInvalid as exc:
                    negatives.append({"case": name, "rejected_as": str(exc)})
                else:
                    raise AssertionError(name + " passed preflight")
            assert len(negatives) == 3
            start = time.monotonic()
            compose(env, "--profile", "restore", "up", "-d", "--wait", "restore_db")
            compose(env, "--profile", "restore", "exec", "-T", "restore_db", "pg_restore", "-l",
                    input_bytes=archive)
            compose(env, "--profile", "restore", "exec", "-T", "restore_db",
                    "pg_restore", "-U", "n8n", "-d", "n8n", "--no-owner", "--no-acl",
                    "--single-transaction", "--exit-on-error", input_bytes=archive)
            assert sql(env, "restore_db", "SELECT string_agg(record_id,',' ORDER BY record_id) FROM lab_records") == "before-backup"
            compose(env, "--profile", "restore", "up", "-d", "--wait", "restore_n8n")
            restored = webhook(15747, challenge)
            restore_seconds = time.monotonic() - start
            assert restored == {"lab": "ch42", "version": "v1", "challenge": challenge}
            assert sql(env, "source_db", "SELECT count(*) FROM lab_records") == "2"
            metrics = goals(snapshot_at, incident_at, restore_seconds,
                            rpo_target_seconds=120, rto_target_seconds=180)
            assert metrics["rpo_met"] and metrics["rto_met"], metrics
            report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "source_image": IMAGE, "restore_image": IMAGE,
                      "postgres_image": "postgres:17.11-alpine", "data": "synthetic",
                      "backup_format": "pg_dump -Fc", "archive_sha256": sha256(archive),
                      "snapshot_at_utc": snapshot_at.isoformat(),
                      "simulated_incident_at_utc": incident_at.isoformat(),
                      "metrics": metrics, "source_records": 2, "restored_records": 1,
                      "restored_webhook": restored, "preflight_rejections": negatives,
                      "limits": ["key digest preflight, not credential decryption",
                                 "logical snapshot, not PITR or multi-store atomic backup",
                                 "lab measurements, not production SLO"]}
            destination = ROOT / "reports" / "live-observation.json"
            destination.parent.mkdir(exist_ok=True)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
            print("PASS ch42 live: isolated restore, workflow, snapshot boundary, RPO/RTO, 3 preflight denials")
        except Exception as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                print(exc.stdout.decode(errors="replace")[-4000:])
                print(exc.stderr.decode(errors="replace")[-8000:])
            print(compose(env, "--profile", "restore", "ps", check=False).stdout.decode(errors="replace"))
            print(compose(env, "--profile", "restore", "logs", "--tail", "80", check=False).stdout.decode(errors="replace")[-12000:])
            raise
        finally:
            compose(env, "--profile", "restore", "down", "-v", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
