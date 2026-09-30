import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from email_lab import (  # noqa: E402
    ModelContractError, evaluate, live_classify, parse_model_output, rule_classify,
)


class EmailLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.emails = json.loads((ROOT / "emails.json").read_text(encoding="utf-8"))
        cls.fixtures = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))

    def test_dataset_is_unique_and_has_all_labels(self):
        self.assertEqual(len({mail["id"] for mail in self.emails}), len(self.emails))
        self.assertEqual({mail["expected"] for mail in self.emails},
                         {"rechnung", "support", "vertrieb", "unsicher"})

    def test_rule_baseline_exposes_priority_error(self):
        self.assertEqual(rule_classify(self.emails[3]).category, "rechnung")
        self.assertEqual(self.emails[3]["expected"], "support")

    def test_fixture_is_replay_not_performance_measurement(self):
        rules = evaluate(self.emails, "rules", "", self.fixtures)
        fixture = evaluate(self.emails, "fixture", "", self.fixtures)
        self.assertEqual((rules["total"], rules["correct"], rules["wrong"]), (12, 7, 2))
        self.assertEqual((fixture["total"], fixture["correct"], fixture["wrong"]), (12, 11, 1))
        self.assertEqual(fixture["contract_errors"], 0)

    def test_unknown_category_is_rejected(self):
        with self.assertRaisesRegex(ModelContractError, "Kategorie"):
            parse_model_output({"category": "zahlung", "evidence": "Rechnung",
                                "reason": "test"}, self.emails[0])

    def test_hallucinated_evidence_is_rejected(self):
        with self.assertRaisesRegex(ModelContractError, "nicht vor"):
            parse_model_output({"category": "rechnung", "evidence": "Geheimkonto",
                                "reason": "test"}, self.emails[0])

    def test_malformed_and_incomplete_outputs_are_rejected(self):
        with self.assertRaises(ModelContractError):
            parse_model_output("{", self.emails[0])
        with self.assertRaises(ModelContractError):
            parse_model_output({"category": "rechnung", "evidence": "Rechnung"}, self.emails[0])

    @patch("email_lab._post")
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test"})
    def test_openai_adapter_uses_structured_response(self, post):
        post.return_value = {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": json.dumps(self.fixtures["e01"])}]}]}
        self.assertEqual(live_classify("openai", "test-model", self.emails[0]).category,
                         "rechnung")
        self.assertTrue(post.call_args.args[1]["text"]["format"]["strict"])

    @patch("email_lab._post")
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"})
    def test_anthropic_adapter_uses_output_config(self, post):
        post.return_value = {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(self.fixtures["e01"])}]}
        self.assertEqual(live_classify("anthropic", "test-model", self.emails[0]).category,
                         "rechnung")
        self.assertEqual(post.call_args.args[1]["output_config"]["format"]["type"],
                         "json_schema")

    @patch("email_lab._post")
    def test_ollama_adapter_uses_json_schema(self, post):
        post.return_value = {"message": {"content": json.dumps(self.fixtures["e01"])}}
        self.assertEqual(live_classify("ollama", "test-model", self.emails[0]).category,
                         "rechnung")
        self.assertEqual(post.call_args.args[1]["format"]["type"], "object")


if __name__ == "__main__":
    unittest.main()
