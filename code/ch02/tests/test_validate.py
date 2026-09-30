import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate import validate  # noqa: E402


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads((ROOT / "architecture.json").read_text(encoding="utf-8"))

    def changed(self):
        return copy.deepcopy(self.baseline)

    def test_baseline(self):
        self.assertEqual(validate(self.baseline), [])

    def test_missing_contract(self):
        case = self.changed()
        case["flows"][0]["contract"] = ""
        self.assertTrue(any("contract" in error for error in validate(case)))

    def test_unknown_endpoint(self):
        case = self.changed()
        case["flows"][0]["to"] = "nowhere"
        self.assertTrue(any("Endpunkt" in error for error in validate(case)))

    def test_confidential_data_to_provider(self):
        case = self.changed()
        case["flows"][3]["classification"] = "confidential"
        self.assertTrue(any("Rohdaten" in error for error in validate(case)))

    def test_write_without_approval(self):
        case = self.changed()
        case["flows"][-1]["approval"] = False
        self.assertTrue(any("Freigabe" in error for error in validate(case)))

    def test_model_directly_writes(self):
        case = self.changed()
        case["flows"][-1]["from"] = "model"
        self.assertTrue(any("direkt schreiben" in error for error in validate(case)))

    def test_requester_cannot_directly_publish(self):
        case = self.changed()
        case["flows"][-1]["from"] = "requester"
        self.assertTrue(any("nur ueber Pruefdienst" in error for error in validate(case)))

    def test_duplicate_id(self):
        case = self.changed()
        case["components"][1]["id"] = "requester"
        self.assertTrue(any("doppelt" in error for error in validate(case)))

    def test_missing_owner(self):
        case = self.changed()
        case["components"][0]["owner"] = ""
        self.assertTrue(any("owner" in error for error in validate(case)))


if __name__ == "__main__":
    unittest.main()
