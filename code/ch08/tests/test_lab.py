import json
import os
import stat
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contract import ingest, order_count, page, retry_after_seconds, signature, validate  # noqa: E402
from init_env import initialize  # noqa: E402


class ChapterEightTests(unittest.TestCase):
    def setUp(self):
        self.event = {"event_id": "evt-123", "customer": "Birke", "amount_cents": 1250}
        self.raw = json.dumps(self.event, ensure_ascii=False, separators=(",", ":")).encode()
        self.headers = {
            "x-lab-timestamp": "1790510400",
            "x-lab-delivery": "del-123",
        }
        self.headers["x-lab-signature"] = signature(
            "this-is-a-test-secret-not-for-production", "1790510400", "del-123", self.raw
        )

    def test_pagination_has_three_bounded_pages(self):
        pages = [page(i, "http://api:8078") for i in (1, 2, 3)]
        self.assertEqual([len(item["data"]) for item in pages], [3, 3, 1])
        self.assertEqual(pages[-1]["next"], None)
        self.assertEqual(len({row["id"] for item in pages for row in item["data"]}), 7)
        with self.assertRaises(ValueError):
            page(4, "http://api:8078")

    def test_signature_binds_exact_bytes_timestamp_and_delivery_id(self):
        event, delivery = validate(
            self.raw, self.headers, "this-is-a-test-secret-not-for-production", now=1790510400
        )
        self.assertEqual((event, delivery), (self.event, "del-123"))
        for raw, changed in (
            (self.raw + b" ", self.headers),
            (self.raw, {**self.headers, "x-lab-delivery": "del-124"}),
            (self.raw, {**self.headers, "x-lab-timestamp": "1790510401"}),
        ):
            with self.assertRaises(PermissionError):
                validate(raw, changed, "this-is-a-test-secret-not-for-production", now=1790510400)

    def test_stale_and_malformed_deliveries_are_rejected(self):
        with self.assertRaises(PermissionError):
            validate(self.raw, self.headers, "this-is-a-test-secret-not-for-production", now=1790510701)
        malformed = b'{"event_id":"evt-123","customer":"Birke","amount_cents":true}'
        changed = dict(self.headers)
        changed["x-lab-signature"] = signature(
            "this-is-a-test-secret-not-for-production", "1790510400", "del-123", malformed
        )
        with self.assertRaises(ValueError):
            validate(malformed, changed, "this-is-a-test-secret-not-for-production", now=1790510400)

    def test_transaction_prevents_parallel_duplicate_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "orders.sqlite3"
            def write(_):
                return ingest(database, self.event, "del-123", self.raw)[0]
            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses = list(pool.map(write, range(12)))
            self.assertEqual(statuses.count(201), 1)
            self.assertEqual(statuses.count(200), 11)
            self.assertEqual(order_count(database), 1)

    def test_conflicting_reuse_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "orders.sqlite3"
            self.assertEqual(ingest(database, self.event, "del-123", self.raw)[0], 201)
            altered = {**self.event, "amount_cents": 2000}
            status, body = ingest(database, altered, "del-124", json.dumps(altered).encode())
            self.assertEqual((status, body["error"]), (409, "idempotency_conflict"))
            other = {**self.event, "event_id": "evt-999"}
            self.assertEqual(ingest(database, other, "del-123", json.dumps(other).encode())[0], 409)
            self.assertEqual(order_count(database), 1)

    def test_retry_after_delta_and_http_date(self):
        now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(retry_after_seconds("2", now), 2)
        self.assertEqual(retry_after_seconds("Sun, 27 Sep 2026 12:01:00 GMT", now), 60)
        self.assertEqual(retry_after_seconds("120", now), 60)
        with self.assertRaises(ValueError):
            retry_after_seconds("later", now)

    def test_workflows_enforce_webhook_gate_and_page_bound(self):
        pages = json.loads((ROOT / "n8n/workflows/ch08-pages.json").read_text())
        fetch = next(node for node in pages["nodes"] if node["name"] == "Fetch Pages")
        self.assertEqual(fetch["parameters"]["options"]["pagination"]["pagination"]["maxRequests"], 4)
        webhook = json.loads((ROOT / "n8n/workflows/ch08-webhook.json").read_text())
        nodes = {node["name"]: node for node in webhook["nodes"]}
        self.assertTrue(nodes["Untrusted Delivery"]["parameters"]["options"]["rawBody"])
        self.assertEqual(nodes["Verify and Commit"]["parameters"]["url"], "http://api:8078/ingest")
        self.assertEqual(nodes["Verify and Commit"]["parameters"]["contentType"], "binaryData")
        self.assertIn("neverError", json.dumps(nodes["Verify and Commit"]))
        self.assertEqual(
            webhook["connections"]["Untrusted Delivery"]["main"][0][0]["node"],
            "Verify and Commit",
        )

    def test_secret_file_is_private_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            self.assertTrue(initialize(path))
            first = path.read_text()
            self.assertFalse(initialize(path))
            self.assertEqual(first, path.read_text())
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertIn("WEBHOOK_SECRET=", first)


if __name__ == "__main__":
    unittest.main()
