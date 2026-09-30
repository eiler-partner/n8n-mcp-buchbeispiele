import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_workflows import workflow
from review_contract import audit, canonical_json


class ReviewContractTest(unittest.TestCase):
    def test_checked_in_artifacts_match_generator(self):
        for name, threshold in (("ch11-baseline.json", 80), ("ch11-candidate.json", 70)):
            actual = json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8"))
            self.assertEqual(actual, workflow(threshold))

    def test_diff_changes_only_the_reviewed_rule(self):
        before = canonical_json(workflow(80))
        after = canonical_json(workflow(70))
        self.assertNotEqual(before, after)
        self.assertIn("score >= 80", before)
        self.assertIn("score >= 70", after)

    def test_export_metadata_does_not_change_review_text(self):
        exported = {**workflow(80), "createdAt": "different", "updatedAt": "different"}
        self.assertEqual(canonical_json(exported), canonical_json(workflow(80)))

    def test_credentials_or_auth_header_are_not_shareable(self):
        with_credentials = workflow(80)
        with_credentials["nodes"][1]["credentials"] = {"someApi": {"name": "Customer Production"}}
        with self.assertRaises(ValueError):
            audit(with_credentials)
        with_header = workflow(80)
        with_header["nodes"][1]["parameters"]["headerParameters"] = {
            "parameters": [{"name": "Authorization", "value": "Bearer example"}]
        }
        with self.assertRaises(ValueError):
            audit(with_header)

    def test_reject_unreviewed_multiple_workflows(self):
        with self.assertRaises(ValueError):
            canonical_json([workflow(80), workflow(70)])


if __name__ == "__main__":
    unittest.main()
