import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core
from core import answer, corpus, digest, identity, retrieve, sign, unauthorized_retrieval, validate_answer
from mcp_stdio import handle
import verify_live
from verify_live import CASES

KEY = b"test-key-ch43-long-enough-for-hmac-signing"


def actor(tenant="acme", groups=None):
    return {"sub": "reader-1", "tenant": tenant, "groups": groups or ["staff"],
            "aud": "ch43-knowledge", "exp": int(time.time()) + 300}


class Contract(unittest.TestCase):
    def setUp(self):
        os.environ["CH43_SIGNING_KEY"] = KEY.decode()

    def test_ingestion_quarantine_and_version(self):
        chunks, quarantine = corpus()
        self.assertEqual({x["source_id"] for x in quarantine}, {"scan", "hostile"})
        self.assertNotIn(1, [x["version"] for x in chunks if x["source_id"] == "travel"])
        self.assertIn(2, [x["version"] for x in chunks if x["source_id"] == "travel"])

    def test_authorized_extract_with_checked_citation(self):
        who = actor()
        found = retrieve("Wann brauchen Dienstreisen eine Genehmigung?", who)
        result = answer("Wann brauchen Dienstreisen eine Genehmigung?", who, found)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["citations"][0]["source_id"], "travel")
        self.assertEqual(result["citations"][0]["version"], 2)

    def test_acl_before_ranking_and_cross_tenant(self):
        staff = actor()
        self.assertNotIn("finance", [x["source_id"] for x in retrieve("internes Projektbudget Orion 73000", staff)])
        self.assertNotIn("beta", [x["source_id"] for x in retrieve("Standort Beta Dezember sieben Tage", staff)])
        self.assertIn("finance", [x["source_id"] for x in retrieve("internes Projektbudget Orion 73000", actor(groups=["finance"]))])
        self.assertIn("beta", [x["source_id"] for x in retrieve("Standort Beta Dezember sieben Tage", actor(tenant="beta"))])

    def test_refusal_without_evidence(self):
        who = actor()
        result = answer("Welche Marsmission hat die Firma genehmigt?", who,
                        retrieve("Welche Marsmission hat die Firma genehmigt?", who))
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["citations"], [])

    def test_forged_and_stale_citations_fail(self):
        who = actor()
        found = retrieve("Dienstreisen Genehmigung", who)
        top = found[0]
        citation = {k: top[k] for k in ("source_id", "version", "section", "sha256")}
        self.assertFalse(validate_answer({"quote": "Frei erfundener Satz", "citation": citation}, found, who))
        self.assertFalse(validate_answer({"quote": top["text"], "citation": dict(citation, version=1)}, found, who))
        self.assertFalse(validate_answer({"quote": top["text"], "citation": dict(citation, source_id="finance")}, found, who))

    def test_source_changed_after_retrieval_fails(self):
        who = actor()
        found = retrieve("Dienstreisen Genehmigung", who)
        top = found[0]
        citation = {k: top[k] for k in ("source_id", "version", "section", "sha256")}
        source = json.loads((ROOT / "data" / "handbook.json").read_text())
        for doc in source["documents"]:
            if doc["id"] == "travel" and doc["version"] == 2:
                doc["sections"][0]["text"] = "Diese Richtlinie wurde geändert."
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handbook.json"
            path.write_text(json.dumps(source))
            self.assertFalse(validate_answer({"quote": top["text"], "citation": citation}, found, who, path=path))

    def test_bad_token_and_no_client_groups(self):
        token = sign(actor(), KEY)
        self.assertEqual(identity(token, KEY)["groups"], ["staff"])
        with self.assertRaises(ValueError):
            identity(token + "x", KEY)
        with self.assertRaises(ValueError):
            identity(sign(dict(actor(), exp=1), KEY), KEY)

    def test_modern_mcp_tool_call(self):
        token = sign(actor(), KEY)
        call = {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
            "name": "search_evidence", "arguments": {"question": "Dienstreisen Genehmigung", "actor_token": token},
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}}
        response = handle(call)
        self.assertEqual(response["result"]["resultType"], "complete")
        self.assertIn("travel", [c["source_id"] for c in response["result"]["structuredContent"]["candidates"]])
        call["params"]["arguments"]["question"] = "internes Projektbudget Orion 73000"
        self.assertEqual(handle(call)["result"]["structuredContent"]["candidates"], [])
        call["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2025-06-18"
        self.assertEqual(handle(call)["error"]["message"], "unsupported_protocol_version")

    def mcp_runs(self):
        runs = {}
        for name, (question, tenant, groups, _) in CASES.items():
            token = sign(actor(tenant, groups), KEY)
            response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_evidence", "arguments": {"question": question, "actor_token": token},
                "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}})
            runs[name] = (identity(token, KEY), response["result"]["structuredContent"]["candidates"])
        return runs

    def test_golden_cases_and_zero_unauthorized_retrieval(self):
        runs = self.mcp_runs()
        for name, (who, candidates) in runs.items():
            self.assertEqual(answer(CASES[name][0], who, candidates)["status"], CASES[name][3], name)
        old = answer(CASES["old_wording_current_version"][0], *runs["old_wording_current_version"])
        self.assertEqual(old["citations"][0]["version"], 2)
        metric = unauthorized_retrieval(runs)
        self.assertEqual((metric["queries"], metric["queries_with_forbidden_candidate"]), (8, 0))
        self.assertEqual(metric["forbidden_candidates"], {})

    def test_leaky_retriever_raises_unauthorized_retrieval(self):
        # Deliberately leaky: the ACL filter before scoring is switched off.
        runs = {}
        with mock.patch.object(core, "authorized", lambda chunk, who: True):
            for name, (question, tenant, groups, _) in CASES.items():
                runs[name] = (actor(tenant, groups), retrieve(question, actor(tenant, groups)))
        metric = unauthorized_retrieval(runs)
        self.assertEqual(set(metric["forbidden_candidates"]), {"staff_finance_denied", "cross_tenant_denied"})
        self.assertEqual((metric["queries_with_forbidden_candidate"], metric["queries"], metric["rate"]), (2, 8, 0.25))

    def test_leak_in_positive_query_counts(self):
        # Stale index: version 1 is still a candidate although the answer comes from version 2.
        runs = {name: (actor(t, g), retrieve(q, actor(t, g))) for name, (q, t, g, _) in CASES.items()}
        old = next(doc for doc in json.loads((ROOT / "data" / "handbook.json").read_text())["documents"]
                   if doc["id"] == "travel" and doc["version"] == 1)
        text = old["sections"][0]["text"]
        who, candidates = runs["staff_travel"]
        candidates.append({"source_id": "travel", "version": 1, "section": "2", "tenant": "acme",
                           "groups": ["staff"], "text": text, "sha256": digest(text), "score": 0.1})
        result = answer(CASES["staff_travel"][0], who, candidates)
        self.assertEqual((result["status"], result["citations"][0]["version"]), ("answered", 2))
        metric = unauthorized_retrieval(runs)
        self.assertEqual(metric["forbidden_candidates"],
                         {"staff_travel": [{"source_id": "travel", "version": 1, "section": "2"}]})
        self.assertEqual((metric["queries_with_forbidden_candidate"], metric["queries"]), (1, 8))

    def test_live_helper_reads_candidate_lists_from_mcp(self):
        def local_exec(env, *args, check=True, stdin_text=None):
            self.assertEqual(args, ("exec", "-T", "knowledge", "python", "mcp_stdio.py"))
            return subprocess.run([sys.executable, str(ROOT / "mcp_stdio.py")], input=stdin_text,
                                  text=True, capture_output=True, check=True, timeout=10)
        calls = {name: (q, sign(actor(t, g), KEY)) for name, (q, t, g, _) in CASES.items()}
        with mock.patch.object(verify_live, "compose", local_exec):
            found = verify_live.mcp_candidates({}, calls)
        self.assertEqual(list(found), list(CASES))
        self.assertEqual([c["source_id"] for c in found["finance_allowed"]], ["finance"])
        self.assertEqual(found["staff_finance_denied"], [])
        self.assertEqual({c["version"] for c in found["old_wording_current_version"]}, {2})

    def test_n8n_artifact(self):
        flow = json.loads((ROOT / "n8n" / "ch43-knowledge.json").read_text())
        self.assertEqual(len(flow["nodes"]), 3)
        self.assertIn("knowledge:8143/ask", flow["nodes"][1]["parameters"]["url"])


if __name__ == "__main__":
    unittest.main()
