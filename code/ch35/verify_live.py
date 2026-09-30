"""Echter n8n-Webhook, Python-Dienst und MCP-Resource-Gegenprobe."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from lab import answer

DIRECT = "http://127.0.0.1:8135/operate"
WEBHOOK = "http://127.0.0.1:15735/webhook/ch35-citations"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch35-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        assert response.status == 200
        return json.load(response)


def mcp(method: str, uri: str | None = None) -> dict:
    params = {"_meta": META}
    if uri:
        params["uri"] = uri
    message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    run = subprocess.run(["docker", "compose", "exec", "-T", "citation",
                          "python", "mcp_stdio.py"], input=json.dumps(message)+"\n",
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(run.stdout.strip())


observations = {}
for case_id in ("urlaub", "konflikt", "hr-verweigert", "hr-erlaubt"):
    via_n8n = post(WEBHOOK, {"action": "answer", "case_id": case_id})
    via_direct = post(DIRECT, {"action": "answer", "case_id": case_id})
    assert via_n8n == via_direct == answer(case_id)
    observations[case_id] = via_n8n
assert observations["urlaub"]["status"] == "answered"
assert len(observations["urlaub"]["claims"]) == 2
assert observations["konflikt"]["status"] == "conflict"
assert observations["hr-verweigert"]["status"] == "no_evidence"
assert observations["hr-erlaubt"]["status"] == "answered"

claims = observations["urlaub"]["claims"]
assert post(WEBHOOK, {"action": "verify", "case_id": "urlaub", "claims": claims})["accepted"]
bad = [{"sentence": "Erfundener Satz."}]
assert not post(WEBHOOK, {"action": "verify", "case_id": "urlaub", "claims": bad})["accepted"]

listed = mcp("resources/list")
uris = {item["uri"] for item in listed["result"]["resources"]}
assert "lab://ch35/urlaub-regel" in uris
assert "lab://ch35/hr-intern" not in uris
read = mcp("resources/read", "lab://ch35/urlaub-regel")
assert "15 Arbeitstage" in read["result"]["contents"][0]["text"]
assert mcp("resources/read", "lab://ch35/hr-intern")["error"]["message"] == "resource_outside_server_scope"

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "n8n_image": "n8nio/n8n:2.40.7", "model_calls": 0,
          "checks": ["n8n_webhook", "python_service", "scope_before_ranking",
                     "multi_document_citations", "conflict_abstention",
                     "missing_citation_rejected", "mcp_resources_scope"],
          "observations": observations}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print("PASS chapter 35 live: 4 cases, n8n, direct API, negative citation and MCP resource scope")
