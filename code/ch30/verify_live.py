"""Prüft den publizierten n8n-Pfad gegen Quelle, Rechte und Ablehnung."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ch30_lab.core import compare

WEBHOOK = "http://127.0.0.1:15730/webhook/ch30-rag"
API = "http://127.0.0.1:8130"


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


cases = [
    ("current", {"question_tag": "urlaub", "tenant": "werk", "role": "employee", "as_of": "2026-09-29"}, "answered"),
    ("old", {"question_tag": "urlaub", "tenant": "werk", "role": "employee", "as_of": "2025-09-29"}, "answered"),
    ("private_denied", {"question_tag": "gehalt", "tenant": "werk", "role": "employee"}, "withheld"),
    ("private_allowed", {"question_tag": "gehalt", "tenant": "werk", "role": "hr"}, "answered"),
    ("unknown", {"question_tag": "unbekannt", "tenant": "werk", "role": "employee"}, "withheld"),
]
observed = []
for name, payload, expected in cases:
    result = post(WEBHOOK, payload)
    direct = post(f"{API}/compare", payload)["results"][2]
    assert result["status"] == expected, (name, result)
    assert result["answer"] == direct["answer"], (name, result)
    assert result["citations"] == direct["citations"], (name, result)
    if expected == "withheld":
        assert result["answer"] is None and not result["citations"]
    observed.append({"case": name, "status": expected, "citations": result["citations"]})
    print(f"PASS n8n {name}: {expected}")

meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch30-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}
messages = [
    {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {"_meta": meta}},
    {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"_meta": meta,
     "uri": "rag://werk/leave-policy/2/leave-v2-a"}},
    {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"_meta": meta,
     "uri": "rag://werk/salary-policy/1/salary-v1-a"}},
]
env = os.environ | {"CH30_TENANT": "werk", "CH30_ROLE": "employee"}
process = subprocess.run(["python3.12", "-m", "ch30_lab.mcp_stdio"],
                         input="\n".join(json.dumps(row) for row in messages) + "\n",
                         text=True, capture_output=True, check=True, env=env)
answers = [json.loads(line) for line in process.stdout.splitlines()]
assert len(answers) == 3
assert any("leave-v2-a" in row["uri"] for row in answers[0]["result"]["resources"])
assert all("salary" not in row["uri"] for row in answers[0]["result"]["resources"])
assert "15 Arbeitstage" in answers[1]["result"]["contents"][0]["text"]
assert answers[2]["error"]["code"] == -32602
print("PASS MCP resource list/read/denied")

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "synthetic_data_only": True, "cases": observed,
          "mcp_resource_checks": ["list", "read", "denied"],
          "strategy_comparison": compare(cases[0][1])}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS chapter 30 live; report: reports/live-observation.json")
