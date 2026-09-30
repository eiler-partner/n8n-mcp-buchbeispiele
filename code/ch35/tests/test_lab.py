import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab import BY_ID, CASES, CORPUS, ContractError, answer, citation, context, validate_claims, visible


class Chapter35Tests(unittest.TestCase):
    def test_multidocument_answer(self):
        result = answer("urlaub")
        self.assertEqual(result["status"], "answered")
        self.assertEqual({c["citation"]["document_id"] for c in result["claims"]},
                         {"personalhandbuch", "freigabeprozess"})
        self.assertTrue(result["validation"]["accepted"])

    def test_scope_before_selection(self):
        selected = {s["chunk_id"] for s in context("urlaub")["selected"]}
        self.assertFalse(selected & {"urlaub-alt", "urlaub-entwurf", "urlaub-fremd", "hr-intern"})
        self.assertTrue(all(visible(BY_ID[ident], CASES["urlaub"]) for ident in selected))

    def test_duplicate_removed(self):
        self.assertNotIn("urlaub-kopie", {s["chunk_id"] for s in context("urlaub")["selected"]})

    def test_conflict_abstains(self):
        result = answer("konflikt")
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["conflicting_facts"], ["homeoffice_tage"])
        self.assertEqual(result["claims"], [])
        row = BY_ID["konflikt-a"]
        check = validate_claims("konflikt", [{"sentence": row["sentence"],
                                               "citation": citation(row)}])
        self.assertEqual(check["checks"][0]["reason"], "unresolved_source_conflict")

    def test_no_authorized_evidence(self):
        self.assertEqual(answer("hr-verweigert")["status"], "no_evidence")
        self.assertEqual(answer("hr-erlaubt")["status"], "answered")

    def test_budget(self):
        packed = context("urlaub", 100)
        self.assertLessEqual(packed["used_chars"], 100)
        with self.assertRaises(ContractError):
            context("urlaub", 79)
        with self.assertRaises(ContractError):
            context("urlaub", True)

    def test_missing_citation(self):
        self.assertFalse(validate_claims("urlaub", [{"sentence": "Beliebig."}])["accepted"])

    def test_fake_citation(self):
        claim = {"sentence": BY_ID["urlaub-regel"]["sentence"],
                 "citation": citation(BY_ID["urlaub-regel"])}
        claim["citation"]["chunk_id"] = "erfunden"
        self.assertEqual(validate_claims("urlaub", [claim])["checks"][0]["reason"],
                         "source_not_in_context")

    def test_modified_page_and_hash(self):
        claim = answer("urlaub")["claims"][0]
        for key, value in (("page", 99), ("sha256", "deadbeef")):
            altered = copy.deepcopy(claim)
            altered["citation"][key] = value
            self.assertEqual(validate_claims("urlaub", [altered])["checks"][0]["reason"],
                             "provenance_mismatch")

    def test_quote_and_sentence(self):
        claim = answer("urlaub")["claims"][0]
        altered = copy.deepcopy(claim)
        altered["citation"]["quote"] = "15 Kalendertage"
        self.assertEqual(validate_claims("urlaub", [altered])["checks"][0]["reason"], "quote_mismatch")
        altered = copy.deepcopy(claim)
        altered["sentence"] = "Es sind 5 Arbeitstage."
        self.assertEqual(validate_claims("urlaub", [altered])["checks"][0]["reason"],
                         "sentence_not_in_fixture_contract")

    def test_hard_negative_and_instruction(self):
        for ident in ("reise-hard-negative", "angriff"):
            row = BY_ID[ident]
            claim = {"sentence": row["sentence"], "citation": citation(row)}
            check = validate_claims("urlaub", [claim])["checks"][0]
            self.assertFalse(check["ok"])

    def test_unknown_case(self):
        with self.assertRaises(ContractError):
            answer("unknown")


if __name__ == "__main__":
    unittest.main()
