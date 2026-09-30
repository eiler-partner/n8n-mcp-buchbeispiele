"""Contract tests for the synthetic API and its architecture cards."""

from __future__ import annotations

import copy
import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


LAB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB_DIR))
from api import LabServer  # noqa: E402
from validate_decisions import validate_cards  # noqa: E402


class LocalApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = LabServer(("127.0.0.1", 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path: str, *, payload: dict[str, str] | None = None) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_fixed_document_lookup(self) -> None:
        status, body = self.request("/documents/DOC-101")
        self.assertEqual(status, 200)
        self.assertEqual(body["version"], "3")
        self.assertEqual(body["classification"], "internal")

    def test_search_returns_versioned_snippet(self) -> None:
        status, body = self.request("/search?q=Freigabe")
        self.assertEqual(status, 200)
        self.assertEqual([hit["document_id"] for hit in body["hits"]], ["DOC-101"])
        self.assertEqual(body["hits"][0]["version"], "3")

    def test_search_rejects_empty_query(self) -> None:
        status, body = self.request("/search")
        self.assertEqual((status, body["error"]), (400, "invalid_query"))

    def test_write_is_only_a_synthetic_in_memory_record(self) -> None:
        status, body = self.request(
            "/approvals", payload={"document_id": "DOC-101", "decision": "approve"}
        )
        self.assertEqual(status, 201)
        self.assertTrue(body["simulation_only"])
        self.assertIn(body, [{**record, "simulation_only": True} for record in self.server.approvals])

    def test_invalid_write_does_not_change_state(self) -> None:
        count = len(self.server.approvals)
        status, body = self.request(
            "/approvals", payload={"document_id": "DOC-101", "decision": "publish"}
        )
        self.assertEqual((status, body["error"]), (400, "invalid_decision"))
        self.assertEqual(len(self.server.approvals), count)


class DecisionCardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cards = json.loads((LAB_DIR / "decisions.json").read_text(encoding="utf-8"))

    def test_sample_cards_are_complete(self) -> None:
        self.assertEqual(validate_cards(self.cards), [])

    def test_missing_boundary_is_rejected(self) -> None:
        broken = copy.deepcopy(self.cards)
        broken["cards"][1]["trust_boundaries"] = []
        self.assertTrue(any("trust_boundaries" in item for item in validate_cards(broken)))

    def test_unjustified_write_candidate_is_rejected(self) -> None:
        broken = copy.deepcopy(self.cards)
        broken["cards"][2]["decision"] = "mcp_candidate"
        self.assertTrue(any("write candidate" in item for item in validate_cards(broken)))

    def test_write_candidate_with_explicit_design_can_pass_structure(self) -> None:
        revised = copy.deepcopy(self.cards)
        write_card = revised["cards"][2]
        write_card["decision"] = "mcp_candidate"
        write_card["authorization_design"] = "Verify reviewer identity and object permissions"
        write_card["consent_design"] = "Require explicit user approval per document"
        self.assertEqual(validate_cards(revised), [])

    def test_bad_operation_type_is_rejected(self) -> None:
        broken = copy.deepcopy(self.cards)
        broken["cards"][0]["operation"] = ["get_document"]
        self.assertTrue(validate_cards(broken))


if __name__ == "__main__":
    unittest.main()
