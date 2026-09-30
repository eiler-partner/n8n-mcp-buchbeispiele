from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from case_service import connect, issue_token, safe_dispatch, verify_audit
from core import local_report, parse_document, read_resource, validate_catalog
from mcp_stdio import handle


class CoreTests(unittest.TestCase):
    def test_four_statuses_conflict_and_evidence(self):
        report = local_report()
        self.assertEqual({c["control_id"]: c["status"] for c in report["controls"]}, {
            "C01": "fulfilled", "C02": "partial", "C03": "not_evidenced",
            "C04": "not_applicable", "C05": "fulfilled", "C06": "partial"})
        self.assertEqual(report["open_control_ids"], ["C02", "C03", "C04", "C06"])
        self.assertIn("contradictory_documents", report["controls"][5]["flags"])
        self.assertFalse(report["controls"][2]["evidence"])
        self.assertTrue(all(len(e["raw_sha256"]) == 64 and "Ziff." in e["locator"]
                            for control in report["controls"] for e in control["evidence"]))

    def test_resource_versions_and_unknown_uri(self):
        request = lambda method, params: handle({"jsonrpc": "2.0", "id": 1, "method": method,
            "params": {**params, "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}})
        resources = request("resources/list", {})["result"]["resources"]
        self.assertEqual(len(resources), 4)
        self.assertEqual(request("resources/read", {"uri": "catalog://supplier-review/v2"})
                         ["result"]["contents"][0]["uri"], "catalog://supplier-review/v2")
        self.assertEqual(request("resources/read", {"uri": "file:///etc/passwd"})
                         ["error"]["code"], -32602)
        self.assertNotEqual(local_report("catalog://supplier-review/v1")["catalog_sha256"],
                            local_report("catalog://supplier-review/v2")["catalog_sha256"])

    def test_document_parser_rejects_unstructured_and_duplicate_locator(self):
        original = Path(__file__).parents[1].joinpath("data/supplier-profile.md").read_bytes()
        self.assertEqual(parse_document(original)["document_id"], "supplier-profile")
        with self.assertRaisesRegex(ValueError, "unstructured_document_line"):
            parse_document(original + b"\nfree prose\n")
        with self.assertRaisesRegex(ValueError, "duplicate_locator"):
            parse_document(original + b"\n- Ziffer 1: duplicate\n")

    def test_source_mapping_is_marked_unvalidated(self):
        sources = json.loads(Path(__file__).parents[1].joinpath("data/regulatory-sources.json")
                             .read_text())["sources"]
        self.assertTrue(all(s["mapping_status"] == "unvalidated_illustrative_reference"
                            for s in sources))
        with self.assertRaisesRegex(ValueError, "resource_not_allowlisted"):
            read_resource("catalog://supplier-review/latest")

    def test_missing_regulatory_locator_fails_catalog(self):
        catalog = json.loads(read_resource("catalog://supplier-review/v1"))
        catalog["controls"][0]["source_locator"] = "Art. 999"
        sources = {"sources": json.loads(Path(__file__).parents[1]
                           .joinpath("data/regulatory-sources.json").read_text())["sources"]}
        with self.assertRaisesRegex(ValueError, "regulatory_source_unversioned_or_missing"):
            validate_catalog(catalog, sources)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.old_key = os.environ.get("CH45_SIGNING_KEY")
        os.environ["CH45_SIGNING_KEY"] = "local-fixture-signing-key-45-at-least-32-characters"
        self.folder = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.folder.name) / "cases.sqlite")
        self.requester = issue_token("alice", "requester")
        self.reviewer = issue_token("bob", "reviewer")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()
        if self.old_key is None:
            os.environ.pop("CH45_SIGNING_KEY", None)
        else:
            os.environ["CH45_SIGNING_KEY"] = self.old_key

    def call(self, payload):
        return safe_dispatch(payload, self.db)

    def start(self):
        case = self.call({"action": "start", "requester_token": self.requester})
        self.assertTrue(case["ok"], case)
        return case

    def review(self, case, token=None, decision="approve", accepted=None):
        report = case["report"]
        return {"action": "review", "case_id": case["case_id"],
                "reviewer_token": token or self.reviewer, "decision": decision,
                "comment": "Synthetische Befunde zur manuellen Sichtung übernommen.",
                "accepted_open_ids": report["open_control_ids"] if accepted is None else accepted,
                "report_sha256": report["report_sha256"],
                "catalog_sha256": report["catalog_sha256"],
                "document_set_sha256": report["document_set_sha256"]}

    def test_valid_gate_and_replay(self):
        case = self.start()
        before = self.call({"action": "export", "case_id": case["case_id"],
                            "requester_token": self.requester})
        self.assertEqual(before["code"], "export_requires_approval")
        self.assertEqual(self.call(self.review(case))["status"], "approved")
        exported = self.call({"action": "export", "case_id": case["case_id"],
                              "requester_token": self.requester})
        self.assertEqual(exported["status"], "exported")
        self.assertEqual(exported["artifact"]["kind"],
                         "human_reviewed_synthetic_assessment_not_legal_certificate")
        self.assertEqual(self.call({"action": "export", "case_id": case["case_id"],
                                    "requester_token": self.requester})["code"],
                         "export_requires_approval")

    def test_self_approval_stale_and_missing_findings(self):
        case = self.start()
        self.assertEqual(self.call(self.review(case, issue_token("alice", "reviewer")))["code"],
                         "self_approval_forbidden")
        stale = self.review(case)
        stale["document_set_sha256"] = "0" * 64
        self.assertEqual(self.call(stale)["code"], "stale_review_basis")
        self.assertEqual(self.call(self.review(case, accepted=["C02"]))["code"],
                         "open_findings_not_acknowledged")
        self.assertEqual(self.call({"action": "inspect", "case_id": case["case_id"],
                                    "requester_token": self.requester})["status"], "draft")

    def test_rejection_and_audit_tampering(self):
        case = self.start()
        self.assertEqual(self.call(self.review(case, decision="reject", accepted=[]))["status"],
                         "rejected")
        self.assertEqual(self.call({"action": "export", "case_id": case["case_id"],
                                    "requester_token": self.requester})["code"],
                         "export_requires_approval")
        case2 = self.start()
        self.assertEqual(self.call(self.review(case2))["status"], "approved")
        self.db.execute("UPDATE audit SET event_json='{}' WHERE case_id=? AND seq=1",
                        (case2["case_id"],))
        self.db.commit()
        self.assertEqual(self.call({"action": "export", "case_id": case2["case_id"],
                                    "requester_token": self.requester})["code"],
                         "audit_integrity_failed")

    def test_stored_report_tampering_is_not_exported(self):
        case = self.start()
        self.assertEqual(self.call(self.review(case))["status"], "approved")
        changed = case["report"].copy()
        changed["result_kind"] = "forged_certificate"
        self.db.execute("UPDATE cases SET report_json=? WHERE id=?",
                        (json.dumps(changed), case["case_id"]))
        self.db.commit()
        self.assertEqual(self.call({"action": "export", "case_id": case["case_id"],
                                    "requester_token": self.requester})["code"],
                         "catalog_or_document_changed")

    def test_document_change_after_draft_stops_review(self):
        case = self.start()
        data = Path(__file__).parents[1] / "data"
        changed = Path(self.folder.name) / "changed.md"
        changed.write_text((data / "supplier-profile.md").read_text().replace("täglich", "wöchentlich"))
        with patch("core.DOCUMENT_FILES", (changed, data / "supplier-contract.md")):
            self.assertEqual(self.call(self.review(case))["code"],
                             "catalog_or_document_changed")

    def test_bad_token_and_unknown_catalog(self):
        self.assertEqual(self.call({"action": "start", "requester_token": "broken"})["code"],
                         "invalid_or_expired_token")
        self.assertEqual(self.call({"action": "start", "requester_token": self.requester,
                                    "catalog_uri": "catalog://supplier-review/latest"})["code"],
                         "catalog_not_allowlisted")


if __name__ == "__main__":
    unittest.main()
