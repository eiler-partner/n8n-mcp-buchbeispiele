import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ch25_lab.cli import choose  # noqa: E402
from ch25_lab.selection import SelectionError, evaluate, fallback, full_report, load_data  # noqa: E402


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.profiles, cls.scenarios = load_data()

    def test_reproducible_report(self):
        report = full_report()
        self.assertEqual(report, full_report())
        self.assertEqual(len(self.cases), 12)
        self.assertEqual(
            report["scenarios"]["lokal-qualitaet"]["dataset_sha256"],
            "dbe9f3216f0251f25370d33cae7d5b4830fc07cf868cebe52cace8a1b3e49b7e",
        )
        self.assertEqual(report["scenarios"]["lokal-qualitaet"]["ranked_candidates"][0]["score"], 0.87)

    def test_quality_selects_precise_and_excludes_external(self):
        report = choose("lokal-qualitaet")
        self.assertEqual(report["selected"], "praezise-lokal")
        self.assertIn({"profile": "extern-variabel", "reason": "datenweg"}, report["excluded"])

    def test_cost_selects_economical(self):
        self.assertEqual(choose("lokal-kosten")["selected"], "sparsam-lokal")

    def test_selected_fixture_invocation(self):
        report = choose("lokal-qualitaet", case_id="e01")
        self.assertEqual(report["fixture_invocation"]["observed"], "hinweis")
        with self.assertRaises(SelectionError):
            choose("tool-lokal", case_id="c01")

    def test_tool_requires_capability(self):
        report = choose("tool-lokal")
        self.assertEqual(report["selected"], "praezise-lokal")
        self.assertIn({"profile": "sparsam-lokal", "reason": "fähigkeit"}, report["excluded"])

    def test_timeout_fallback_only_to_compatible(self):
        report = choose("lokal-qualitaet", "timeout")
        self.assertEqual(report["selected"], "sparsam-lokal")
        with self.assertRaises(SelectionError):
            choose("tool-lokal", "timeout")

    def test_policy_failure_not_fallback(self):
        with self.assertRaises(SelectionError):
            choose("lokal-qualitaet", "policy")

    def test_budget_fail_closed(self):
        scenarios = copy.deepcopy(self.scenarios)
        scenarios["lokal-qualitaet"]["max_cost_units"] = 0.1
        report = evaluate("lokal-qualitaet", self.cases, self.profiles, scenarios)
        self.assertIsNone(report["selected"])

    def test_missing_measurement_fails(self):
        profiles = copy.deepcopy(self.profiles)
        profiles[1]["outputs"].pop("c01")
        with self.assertRaisesRegex(SelectionError, "Messwerte fehlen"):
            evaluate("lokal-qualitaet", self.cases, profiles, self.scenarios)

    def test_invalid_weights_fail(self):
        scenarios = copy.deepcopy(self.scenarios)
        scenarios["lokal-qualitaet"]["weights"]["quality"] = 0.9
        with self.assertRaisesRegex(SelectionError, "zusammen 1"):
            evaluate("lokal-qualitaet", self.cases, self.profiles, scenarios)

    def test_unknown_scenario_fails(self):
        with self.assertRaises(SelectionError):
            choose("unbekannt")


if __name__ == "__main__":
    unittest.main()
