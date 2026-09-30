import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import (CASES, CORPUS, GATES, GOLDEN, VARIANTS, chunks,
                      evaluate_all, evaluate_case, evaluate_variant,
                      fixture_answer, retrieve, valid_citation)


class Chapter36Tests(unittest.TestCase):
    def test_four_variants_same_cases(self):
        report = evaluate_all()
        self.assertEqual(len(report["results"]), 4)
        self.assertEqual({row["variant"] for row in report["results"]},
                         {"short+lexical", "short+expanded", "wide+lexical", "wide+expanded"})
        self.assertTrue(all(len(row["cases"]) == len(GOLDEN) for row in report["results"]))

    def test_chunking_changes_units(self):
        case = CASES["vacation_deadline"]
        short = chunks("short", case)
        wide = chunks("wide", case)
        self.assertGreater(len(short), len(wide))
        self.assertEqual(len(next(row for row in wide if row["document_id"] == "personalhandbuch")["fact_ids"]), 2)

    def test_scope_before_top_k(self):
        for chunking, retrieval in VARIANTS:
            hits = retrieve(CASES["vacation_deadline"], chunking, retrieval, 10)
            docs = {hit["document_id"] for hit in hits}
            self.assertFalse(docs & {"hr-intern", "personalhandbuch-alt",
                                     "personalhandbuch-entwurf", "fremdhandbuch"})

    def test_alias_effect_not_model_semantics(self):
        case = CASES["abroad_alias"]
        self.assertFalse(retrieve(case, "short", "lexical"))
        self.assertIn("abroad_expenses", [fact for hit in retrieve(case, "short", "expanded")
                                           for fact in hit["fact_ids"]])

    def test_hard_negative_and_no_answer(self):
        result = evaluate_case(CASES["travel_hard_negative"], "short", "expanded")
        self.assertEqual(result["context_recall"], 1.0)
        for case_id in ("hr_denied", "unknown"):
            self.assertTrue(evaluate_case(CASES[case_id], "short", "expanded")["no_answer_correct"])

    def test_citation_tampering(self):
        hits = retrieve(CASES["vacation_deadline"], "short", "expanded")
        claim = fixture_answer(hits)[0]
        self.assertTrue(valid_citation(claim, hits))
        altered = copy.deepcopy(claim)
        altered["citation_chunk_id"] = "invented"
        self.assertFalse(valid_citation(altered, hits))
        altered = copy.deepcopy(claim)
        altered["sentence"] = "Eine erfundene Frist."
        self.assertFalse(valid_citation(altered, hits))

    def test_gate_separates_coverage_from_precision(self):
        short = evaluate_variant("short", "expanded")
        wide = evaluate_variant("wide", "expanded")
        self.assertEqual(short["release"], "pass")
        self.assertEqual(wide["metrics"]["context_recall"], 1.0)
        self.assertFalse(wide["gate_checks"]["answer_precision"])
        self.assertEqual(wide["release"], "hold")

    def test_missing_or_invalid_config_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown_chunking"):
            chunks("magic", CASES["vacation_deadline"])
        with self.assertRaisesRegex(ValueError, "unknown_retrieval"):
            retrieve(CASES["vacation_deadline"], "short", "magic")
        with self.assertRaisesRegex(ValueError, "invalid_top_k"):
            retrieve(CASES["vacation_deadline"], "short", "lexical", True)

    def test_fixed_gates_and_hashes(self):
        report = evaluate_all()
        self.assertEqual(report["gate_policy"], GATES)
        self.assertEqual(len(report["corpus_sha256"]), 64)
        self.assertEqual(len(report["golden_sha256"]), 64)
        self.assertEqual(len(report["evaluator_sha256"]), 64)
        self.assertEqual(len(report["aliases_sha256"]), 64)
        self.assertEqual(report["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
