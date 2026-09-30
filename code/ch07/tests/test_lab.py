import json
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import Handler  # noqa: E402
from data import CASES, envelope, expected_summary  # noqa: E402
from init_env import initialize  # noqa: E402


class ChapterSevenTests(unittest.TestCase):
    def test_empty_input_has_a_real_zero_summary(self):
        self.assertEqual(envelope("empty")["records"], [])
        self.assertEqual(expected_summary("empty")["unique_count"], 0)
        self.assertIsNone(expected_summary("empty")["first_id"])

    def test_single_input_is_preserved(self):
        self.assertEqual(expected_summary("single")["north_cents"], 1250)
        self.assertEqual(expected_summary("single")["unique_count"], 1)

    def test_large_input_filters_and_deduplicates(self):
        summary = expected_summary("large")
        self.assertEqual((summary["raw_count"], summary["eligible_count"], summary["unique_count"]), (150, 133, 114))
        self.assertEqual((summary["north_cents"], summary["south_cents"]), (54000, 46400))
        self.assertEqual((summary["first_id"], summary["last_id"]), ("R-002", "R-123"))

    def test_all_filtered_is_not_lost(self):
        self.assertEqual(expected_summary("filtered")["raw_count"], 2)
        self.assertEqual(expected_summary("filtered")["eligible_count"], 0)
        self.assertEqual(expected_summary("filtered")["unique_count"], 0)

    def test_api_returns_envelopes_and_404(self):
        for case in (*CASES, "unknown"):
            handler = Handler.__new__(Handler)
            handler.path = f"/cases/{case}"
            handler.wfile = io.BytesIO()
            statuses = []
            handler.send_response = statuses.append
            handler.send_header = lambda *_: None
            handler.end_headers = lambda: None
            handler.do_GET()
            body = json.loads(handler.wfile.getvalue())
            self.assertEqual(statuses, [200] if case in CASES else [404])
            self.assertEqual(body, envelope(case) if case in CASES else {"error": "not_found"})

    def test_subworkflow_contains_explicit_data_nodes(self):
        path = ROOT / "n8n/workflows/ch07-processor.json"
        workflow = json.loads(path.read_text(encoding="utf-8"))
        nodes = {node["name"]: node for node in workflow["nodes"]}
        self.assertEqual(nodes["Sub-workflow Input"]["parameters"]["inputSource"], "passthrough")
        for name, kind in (
            ("Any Eligible?", "if"),
            ("Split Records", "splitOut"),
            ("Filter Eligible", "filter"),
            ("Dedupe This Input", "removeDuplicates"),
            ("Sort Team and ID", "sort"),
            ("Aggregate Items", "aggregate"),
        ):
            self.assertEqual(nodes[name]["type"], f"n8n-nodes-base.{kind}")
        self.assertEqual(nodes["Dedupe This Input"]["parameters"]["fieldsToCompare"], "rows.id")

    def test_parent_waits_for_one_envelope_per_call(self):
        workflow = json.loads((ROOT / "n8n/workflows/ch07-parent.json").read_text(encoding="utf-8"))
        caller = next(node for node in workflow["nodes"] if node["name"] == "Process One Envelope")
        self.assertEqual(caller["parameters"]["mode"], "each")
        self.assertTrue(caller["parameters"]["options"]["waitForSubWorkflow"])
        self.assertEqual(caller["parameters"]["workflowId"]["value"], "ch07Processor")

    def test_batch_loop_has_explicit_return_edge(self):
        workflow = json.loads((ROOT / "n8n/workflows/ch07-batches.json").read_text(encoding="utf-8"))
        loop = next(node for node in workflow["nodes"] if node["name"] == "Loop Over Items")
        self.assertEqual(loop["parameters"]["batchSize"], 3)
        self.assertEqual(workflow["connections"]["Process Batch"]["main"][0][0]["node"], "Loop Over Items")

    def test_compose_is_local_and_has_no_default_secret(self):
        config = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:${N8N_PORT:-15681}", config)
        self.assertIn("127.0.0.1:${API_PORT:-18067}", config)
        self.assertIn("${POSTGRES_PASSWORD:?", config)
        self.assertNotIn("N8N_LICENSE", config)

    def test_env_generation_is_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            self.assertTrue(initialize(path))
            first = path.read_text(encoding="utf-8")
            self.assertFalse(initialize(path))
            self.assertEqual(first, path.read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
