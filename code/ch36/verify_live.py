"""Datierter Live-Test für n8n, HTTP und MCP im Kapitel-36-Stack."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from evaluate import CASES, GATES, evaluate_all, evaluate_case

DIRECT = "http://127.0.0.1:8136/evaluate"
WEBHOOK = "http://127.0.0.1:15736/webhook/ch36-evaluation"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch36-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        assert response.status == 200
        return json.load(response)


def mcp(message: dict) -> dict:
    run = subprocess.run(["docker", "compose", "exec", "-T", "evaluator",
                          "python", "mcp_stdio.py"], input=json.dumps(message)+"\n",
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(run.stdout.strip())


via_n8n = post(WEBHOOK, {"action": "compare"})
via_direct = post(DIRECT, {"action": "compare"})
local = evaluate_all()
for report in (via_n8n, via_direct, local):
    report.pop("observed_at_utc")
assert via_n8n == via_direct == local
assert len(via_n8n["results"]) == 4
assert [row["release"] for row in via_n8n["results"]] == ["hold", "pass", "hold", "hold"]
assert via_n8n["gate_policy"] == GATES

case_body = {"action": "case", "case_id": "travel_hard_negative",
             "chunking": "short", "retrieval": "expanded"}
assert post(WEBHOOK, case_body) == evaluate_case(CASES["travel_hard_negative"], "short", "expanded")

listed = mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}})
assert listed["result"]["tools"][0]["name"] == "compare_rag_variants"
called = mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"_meta": META, "name": "compare_rag_variants", "arguments": {}}})
summary = json.loads(called["result"]["content"][0]["text"])
assert [row["release"] for row in summary["results"]] == ["hold", "pass", "hold", "hold"]
assert summary["golden_sha256"] == via_n8n["golden_sha256"]

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "n8n_image": "n8nio/n8n:2.40.7", "model_calls": 0,
          "checks": ["four_paired_variants", "same_hashes", "n8n_webhook", "python_service",
                     "hard_negative", "mcp_summary", "release_gate"],
          "evaluation": via_n8n}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print("PASS chapter 36 live: four variants, 10 cases, n8n, HTTP and MCP")
