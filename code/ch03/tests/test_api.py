import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import Handler  # noqa: E402


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        class IsolatedHandler(Handler):
            data_dir = Path(cls.temp.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), IsolatedHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def request(self, path, method="GET", body=None, content_type=None):
        headers = {"Content-Type": content_type} if content_type else {}
        req = Request(self.base + path, data=body, method=method, headers=headers)
        try:
            response = urlopen(req, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, dict(response.headers), json.load(response)

    def test_health(self):
        status, _, body = self.request("/health")
        self.assertEqual((status, body), (200, {"status": "ok"}))

    def test_document_matches_schema(self):
        status, headers, body = self.request("/documents/doc-1")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        schema = json.loads((ROOT / "document.schema.json").read_text())
        Draft202012Validator(schema).validate(body)

    def test_document_schema_detects_wrong_type(self):
        schema = json.loads((ROOT / "document.schema.json").read_text())
        self.assertFalse(Draft202012Validator(schema).is_valid(
            {"id": "doc-1", "title": "x", "version": "3", "published": True}
        ))

    def test_pagination(self):
        status, _, body = self.request("/documents?limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["next_cursor"], 1)
        _, _, second = self.request("/documents?limit=1&cursor=1")
        self.assertIsNone(second["next_cursor"])

    def test_invalid_pagination(self):
        status, _, body = self.request("/documents?limit=0")
        self.assertEqual((status, body["error"]), (400, "invalid_pagination"))

    def test_unknown_document(self):
        status, _, body = self.request("/documents/doc-999")
        self.assertEqual((status, body["error"]), (404, "document_not_found"))

    def test_wrong_method(self):
        status, headers, body = self.request("/reviews")
        self.assertEqual((status, headers["Allow"], body["error"]),
                         (405, "POST", "method_not_allowed"))

    def test_missing_media_type(self):
        status, _, body = self.request("/reviews", "POST", b"{}", "text/plain")
        self.assertEqual((status, body["error"]), (415, "json_required"))

    def test_malformed_json(self):
        status, _, body = self.request("/reviews", "POST", b'{"document_id":',
                                       "application/json")
        self.assertEqual((status, body["error"]), (400, "invalid_json"))

    def test_schema_mismatch(self):
        status, _, body = self.request("/reviews", "POST", b'{"document_id":"doc-1"}',
                                       "application/json")
        self.assertEqual((status, body["error"]), (422, "schema_mismatch"))

    def test_create_and_get_review(self):
        body = b'{"document_id":"doc-1","decision":"approve"}'
        status, headers, created = self.request(
            "/reviews", "POST", body, "application/json"
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["document_id"], "doc-1")
        location = headers["Location"]
        self.assertTrue(location.startswith("/reviews/"))
        read_status, _, stored = self.request(location)
        self.assertEqual(read_status, 200)
        self.assertEqual(stored, created)


if __name__ == "__main__":
    unittest.main()
