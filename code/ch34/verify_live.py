"""Datierter Ende-zu-Ende-Test der vier Suchvarianten und ihrer Scope-Grenzen."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from lab import CASES, CORPUS, MODES, visible

DIRECT = "http://127.0.0.1:8134/operate"
WEBHOOK = "http://127.0.0.1:15734/webhook/ch34-retrieval"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch34-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def ok(url: str, body: dict) -> dict:
    code, result = post(url, body)
    assert code == 200, (code, result)
    return result


def mcp(case_id: str, mode: str) -> dict:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"_meta": META, "name": "compare_retrieval",
                          "arguments": {"case_id": case_id, "mode": mode}}}
    run = subprocess.run(["docker", "compose", "exec", "-T", "retrieval",
                          "python", "mcp_stdio.py"], input=json.dumps(message)+"\n",
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(run.stdout.strip())


seeded = ok(WEBHOOK, {"action": "seed"})
assert seeded["count"] == len(CORPUS)
assert ok(DIRECT, {"action": "seed"}) == seeded
evaluation = ok(WEBHOOK, {"action": "evaluate"})
assert len(evaluation["cases"]) == len(CASES) * len(MODES)
assert set(evaluation["summary"]) == set(MODES)
for result in evaluation["cases"]:
    case = CASES[result["case_id"]]
    allowed = {r["id"] for r in CORPUS if visible(r, case)}
    ids = [hit["id"] for hit in result["hits"]]
    assert len(ids) == len(set(ids)) and set(ids) <= allowed
    assert len(ids) <= 3
    assert result["scope"]["version"] == ("2026-01" if case["as_of"] < "2026-09-01" else "2026-09")
print(f"PASS {len(evaluation['cases'])} variant/case runs; every hit within tenant, role, status and version")

# FTS-Zweig mit und ohne freigegebene Expansion im Fall rkk-frist (vor der Fusion)
rkk = {r["mode"]: r for r in evaluation["cases"] if r["case_id"] == "rkk-frist"}
rkk_ids = {mode: [hit["id"] for hit in rkk[mode]["hits"]] for mode in MODES}
assert rkk_ids["lexical"] == [], rkk_ids
assert rkk_ids["lexical_expanded"] == ["v2-travel"], rkk_ids
assert rkk_ids["hybrid"] == rkk_ids["hybrid_expanded"], rkk_ids
assert rkk["hybrid"]["metrics"] == rkk["hybrid_expanded"]["metrics"]
assert abs(rkk["hybrid"]["hits"][0]["score"] - 1 / 61) < 1e-9
assert abs(rkk["hybrid_expanded"]["hits"][0]["score"] - 2 / 61) < 1e-9
print("PASS rkk-frist FTS branch: without expansion", rkk_ids["lexical"],
      "| with expansion", rkk_ids["lexical_expanded"],
      "| fused top IDs unchanged", rkk_ids["hybrid_expanded"])

employee_hr = [r for r in evaluation["cases"] if r["case_id"] == "hr-code-denied"]
assert all(not r["hits"] for r in employee_hr)
authorized_hr = [r for r in evaluation["cases"] if r["case_id"] == "hr-code-authorized"]
assert all(r["hits"] and r["hits"][0]["id"] == "v2-hr" for r in authorized_hr)
assert post(DIRECT, {"action": "search", "case_id": "unknown", "mode": "hybrid"}) == (422, {"code": "unknown_case"})
assert post(DIRECT, {"action": "search", "case_id": "vacation-frist", "mode": "unknown"}) == (422, {"code": "unknown_mode"})
print("PASS no-answer and HR authorization boundary; invalid case/mode rejected")

tool = mcp("vacation-frist", "hybrid")
assert "result" in tool
tool_result = json.loads(tool["result"]["content"][0]["text"])
assert tool_result["case_id"] == "vacation-frist"
assert mcp("hr-code-authorized", "hybrid")["error"]["message"] == "case_outside_server_scope"
print("PASS MCP employee scope; HR case denied")

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "synthetic_vectors_only": True, "n8n_image": "n8nio/n8n:2.40.7",
          "seed": seeded, "evaluation": evaluation,
          "fts_expansion_rkk_frist": rkk_ids,
          "checks": ["n8n_webhook", "postgres_fts", "pgvector_exact",
                     "rrf", "fts_expansion_branch", "four_scopes_before_top_k", "no_answer",
                     "hr_denial", "mcp_employee_scope", "repeatable_seed"]}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print("PASS chapter 34 live; reports/live-observation.json")
print("SUMMARY", json.dumps(evaluation["summary"], ensure_ascii=False))
