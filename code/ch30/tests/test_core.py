import unittest

from ch30_lab.core import ContractError, answer, authorized, compare, retrieve
from ch30_lab.mcp_stdio import handle


class Chapter30Contract(unittest.TestCase):
    def setUp(self):
        self.request = {"question_tag": "urlaub", "tenant": "werk", "role": "employee", "as_of": "2026-09-29"}

    def test_three_strategies(self):
        rows = compare(self.request)["results"]
        self.assertFalse(rows[0]["accepted"])
        self.assertEqual(rows[1]["answer"], "Mindestens 15 Arbeitstage vor Beginn.")
        self.assertEqual(rows[2]["answer"], rows[1]["answer"])
        self.assertLess(rows[2]["context_chars"], rows[1]["context_chars"])
        self.assertEqual(rows[2]["citations"][0]["version"], 2)

    def test_old_deleted_and_foreign_excluded(self):
        ids = [row["chunk_id"] for row in authorized(self.request)]
        self.assertIn("leave-v2-a", ids)
        self.assertNotIn("leave-v1-a", ids)
        self.assertNotIn("leave-v3-deleted", ids)
        self.assertNotIn("other-leave-v1", ids)
        self.assertNotIn("salary-v1-a", ids)

    def test_time_travel(self):
        request = self.request | {"as_of": "2025-09-29", "strategy": "rag"}
        self.assertEqual(answer(retrieve(request))["citations"][0]["version"], 1)

    def test_no_evidence_withheld(self):
        request = self.request | {"question_tag": "gehalt", "strategy": "rag"}
        self.assertEqual(answer(retrieve(request))["status"], "withheld")
        self.assertEqual(answer(retrieve(request))["citations"], [])

    def test_unknown_question_withheld(self):
        request = self.request | {"question_tag": "unbekannt", "strategy": "rag"}
        self.assertEqual(answer(retrieve(request))["reason"], "no_authorized_evidence")

    def test_authorized_hr(self):
        request = self.request | {"question_tag": "gehalt", "role": "hr", "strategy": "rag"}
        self.assertEqual(answer(retrieve(request))["answer"], "Im November.")

    def test_tampered_evidence_rejected(self):
        envelope = retrieve(self.request | {"strategy": "rag"})
        envelope["evidence"][0]["text"] = "Manipuliert"
        with self.assertRaisesRegex(ContractError, "evidence_mismatch"):
            answer(envelope)

    def test_invalid_request(self):
        with self.assertRaisesRegex(ContractError, "unknown_scope"):
            retrieve(self.request | {"tenant": "x", "strategy": "rag"})

    def test_mcp_resources_scope(self):
        meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
        listing = handle({"id": 1, "method": "resources/list", "params": {"_meta": meta}}, "werk", "employee")
        uris = [r["uri"] for r in listing["result"]["resources"]]
        self.assertTrue(any("leave-v2-a" in u for u in uris))
        self.assertFalse(any("salary" in u or "deleted" in u or "fremd" in u for u in uris))
        reading = handle({"id": 2, "method": "resources/read", "params": {"_meta": meta, "uri": uris[0]}}, "werk", "employee")
        self.assertIn("text", reading["result"]["contents"][0])
        denied = handle({"id": 3, "method": "resources/read", "params": {"_meta": meta, "uri": "rag://werk/salary-policy/1/salary-v1-a"}}, "werk", "employee")
        self.assertEqual(denied["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
