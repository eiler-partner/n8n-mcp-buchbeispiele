import unittest

from core import inspect_trace, service_sli, synthetic_cost_micro_usd


def rows(correlation="a"*32, model_status="ok"):
    return [{"request_id": "r1", "correlation_id": correlation if stage != "model" else correlation,
             "stage": stage, "parent_stage": parent, "duration_ms": 2,
             "status": model_status if stage == "model" else "ok"}
            for stage, parent in [("n8n", None), ("mcp", "n8n"),
                                  ("retrieval", "mcp"), ("model", "mcp")]]


class ContractTests(unittest.TestCase):
    def test_complete(self):
        self.assertTrue(inspect_trace(rows(), "r1")["complete"])

    def test_lost_correlation(self):
        values = rows()
        values[-1]["correlation_id"] = None
        self.assertIn("correlation_broken", inspect_trace(values, "r1")["faults"])

    def test_missing_stage(self):
        self.assertIn("model_count_0", inspect_trace(rows()[:-1], "r1")["faults"])

    def test_wrong_parent(self):
        values = rows()
        values[-1]["parent_stage"] = "n8n"
        self.assertIn("model_parent_broken", inspect_trace(values, "r1")["faults"])

    def test_synthetic_cost(self):
        self.assertEqual(synthetic_cost_micro_usd(120, 30), 48)
        with self.assertRaises(ValueError):
            synthetic_cost_micro_usd(-1, 2)

    def test_sli_includes_business_error(self):
        self.assertEqual(service_sli([{"complete": True, "business_ok": True},
                                      {"complete": True, "business_ok": False}])["good"], 1)


if __name__ == "__main__":
    unittest.main()
