"""Datierter n8n-/MCP-Prüflauf mit synthetischen Versionen und Scope-Gegenproben."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEBHOOK = "http://127.0.0.1:15732/webhook/ch32-policy"
API = "http://127.0.0.1:8132/operate"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch32-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def webhook(body: dict) -> dict:
    status, result = post(WEBHOOK, body)
    assert status == 200, (status, result)
    return result


def mcp(method: str, *, role: str, as_of: str, uri: str | None = None) -> dict:
    params = {"_meta": META}
    if uri is not None:
        params["uri"] = uri
    process = subprocess.run(
        ["docker", "compose", "exec", "-T", "-e", f"CH32_ROLE={role}",
         "-e", f"CH32_AS_OF={as_of}", "policy", "python", "-m", "ch32_lab.mcp_stdio"],
        input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) + "\n",
        capture_output=True, text=True, check=True, timeout=30)
    return json.loads(process.stdout.strip())


v1 = webhook({"action": "publish", "version_id": "2026-01"})
assert v1["status"] == "published" and v1["chunk_count"] >= 5
old = webhook({"action": "visible", "as_of": "2026-08-31", "role": "employee"})
assert any("10 Arbeitstage" in row["text"] for row in old["chunks"])
assert not any(row["audience"] == "hr" for row in old["chunks"])
print("PASS version 1: historical employee scope")

comparison = webhook({"action": "preview", "version_id": "2026-09"})
assert comparison["structural_chunk_count"] >= 5
assert comparison["table_chunk_count"] == 1
v2 = webhook({"action": "publish", "version_id": "2026-09"})
assert v2["status"] == "published" and v2["chunk_count"] == comparison["structural_chunk_count"]
current = webhook({"action": "visible", "as_of": "2026-09-29", "role": "employee"})
assert any("15 Arbeitstage" in row["text"] for row in current["chunks"])
assert any("30 Kalendertage" in row["text"] for row in current["chunks"])
assert not any("10 Arbeitstage" in row["text"] or "45 Kalendertage" in row["text"]
               for row in current["chunks"])
assert all(row["version_id"] == "2026-09" and row["audience"] == "all"
           for row in current["chunks"])
hr = webhook({"action": "visible", "as_of": "2026-09-29", "role": "hr"})
assert hr["count"] == current["count"] + 1
hr_only = next(row for row in hr["chunks"] if row["audience"] == "hr")
history = webhook({"action": "history"})
assert history["versions"][0]["valid_until"] == "2026-09-01"
assert history["versions"][1]["valid_until"] is None
print("PASS version 2: old facts absent; HR chunk filtered")

duplicate = webhook({"action": "publish", "version_id": "2026-09"})
assert duplicate["duplicate"] is True
for payload, reason in [({"action": "visible", "as_of": "2026-09-29", "role": "admin"}, "unknown_role"),
                        ({"action": "visible", "as_of": "2026-02-30", "role": "employee"}, "invalid_date"),
                        ({"action": "publish", "version_id": "unknown"}, "unknown_version")]:
    code, error = post(API, payload)
    assert (code, error["code"]) == (422, reason), (code, error)
print("PASS duplicate and invalid-scope/date/version contracts")

listing = mcp("resources/list", role="employee", as_of="2026-09-29")
resources = listing["result"]["resources"]
assert len(resources) == current["count"]
assert listing["result"]["ttlMs"] == 0 and listing["result"]["cacheScope"] == "private"
read = mcp("resources/read", role="employee", as_of="2026-09-29", uri=resources[0]["uri"])
assert read["result"]["contents"][0]["text"]
old_uri = "policy://RICHTLINIE-32/2026-01/" + old["chunks"][0]["chunk_id"]
hr_uri = "policy://RICHTLINIE-32/2026-09/" + hr_only["chunk_id"]
assert mcp("resources/read", role="employee", as_of="2026-09-29", uri=old_uri)["error"]["code"] == -32602
assert mcp("resources/read", role="employee", as_of="2026-09-29", uri=hr_uri)["error"]["code"] == -32602
print("PASS MCP: current employee list/read; old and HR read denied")

withdrawn = webhook({"action": "withdraw", "effective_at": "2026-10-01"})
assert withdrawn["status"] == "withdrawn"
later = webhook({"action": "visible", "as_of": "2026-10-02", "role": "employee"})
assert later["count"] == 0
assert mcp("resources/list", role="employee", as_of="2026-10-02")["result"]["resources"] == []
assert webhook({"action": "history"})["versions"] == history["versions"]
print("PASS withdrawal: future view empty; history retained")

report = {
    "observed_at_utc": datetime.now(timezone.utc).isoformat(),
    "synthetic_data_only": True,
    "n8n_image": "n8nio/n8n:2.40.7",
    "splitter_version": comparison["splitter_version"],
    "comparison": comparison,
    "versions": {"v1": v1, "v2": v2, "history": webhook({"action": "history"})},
    "visible_counts": {"historical_employee": old["count"],
                       "current_employee": current["count"], "current_hr": hr["count"],
                       "after_withdrawal_employee": later["count"]},
    "checks": ["n8n_published_webhook", "old_facts_absent", "hr_filtered",
               "mcp_read_denials", "withdrawal", "duplicate", "invalid_inputs"],
}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS chapter 32 live; report: reports/live-observation.json")
