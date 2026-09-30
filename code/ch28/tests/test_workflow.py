"""Struktur des n8n-Workflows: Fehlerausgang und Testschalter der Mehrstufenkette."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from ch28_lab.core import ContractError, review, route, work

WORKFLOW = json.loads(
    (Path(__file__).resolve().parents[1] / "n8n/ch28-compare.json").read_text(encoding="utf-8"))
NODES = {node["name"]: node for node in WORKFLOW["nodes"]}
STAGES = ("Router", "Specialist Worker", "Contract Reviewer")
REJECTION = "Return Stage Rejection"


class WorkflowTests(unittest.TestCase):
    def test_ids_names_and_connections_are_consistent(self):
        ids = [node["id"] for node in WORKFLOW["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(NODES), len(WORKFLOW["nodes"]))
        for source, outputs in WORKFLOW["connections"].items():
            self.assertIn(source, NODES)
            for branch in outputs["main"]:
                for target in branch:
                    self.assertIn(target["node"], NODES)

    def test_only_existing_node_types_and_versions(self):
        self.assertEqual({(node["type"], node["typeVersion"]) for node in WORKFLOW["nodes"]}, {
            ("n8n-nodes-base.webhook", 2.1),
            ("n8n-nodes-base.httpRequest", 4.4),
            ("n8n-nodes-base.respondToWebhook", 1.4),
        })

    def test_each_stage_rejection_reaches_the_caller(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(NODES[stage].get("onError"), "continueErrorOutput")
                _, error_output = WORKFLOW["connections"][stage]["main"]
                self.assertEqual([target["node"] for target in error_output], [REJECTION])
        rejection = NODES[REJECTION]["parameters"]
        self.assertEqual(rejection["options"]["responseCode"], 422)
        self.assertIn("rejected_by: $prevNode.name", rejection["responseBody"])
        self.assertIn("detail: $json.error.message", rejection["responseBody"])
        self.assertNotIn("onError", NODES["Single Deterministic Worker"])

    def test_expressions_are_single_templates(self):
        for node in WORKFLOW["nodes"]:
            for key in ("body", "responseBody"):
                value = node["parameters"].get(key)
                if value:
                    with self.subTest(node=node["name"]):
                        self.assertTrue(value.startswith("={{ ") and value.endswith(" }}"))
                        self.assertEqual((value.count("{{"), value.count("}}")), (1, 1))

    def test_tamper_switch_is_rejected_by_the_named_stage(self):
        worker_body = NODES["Specialist Worker"]["parameters"]["body"]
        reviewer_body = NODES["Contract Reviewer"]["parameters"]["body"]
        self.assertIn("query.tamper === 'context'", worker_body)
        self.assertIn("query.tamper === 'answer'", reviewer_body)
        self.assertEqual(NODES["Router"]["parameters"]["body"], "={{ JSON.stringify($json.body) }}")
        context = re.search(r"context: '([^']*)'", worker_body).group(1)
        answer = re.search(r"answer: '([^']*)'", reviewer_body).group(1)
        handoff = route({"case_id": "c01", "tenant_id": "lab"})
        with self.assertRaises(ContractError) as caught:
            work(dict(handoff, context=context))
        self.assertEqual(caught.exception.code, "context_mismatch")
        result = work(handoff)
        result["worker"]["answer"] = answer
        with self.assertRaises(ContractError) as caught:
            review(result)
        self.assertEqual(caught.exception.code, "worker_result_mismatch")


if __name__ == "__main__":
    unittest.main()
