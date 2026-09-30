import copy
import unittest

from decide import all_decisions, decide, profiles
from mcp_stdio import handle

META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}


class DecisionTests(unittest.TestCase):
    def test_three_profiles(self):
        result = all_decisions()
        self.assertEqual([item["selected"] for item in result["decisions"]],
                         ["cloud", "self_hosted", "hybrid"])
        self.assertEqual(len(result["dataset_sha256"]), 64)

    def test_local_requirement_is_hard_gate(self):
        row = decide(profiles()["interne_akte"])
        self.assertFalse(row["candidates"][0]["eligible"])
        self.assertIsNone(row["candidates"][0]["score"])

    def test_no_ops_team_rejects_owned_runtime(self):
        row = decide(profiles()["kleines_team"])
        self.assertFalse(row["candidates"][1]["eligible"])

    def test_no_split_approval_rejects_hybrid(self):
        profile = copy.deepcopy(profiles()["geteilte_ki"])
        profile["external_model_approved"] = False
        self.assertEqual(decide(profile)["selected"], "self_hosted")

    def test_community_multi_main_is_not_assumed(self):
        profile = copy.deepcopy(profiles()["interne_akte"])
        profile["requires_multi_main"] = True
        row = decide(profile)
        self.assertEqual(row["status"], "needs_clarification")
        self.assertEqual(row["candidates"][1]["score"], None)

    def test_third_party_hosting_halts_for_license(self):
        profile = copy.deepcopy(profiles()["kleines_team"])
        profile["third_party_hosting"] = True
        self.assertEqual(decide(profile)["status"], "needs_clarification")

    def test_boolean_as_weight_rejected(self):
        profile = copy.deepcopy(profiles()["kleines_team"])
        profile["weights"]["operability"] = True
        with self.assertRaisesRegex(ValueError, "invalid_weight_range"):
            decide(profile)

    def test_unknown_field_rejected(self):
        profile = copy.deepcopy(profiles()["kleines_team"])
        profile["secret"] = "not-for-report"
        with self.assertRaisesRegex(ValueError, "invalid_profile_fields"):
            decide(profile)

    def test_stable_hash_and_terms(self):
        first = decide(profiles()["geteilte_ki"])
        self.assertEqual(first, decide(profiles()["geteilte_ki"]))
        self.assertEqual(first["candidates"][2]["score"], sum(first["candidates"][2]["weighted_terms"].values()))

    def test_tie_needs_human_clarification(self):
        profile = copy.deepcopy(profiles()["kleines_team"])
        profile["ops_team"] = True
        profile["weights"] = {"operability": 2, "data_control": 1,
                              "model_access": 1, "portability": 1,
                              "cost_predictability": 2}
        result = decide(profile)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["tied"], ["cloud", "self_hosted"])

    def test_mcp_tool_contract(self):
        listed = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}})
        self.assertEqual(listed["result"]["tools"][0]["name"], "decide_architecture")
        called = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"_meta": META, "name": "decide_architecture", "arguments": {"profile_id": "kleines_team"}}})
        self.assertEqual(__import__("json").loads(called["result"]["content"][0]["text"])["selected"], "cloud")


if __name__ == "__main__":
    unittest.main()
