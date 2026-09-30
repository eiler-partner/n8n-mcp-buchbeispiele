"""Prüft beide publizierten n8n-Pfade, drei Manipulationen über n8n und den Bericht."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ch28_lab.core import CASES

WEBHOOK = "http://127.0.0.1:15728/webhook"
API = "http://127.0.0.1:8128"

# Negative Übergaben laufen über denselben Webhook wie die Positivfälle.
# tamper ist ein Testschalter des Lehr-Workflows: context verändert die Hülle
# vor dem Worker, answer das Worker-Ergebnis vor dem Reviewer.
NEGATIVE = (
    ("tenant_mismatch", "", {"case_id": "c01", "tenant_id": "other"}, "Router"),
    ("context_mismatch", "?tamper=context", {"case_id": "c01", "tenant_id": "lab"},
     "Specialist Worker"),
    ("worker_result_mismatch", "?tamper=answer", {"case_id": "c01", "tenant_id": "lab"},
     "Contract Reviewer"),
)


def request(url: str, data: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url, data=raw, method="POST" if raw is not None else "GET",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def wait_for_published_workflow(timeout: float = 90) -> None:
    """Wartet, bis n8n die importierte Fassung mit Fehlerausgang ausführt.

    Direkt nach dem Start meldet n8n 2.40.7 Webhooks teils noch als unbekannt
    (404). Lag schon eine ältere Fassung im Volume, führt es einige Sekunden lang
    diese aus; sie antwortet bei Ablehnung nur mit 500 "Error in workflow".
    """
    deadline = time.monotonic() + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            last = request(f"{WEBHOOK}/ch28-multi", {"case_id": "c01", "tenant_id": "other"})
            if last[0] == 422 and "rejected_by" in last[1]:
                return
        except (OSError, ValueError) as exc:
            last = exc
        time.sleep(1)
    raise AssertionError(f"n8n führt die Workflow-Fassung mit Fehlerausgang nicht aus: {last}")


wait_for_published_workflow()
rows = []
for case in CASES.values():
    body = {"case_id": case["id"], "tenant_id": case["tenant_id"]}
    simple_status, simple = request(f"{WEBHOOK}/ch28-baseline", body)
    multi_status, multi = request(f"{WEBHOOK}/ch28-multi", body)
    assert simple_status == multi_status == 200, (case["id"], simple, multi)
    for result in (simple, multi):
        assert result["status"] == "accepted", result
        assert result["route"] == case["expected_route"], result
        assert result["answer"] == case["expected_answer"], result
        assert result["source_id"] == case["source_id"], result
    assert (simple["stage_calls"], multi["stage_calls"]) == (1, 3)
    rows.append({"case_id": case["id"], "baseline_pass": True, "multi_pass": True,
                 "handoff_context_bytes": multi["context_bytes"]})
    print(f"PASS {case['id']}: baseline and multi")

negative = []
for code, query, body, stage in NEGATIVE:
    status, value = request(f"{WEBHOOK}/ch28-multi{query}", body)
    assert status == 422, (code, status, value)
    assert value.get("rejected_by") == stage, (code, value)
    # Die Fehlermeldung der Stufe enthält den Fehlercode des Python-Dienstes.
    assert code in json.dumps(value.get("detail"), ensure_ascii=False), (code, value)
    negative.append({"check": code, "webhook": f"ch28-multi{query}",
                     "rejected_by": stage, "status": status})
    print(f"PASS n8n negative {code}: rejected by {stage}")

_, comparison = request(f"{API}/report")
assert comparison["decision"] == "baseline"
assert comparison["baseline_pass"] == comparison["multi_pass"] == 8
assert comparison["total_baseline_stages"] == 8
assert comparison["total_multi_stages"] == 24

report = {
    "observed_at_utc": datetime.now(timezone.utc).isoformat(),
    "synthetic_data_only": True, "n8n_cases": rows,
    "negative_contract_checks": negative, "comparison": comparison,
}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS {len(rows) * 2} n8n paths + {len(negative)} negative checks via n8n")
print("decision: baseline; report: reports/live-observation.json")
