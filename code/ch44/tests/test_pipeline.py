import http.client
import json
import os
import sys
import threading
import unittest
import urllib.error
from email.message import Message
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fixture_server
from mcp_stdio import handle
from pipeline import Budget, build_report, validate_report
from server import SOURCE_IDS, process
from source_io import read_source

FIXTURES = {"/api/quarter": ("api-quarter.json", "application/json", "2026-07-05T08:00:00Z", "0"),
            "/web/briefing": ("briefing.html", "text/html", "2026-07-06T07:00:00Z", "0"),
            "/web/tdm": ("tdm.html", "text/html", "2026-07-06T07:00:00Z", "1")}


class PipelineContract(unittest.TestCase):
    def setUp(self):
        self.hits = []
        self.get_tdm = {}  # optional override of the GET header per path
        self.patches = [patch("source_io.fetch", self.fake_fetch), patch("source_io.head", self.fake_head)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def headers(self, path, tdm):
        name, content_type, published, default_tdm = FIXTURES[path]
        headers = Message()
        headers["Content-Type"] = content_type
        headers["X-Published-At"] = published
        headers["tdm-reservation"] = default_tdm if tdm is None else tdm
        return headers

    def fake_head(self, url):
        path = urlsplit(url).path
        self.hits.append(("HEAD", path))
        if path == "/web/redirect":
            raise urllib.error.HTTPError(url, 302, "redirect", None, None)
        return self.headers(path, None)

    def fake_fetch(self, url):
        path = urlsplit(url).path
        self.hits.append(("GET", path))
        if path == "/web/redirect":
            raise urllib.error.HTTPError(url, 302, "redirect", None, None)
        if path == "/robots.txt":
            return b"User-agent: ch44-lab\nDisallow: /web/private\nAllow: /\n", Message()
        headers = self.headers(path, self.get_tdm.get(path))
        # Like source_io.fetch(): with tdm-reservation 1 the body is not read.
        body = b"" if headers["tdm-reservation"] == "1" else (ROOT / "data" / FIXTURES[path][0]).read_bytes()
        return body, headers

    def test_sources_and_policy_gates(self):
        accepted = [read_source(key) for key in ("api-quarter", "web-briefing", "file-regions")]
        self.assertEqual([row["status"] for row in accepted], ["accepted"] * 3)
        self.assertEqual(len({row["raw_sha256"] for row in accepted}), 3)
        blocked = [read_source(key) for key in ("web-robots-blocked", "web-tdm-blocked",
                                                  "web-terms-blocked", "web-redirect-blocked")]
        self.assertEqual([row["reason"] for row in blocked],
                         ["robots_disallow", "tdm_reserved", "terms_review_required", "redirect_blocked"])
        self.assertTrue(all("raw_text" not in row for row in blocked))
        requested = {path for _, path in self.hits}
        self.assertNotIn("/web/private", requested)
        self.assertNotIn("/web/terms", requested)
        # TDM page and redirect: HEAD only, no GET; accepted pages: HEAD, then GET.
        self.assertIn(("HEAD", "/web/tdm"), self.hits)
        self.assertNotIn(("GET", "/web/tdm"), self.hits)
        self.assertNotIn(("GET", "/web/redirect"), self.hits)
        self.assertLess(self.hits.index(("HEAD", "/api/quarter")), self.hits.index(("GET", "/api/quarter")))
        robots = len(b"User-agent: ch44-lab\nDisallow: /web/private\nAllow: /\n")
        self.assertEqual(blocked[1]["transfer_bytes"], robots)

    def test_get_contradicting_head_fails_closed(self):
        self.get_tdm["/web/briefing"] = "1"  # HEAD says 0, the later GET says 1
        row = read_source("web-briefing")
        self.assertEqual((row["status"], row["reason"]), ("blocked", "tdm_reserved"))
        self.assertNotIn("raw_text", row)
        self.assertEqual(row["transfer_bytes"], len(b"User-agent: ch44-lab\nDisallow: /web/private\nAllow: /\n"))

    def test_dedup_conflict_and_lineage(self):
        records = [read_source(key) for key in ("api-quarter", "web-briefing", "file-regions",
                                               "web-robots-blocked", "web-tdm-blocked",
                                               "web-terms-blocked", "web-redirect-blocked")]
        report = build_report(records)
        self.assertEqual(report["profile"]["accepted_count"], 3)
        self.assertEqual(report["profile"]["blocked_count"], 4)
        self.assertEqual(report["profile"]["duplicate_groups"], 2)
        self.assertEqual(report["profile"]["conflict_metrics"], 1)
        self.assertEqual(report["status"], "review_required")
        by_id = {row["statement_id"]: row for row in report["statements"]}
        self.assertEqual({c["value"] for c in by_id["orders"]["claims"]}, {"1198", "1200"})
        self.assertEqual(len(next(c for c in by_id["orders"]["claims"] if c["value"] == "1200")["evidence"]), 2)
        self.assertTrue(validate_report(report, records))
        for statement in report["statements"]:
            for claim in statement["claims"]:
                for evidence in claim["evidence"]:
                    self.assertIn("raw_sha256", evidence)
                    self.assertIn("retrieved_at_utc", evidence)
                    self.assertIn("published_at_utc", evidence)
                    self.assertEqual(evidence["steps"][-1], "deduplicate")

    def test_fabricated_statement_and_missing_timestamp_rejected(self):
        records = [read_source(key) for key in ("api-quarter", "web-briefing", "file-regions")]
        report = build_report(records)
        report["statements"][0]["text"] = "Frei erfundene Behauptung."
        self.assertFalse(validate_report(report, records))
        del records[0]["published_at_utc"]
        self.assertFalse(validate_report(report, records))

    def test_mcp_is_readonly_and_no_arbitrary_url(self):
        meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
        listing = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}})
        self.assertEqual([tool["name"] for tool in listing["result"]["tools"]], ["read_source"])
        bad = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "read_source", "arguments": {"source_id": "http://169.254.169.254/"}, "_meta": meta}})
        self.assertEqual(bad["error"]["message"], "source_not_allowlisted")
        write = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "write_source", "arguments": {}, "_meta": meta}})
        self.assertEqual(write["error"]["message"], "method_not_found")

    def test_budgets_and_gateway(self):
        budget = Budget(max_steps=1, max_bytes=2)
        budget.reserve_step()
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            budget.reserve_step()
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            budget.add_bytes(3)
        with self.assertRaisesRegex(ValueError, "invalid_request"):
            process({"action": "run", "url": "http://example.invalid"})
        with patch("server.mcp_read", read_source):
            report = process({"action": "run"})
        self.assertEqual(report["path"], "n8n-mcp-readonly")
        self.assertEqual(report["budget"]["steps"], 7)

    def test_n8n_artifact(self):
        flow = json.loads((ROOT / "n8n" / "ch44-research.json").read_text())
        self.assertEqual(len(flow["nodes"]), 3)
        self.assertIn("analyst:8145/research", flow["nodes"][1]["parameters"]["url"])


