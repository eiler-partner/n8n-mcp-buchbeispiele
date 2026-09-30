from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


webhook = "http://127.0.0.1:15726/webhook/ch26-extract"
observations = []
for case_id in ("c01", "c05", "c08"):
    result = post(webhook, {"case_id": case_id, "variant": "candidate"})
    assert result["contract_pass"] and result["golden_pass"], result
    assert result["exact_match"] is True, result
    observations.append({"case_id": case_id, "variant": "candidate",
                         "contract_pass": result["contract_pass"],
                         "golden_pass": result["golden_pass"],
                         "exact_match": result["exact_match"]})
    print(f"candidate {case_id}: contract + golden pass")
for case_id, error in (("c05", "schema"), ("c06", "schema"), ("c08", "golden_mismatch")):
    result = post(webhook, {"case_id": case_id, "variant": "baseline"})
    assert result["error_class"] == error and not result["golden_pass"], result
    assert result["exact_match"] is False, result
    observations.append({"case_id": case_id, "variant": "baseline",
                         "error_class": result["error_class"],
                         "golden_pass": result["golden_pass"],
                         "exact_match": result["exact_match"]})
    print(f"baseline {case_id}: {error}")
try:
    post("http://127.0.0.1:8126/extract", {"case_id": "unknown", "variant": "candidate"})
except urllib.error.HTTPError as exc:
    assert exc.code == 422, exc.code
    observations.append({"negative_request": "unknown_case", "status": exc.code})
else:
    raise AssertionError("Unbekannte Testfälle müssen abgewiesen werden")
print("invalid request: 422")
report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "scope": "synthetic local n8n and Docker integration; no model quality claim",
          "checks": observations, "all_passed": True}
path = Path(__file__).resolve().parent / "reports/live-observation.json"
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS chapter 26 live; report: {path.relative_to(path.parent.parent)}")
