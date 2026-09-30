from __future__ import annotations

import unittest

from ch28_lab.core import CASES, ContractError, baseline, compare, review, route, work


def input_for(case_id="c01", tenant="lab"):
    return {"case_id": case_id, "tenant_id": tenant}


class ContractTests(unittest.TestCase):
    def assert_code(self, code, fn, value):
        with self.assertRaises(ContractError) as caught:
            fn(value)
        self.assertEqual(caught.exception.code, code)

    def test_all_baseline_and_multi_cases(self):
        for case in CASES.values():
            with self.subTest(case=case["id"]):
                simple = baseline(input_for(case["id"]))
                multi = review(work(route(input_for(case["id"]))))
                for value in (simple, multi):
                    self.assertEqual(value["status"], "accepted")
                    self.assertEqual(value["route"], case["expected_route"])
                    self.assertEqual(value["answer"], case["expected_answer"])

    def test_comparison_rejects_unneeded_roles(self):
        report = compare()
        self.assertEqual((report["baseline_pass"], report["multi_pass"]), (8, 8))
        self.assertEqual(report["decision"], "baseline")
        self.assertEqual((report["total_baseline_stages"],
                          report["total_multi_stages"]), (8, 24))

    def test_unknown_case(self):
        self.assert_code("unknown_case", baseline, input_for("c99"))

    def test_tenant_mismatch(self):
        self.assert_code("tenant_mismatch", route, input_for(tenant="other"))

    def test_extra_handoff_field(self):
        value = route(input_for())
        value["unexpected"] = "x"
        self.assert_code("handoff_shape", work, value)

    def test_context_tampering(self):
        value = route(input_for())
        value["context"] = "fremder Kontext"
        self.assert_code("context_mismatch", work, value)

    def test_context_budget(self):
        value = route(input_for())
        value["context"] = "x" * 300
        self.assert_code("context_budget", work, value)

    def test_trace_mismatch(self):
        value = route(input_for())
        value["trace_id"] = "forged"
        self.assert_code("trace_mismatch", work, value)

    def test_wrong_route(self):
        value = route(input_for("c03"))
        value["route"] = "billing"
        self.assert_code("route_mismatch", work, value)

    def test_route_must_be_string(self):
        value = route(input_for())
        value["route"] = ["billing"]
        self.assert_code("route_mismatch", work, value)

    def test_schema_version_must_be_integer(self):
        value = route(input_for())
        value["schema_version"] = True
        self.assert_code("handoff_version", work, value)

    def test_exhausted_budget(self):
        value = route(input_for())
        value["budget_remaining"] = 1
        self.assert_code("budget_exhausted", work, value)

    def test_wrong_evidence(self):
        value = work(route(input_for()))
        value["worker"]["source_id"] = "faq-1"
        self.assert_code("worker_result_mismatch", review, value)

    def test_wrong_answer(self):
        value = work(route(input_for()))
        value["worker"]["answer"] = "erfunden"
        self.assert_code("worker_result_mismatch", review, value)

    def test_worker_extra_field(self):
        value = work(route(input_for()))
        value["worker"]["reasoning"] = "geheim"
        self.assert_code("worker_shape", review, value)

    def test_review_shape(self):
        self.assert_code("review_shape", review, {"worker": {}})


if __name__ == "__main__":
    unittest.main()
