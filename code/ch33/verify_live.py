"""Datierte Ende-zu-Ende-Gegenprobe: n8n, PostgreSQL/pgvector, Qdrant, MCP."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEBHOOK = "http://127.0.0.1:15733/webhook/ch33-vectors"
DIRECT = "http://127.0.0.1:8133/operate"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch33-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def ok(url: str, body: dict) -> dict:
    code, result = post(url, body)
    assert code == 200, (code, result)
    return result


def search(store: str, model: str, *, role="employee", as_of="2026-09-29", vector=None,
           top_k=3, via_n8n=False) -> dict:
    dim = 4 if model == "fixture-v1" else 6
    payload = {"action": "query", "store": store, "model_id": model,
               "tenant_id": "buchlabor", "role": role, "as_of": as_of,
               "vector": vector or [1.0, 0.1, 0.1, 0.1] + ([0.05, 0.02] if dim == 6 else []),
               "top_k": top_k}
    return ok(WEBHOOK if via_n8n else DIRECT, payload)


def mcp(arguments: dict):
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"_meta": META, "name": "search_fixture_vectors",
                          "arguments": arguments}}
    proc = subprocess.run(["docker", "compose", "exec", "-T", "vectors",
                           "python", "mcp_stdio.py"], input=json.dumps(message) + "\n",
                          text=True, capture_output=True, check=True, timeout=30)
    return json.loads(proc.stdout.strip())


observations = []
for model in ("fixture-v1", "fixture-v2"):
    seeded = ok(WEBHOOK, {"action": "seed", "model_id": model})
    assert seeded["count"] == 8
    again = ok(DIRECT, {"action": "seed", "model_id": model})
    assert again == seeded
    pg = search("pgvector", model, via_n8n=True)
    qd = search("qdrant", model, via_n8n=True)
    assert [x["chunk_id"] for x in pg["hits"]] == [x["chunk_id"] for x in qd["hits"]]
    assert [x["text_sha256"] for x in pg["hits"]] == [x["text_sha256"] for x in qd["hits"]]
    assert pg["hits"][0]["section_id"] == "vacation"
    assert all(x["version_id"] == "2026-09" and x["audience"] == "all"
               for x in pg["hits"] + qd["hits"])
    old = search("qdrant", model, as_of="2026-08-31")
    assert all(x["version_id"] == "2026-01" for x in old["hits"])
    hr = search("pgvector", model, role="hr", vector=[0.1, 0.1, 0.1, 1.0] +
                ([0.05, 0.02] if model == "fixture-v2" else []), top_k=4)
    assert hr["hits"][0]["audience"] == "hr"
    employee = search("qdrant", model, vector=[0.1, 0.1, 0.1, 1.0] +
                      ([0.05, 0.02] if model == "fixture-v2" else []), top_k=4)
    assert all(x["audience"] == "all" for x in employee["hits"])
    # Gleichstand: Urlaub und Reisekosten liegen symmetrisch zum Anfragevektor.
    tie_vector = [1.0, 1.0, 0.1, 0.1] + ([0.05, 0.02] if model == "fixture-v2" else [])
    tie_ids = {}
    for store in ("pgvector", "qdrant"):
        two = search(store, model, vector=tie_vector, top_k=2)["hits"]
        assert two[0]["score"] == two[1]["score"], (store, "kein exakter Gleichstand", two)
        one = search(store, model, vector=tie_vector, top_k=1)["hits"]
        tie_ids[store] = [x["chunk_id"] for x in two]
        assert tie_ids[store] == ["v2-travel", "v2-vacation"], (store, tie_ids[store])
        assert [x["chunk_id"] for x in one] == ["v2-travel"], (store, one)
    observations.append({"model_id": model, "dimension": seeded["dimension"],
                         "top_ids": [x["chunk_id"] for x in pg["hits"]],
                         "old_version_top_id": old["hits"][0]["chunk_id"],
                         "hr_top_id": hr["hits"][0]["chunk_id"],
                         "tie_top_ids": tie_ids})
    print("PASS", model, "same scoped order in both stores; version and role filters;",
          "equal scores ordered by chunk_id")

bad = {"action": "query", "store": "pgvector", "model_id": "fixture-v2",
       "tenant_id": "buchlabor", "role": "employee", "as_of": "2026-09-29",
       "vector": [1, 0, 0, 0]}
assert post(DIRECT, bad) == (422, {"code": "invalid_query_vector"})
for field, value, reason in (("tenant_id", "other", "unknown_tenant"),
                             ("role", "admin", "unknown_role"),
                             ("as_of", "2026-10-02", "no_visible_version")):
    body = {**bad, "model_id": "fixture-v1", field: value}
    assert post(DIRECT, body) == (422, {"code": reason})
print("PASS dimension, tenant, role and withdrawal rejects")

tool = mcp({"store": "qdrant", "model_id": "fixture-v1", "vector": [1, 0.1, 0.1, 0.1]})
assert "result" in tool
mcp_hits = json.loads(tool["result"]["content"][0]["text"])["hits"]
assert mcp_hits[0]["section_id"] == "vacation"
assert all(x["audience"] == "all" for x in mcp_hits)
print("PASS MCP scoped tool path")

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "synthetic_vectors_only": True, "n8n_image": "n8nio/n8n:2.40.7",
          "observations": observations,
          "checks": ["n8n_webhook_both_stores", "repeatable_seed",
                     "pgvector_qdrant_same_top_ids_and_hashes",
                     "equal_score_tie_break_both_stores", "old_version",
                     "hr_filtered", "dimension_reject", "tenant_reject",
                     "withdrawal_reject", "mcp_scoped_tool"]}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS chapter 33 live; reports/live-observation.json")
