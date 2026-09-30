"""Datiertes Live-Protokoll für HTTP, n8n und MCP-stdio."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from decide import all_decisions, decide, profiles

DIRECT = "http://127.0.0.1:8137/decide"
WEBHOOK = "http://127.0.0.1:15737/webhook/ch37-architecture"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch37-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        assert response.status == 200
        return json.load(response)


def mcp(message: dict) -> dict:
    run = subprocess.run(["docker", "compose", "exec", "-T", "architect", "python", "mcp_stdio.py"],
                         input=json.dumps(message) + "\n", capture_output=True, text=True, check=True, timeout=30)
    return json.loads(run.stdout.strip())


local = all_decisions()
assert post(DIRECT, {"action": "all"}) == local
assert post(WEBHOOK, {"action": "all"}) == local
assert [row["selected"] for row in local["decisions"]] == ["cloud", "self_hosted", "hybrid"]
for key in profiles():
    expected = decide(profiles()[key])
    assert post(WEBHOOK, {"action": "profile", "profile_id": key}) == expected
    called = mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"_meta": META, "name": "decide_architecture", "arguments": {"profile_id": key}}})
    assert json.loads(called["result"]["content"][0]["text"]) == expected

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "n8n_image": "n8nio/n8n:2.40.7", "model_calls": 0,
          "checks": ["three_profiles", "hard_gates", "same_policy_hash", "direct_http", "n8n_webhook", "mcp_stdio"],
          "result": local}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS chapter 37 live: 3 profiles via Python, HTTP, n8n and MCP")
