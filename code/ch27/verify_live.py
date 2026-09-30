"""Echter n8n-/Neustarttest mit synthetischen Daten, ohne Cloud-Modell."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


API = "http://127.0.0.1:8127"
WEBHOOK = "http://127.0.0.1:15727/webhook"


def request(url: str, data: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(data).encode() if data is not None else None
    method = "POST" if raw is not None else "GET"
    req = urllib.request.Request(url, data=raw, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def must(url: str, data: dict | None = None) -> dict:
    status, result = request(url, data)
    assert status == 200, (url, status, result)
    return result


def wait_healthy() -> None:
    for _ in range(40):
        try:
            must(f"{API}/health")
            must("http://127.0.0.1:15727/healthz")
            return
        except Exception:
            time.sleep(1)
    raise AssertionError("Dienste nach Neustart nicht gesund")


suffix = uuid.uuid4().hex[:10]
tenant = f"tenant-{suffix}"
session = f"session-{suffix}"
run = f"restart-{suffix}"
start = {"run_id": run, "tenant_id": tenant, "session_id": session,
         "text": "Synthetischen Vorgang prüfen", "proposed_note": "Nur Labordaten",
         "max_steps": 2}
resume = {"run_id": run, "tenant_id": tenant, "resume_key": f"key-{suffix}",
          "expected_revision": 1, "decision": "continue"}
checks = []

created = must(f"{WEBHOOK}/ch27-start", start)
assert created["state"] == "awaiting_resume" and created["effect_count"] == 0
checks.append("n8n_start_checkpoint")

subprocess.run(["docker", "compose", "restart", "agent", "n8n"], check=True)
wait_healthy()
persisted = must(f"{API}/runs/{run}?tenant_id={tenant}")
assert persisted["state"] == "awaiting_resume" and persisted["revision"] == 1
checks.append("restart_persisted")

finished = must(f"{WEBHOOK}/ch27-resume", resume)
assert finished["state"] == "completed" and finished["effect_count"] == 1
checks.append("n8n_resume_effect_once")

retry = must(f"{WEBHOOK}/ch27-resume", resume)
assert retry["replay"] and retry["effect_count"] == 1
checks.append("same_key_replay")

other = dict(resume, resume_key=f"other-{suffix}")
status, body = request(f"{API}/resume", other)
assert (status, body["error"]) == (409, "already_final")
checks.append("different_key_rejected")

run2 = f"lostack-{suffix}"
start2 = dict(start, run_id=run2)
resume2 = dict(resume, run_id=run2, resume_key=f"lost-key-{suffix}")
must(f"{WEBHOOK}/ch27-start", start2)
status, body = request(f"{API}/resume", dict(resume2, simulate_lost_ack=True))
assert (status, body["error"]) == (503, "ack_lost_after_commit")
recovered = must(f"{WEBHOOK}/ch27-resume", resume2)
assert recovered["replay"] and recovered["effect_count"] == 1
checks.append("lost_ack_retry_effect_once")

forgotten = must(f"{API}/forget", {"tenant_id": tenant, "session_id": session})
assert forgotten["deleted_runs"] == 2
status, body = request(f"{API}/start", start)
assert (status, body["error"]) == (410, "deleted_run_id")
checks.append("forget_with_tombstone")

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "synthetic_data_only": True, "checks": checks, "passed": len(checks)}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for check in checks:
    print(f"PASS {check}")
print(f"PASS {len(checks)} live checks; report: reports/live-observation.json")
