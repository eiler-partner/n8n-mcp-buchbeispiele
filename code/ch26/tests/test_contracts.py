import copy
import json
import unittest
from unittest import mock

from ch26_lab.contracts import (compare_with_golden, evaluate_variant, full_report,
                                grade_case, load_registry, validate_output)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema, cls.cases, cls.fixtures, cls.prompts = load_registry()
        cls.case = cls.cases[0]
        cls.valid = cls.case["golden"]

    def check_error(self, value, expected):
        result = validate_output(value, self.case["text"], self.schema)
        self.assertFalse(result["contract_pass"])
        self.assertEqual(result["error_class"], expected)

    def test_report_and_version_hashes(self):
        report = full_report()
        self.assertEqual(report, full_report())
        self.assertTrue(report["release_ready"])
        self.assertEqual(report["baseline"]["contract_pass_count"], 6)
        self.assertEqual(report["baseline"]["golden_pass_count"], 5)
        self.assertEqual(report["candidate"]["contract_pass_count"], 8)
        self.assertEqual(report["candidate"]["golden_pass_count"], 8)
        self.assertEqual(report["baseline"]["exact_match_count"], 5)
        self.assertEqual(report["candidate"]["exact_match_count"], 8)
        self.assertEqual(report["golden_comparison"]["exact_fields"],
                         ["intent", "date", "needs_review"])
        self.assertNotEqual(report["baseline"]["prompt_sha256"], report["candidate"]["prompt_sha256"])

    def test_valid_json_and_golden(self):
        result = grade_case(self.case, json.dumps(self.valid), self.schema)
        self.assertTrue(result["contract_pass"] and result["golden_pass"])
        self.assertTrue(result["exact_match"])

    def test_other_verbatim_evidence_passes_golden(self):
        value = copy.deepcopy(self.valid)
        value["evidence"] = "am 2026-10-05"
        result = grade_case(self.case, value, self.schema)
        self.assertTrue(result["contract_pass"] and result["golden_pass"])
        self.assertFalse(result["exact_match"])
        self.assertIsNone(result["error_class"])

    def test_core_field_mismatch_fails_golden(self):
        for key, wrong in (("intent", "cancellation"), ("date", None)):
            with self.subTest(field=key):
                value = copy.deepcopy(self.valid)
                value[key] = wrong
                if key == "date":
                    value["needs_review"] = True
                result = grade_case(self.case, value, self.schema)
                self.assertTrue(result["contract_pass"])
                self.assertFalse(result["golden_pass"] or result["exact_match"])
                self.assertEqual(result["error_class"], "golden_mismatch")

    def test_golden_requires_verbatim_evidence(self):
        value = copy.deepcopy(self.valid)
        value["evidence"] = "Termin am 5. Oktober"
        self.assertFalse(compare_with_golden(value, self.case)["golden_pass"])

    def test_release_gate_is_fieldwise(self):
        fixtures = copy.deepcopy(self.fixtures)
        fixtures["candidate"]["c01"]["evidence"] = "am 2026-10-05"
        registry = (self.schema, self.cases, fixtures, self.prompts)
        with mock.patch("ch26_lab.contracts.load_registry", return_value=registry):
            report = full_report()
        self.assertTrue(report["release_ready"])
        self.assertEqual(report["candidate"]["golden_pass_count"], 8)
        self.assertEqual(report["candidate"]["exact_match_count"], 7)
        fixtures["candidate"]["c08"] = copy.deepcopy(self.fixtures["baseline"]["c08"])
        with mock.patch("ch26_lab.contracts.load_registry", return_value=registry):
            report = full_report()
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["candidate"]["golden_pass_count"], 7)

    def test_malformed_json(self):
        self.check_error('{"intent":', "json_syntax")

    def test_missing_required(self):
        value = copy.deepcopy(self.valid)
        value.pop("evidence")
        self.check_error(value, "schema")

    def test_wrong_type(self):
        value = copy.deepcopy(self.valid)
        value["needs_review"] = "false"
        self.check_error(value, "schema")

    def test_extra_field(self):
        value = copy.deepcopy(self.valid)
        value["approved"] = True
        self.check_error(value, "schema")

    def test_wrong_enum(self):
        value = copy.deepcopy(self.valid)
        value["intent"] = "booking"
        self.check_error(value, "schema")

    def test_invalid_date_format(self):
        value = copy.deepcopy(self.valid)
        value["date"] = "2026-13-99"
        self.check_error(value, "schema")

    def test_unanchored_evidence(self):
        value = copy.deepcopy(self.valid)
        value["evidence"] = "frei erfunden"
        self.check_error(value, "semantic_evidence")

    def test_date_not_in_input(self):
        value = copy.deepcopy(self.valid)
        value["date"] = "2026-10-06"
        self.check_error(value, "semantic_date")

    def test_date_check_is_plain_string_comparison(self):
        # Befund 26-F1: kein Normalisieren; alle Falltexte enthalten ISO-Daten.
        for case in self.cases:
            if case["golden"]["date"] is not None:
                self.assertIn(case["golden"]["date"], case["text"])
        value = {"intent": "appointment", "date": "2026-10-14",
                 "evidence": "Termin am 14. Oktober", "needs_review": False}
        result = validate_output(value, "Bitte einen Termin am 14. Oktober 2026.", self.schema)
        self.assertEqual(result["error_class"], "semantic_date")

    def test_review_invariant(self):
        value = copy.deepcopy(self.valid)
        value["needs_review"] = True
        self.check_error(value, "semantic_review")

    def test_information_invariant(self):
        value = copy.deepcopy(self.valid)
        value["intent"] = "information"
        self.check_error(value, "semantic_information")

    def test_schema_valid_but_golden_wrong(self):
        case = self.cases[7]
        result = grade_case(case, self.fixtures["baseline"][case["id"]], self.schema)
        self.assertTrue(result["contract_pass"])
        self.assertFalse(result["golden_pass"])
        self.assertFalse(result["exact_match"])
        self.assertEqual(result["error_class"], "golden_mismatch")

    def test_refusal_and_truncation(self):
        self.assertEqual(validate_output("", self.case["text"], self.schema, refusal=True)["error_class"], "refusal")
        self.assertEqual(validate_output("{}", self.case["text"], self.schema, truncated=True)["error_class"], "truncated")

    def test_unknown_variant(self):
        with self.assertRaises(ValueError):
            evaluate_variant("future")


if __name__ == "__main__":
    unittest.main()