class FixtureServerHead(unittest.TestCase):
    """Real client against the real fixture server, briefly on a free port on 127.0.0.1."""

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), fixture_server.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        with fixture_server.LOCK:
            fixture_server.HITS.clear()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_server_answers_head_without_body(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        connection.request("HEAD", "/web/tdm")
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("tdm-reservation"), "1")
        self.assertEqual(int(response.getheader("Content-Length")), len((ROOT / "data" / "tdm.html").read_bytes()))
        self.assertEqual(body, b"")

    def test_pipeline_uses_head_for_tdm_page(self):
        with patch.dict(os.environ, {"CH44_FIXTURE_BASE": f"http://127.0.0.1:{self.port}"}):
            rows = {source_id: read_source(source_id) for source_id in SOURCE_IDS}
        self.assertEqual(rows["web-tdm-blocked"]["reason"], "tdm_reserved")
        self.assertEqual(rows["web-redirect-blocked"]["reason"], "redirect_blocked")
        self.assertEqual(sum(row["status"] == "accepted" for row in rows.values()), 3)
        with fixture_server.LOCK:
            hits = list(fixture_server.HITS)
        self.assertIn("HEAD /web/tdm", hits)
        self.assertNotIn("GET /web/tdm", hits)
        self.assertNotIn("GET /web/redirect", hits)
        self.assertIn("GET /web/briefing", hits)
        self.assertFalse({"/web/private", "/web/terms"} & {hit.split(" ", 1)[1] for hit in hits})


if __name__ == "__main__":
    unittest.main()
