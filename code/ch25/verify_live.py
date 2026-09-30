from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


base = "http://127.0.0.1:15725/webhook/ch25-select"
observations = []
for scenario, expected in [
    ("lokal-qualitaet", "praezise-lokal"),
    ("lokal-kosten", "sparsam-lokal"),
    ("tool-lokal", "praezise-lokal"),
]:
    case_id = "t01" if scenario == "tool-lokal" else "c01"
    result = post(base, {"scenario": scenario, "case_id": case_id})
    assert result["selected"] == expected, result
    assert result["fixture_invocation"]["profile"] == expected, result
    assert result["measurement_kind"] == "synthetic_fixture_not_real_model_benchmark"
    observations.append({"scenario": scenario, "selected": result["selected"],
                         "measurement_kind": result["measurement_kind"]})
    print(f"{scenario}: {result['selected']}")
result = post(base, {"scenario": "lokal-qualitaet", "failure_kind": "timeout"})
assert result["selected"] == "sparsam-lokal" and result["fallback_from"] == "praezise-lokal"
observations.append({"scenario": "timeout_fallback", "selected": result["selected"],
                     "fallback_from": result["fallback_from"]})
print("timeout fallback: sparsam-lokal")

for payload in [
    {"scenario": "lokal-qualitaet", "failure_kind": "policy"},
    {"scenario": "tool-lokal", "failure_kind": "timeout"},
    {"scenario": "unbekannt"},
]:
    try:
        post("http://127.0.0.1:8125/choose", payload)
    except urllib.error.HTTPError as exc:
        assert exc.code == 422, exc.code
        observations.append({"negative_request": payload, "status": exc.code})
    else:
        raise AssertionError(f"fail-closed erwartet: {payload}")
print("negative contracts: 422")
report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "scope": "synthetic local n8n and Docker integration; no model benchmark",
          "checks": observations, "all_passed": True}
path = Path(__file__).resolve().parent / "reports/live-observation.json"
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS chapter 25 live; report: {path.relative_to(path.parent.parent)}")
