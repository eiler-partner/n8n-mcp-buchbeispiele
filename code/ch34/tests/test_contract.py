import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab
from lab import (CASES, CORPUS, MODES, ContractError, evaluate, measures, retrieve,
                 rrf, validate_fixture, version_at, visible)


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


FAKE_PSYCOPG = types.SimpleNamespace(connect=lambda dsn: _Connection())


def hit(chunk_id, score):
    return {"id": chunk_id, "text": "t", "text_sha256": "h", "score": score}


# Simulierte Zweiglisten für rkk-frist; echte FTS-Ergebnisse liefert erst der Live-Lauf.
SIMULATED = {("rkk-frist", False): [],
             ("rkk-frist", True): [hit("v2-travel", 0.5)]}
DENSE = [hit("v2-travel", 0.99), hit("v2-travel-proof", 0.98)]


class RetrievalContractTests(unittest.TestCase):
    def test_fixture_scope(self):
        validate_fixture()
        employee = CASES["vacation-frist"]
        ids = {r["id"] for r in CORPUS if visible(r, employee)}
        self.assertIn("v2-vacation", ids)
        self.assertNotIn("v1-vacation", ids)
        self.assertNotIn("v2-hr", ids)
        self.assertNotIn("v2-draft-hard-negative", ids)
        self.assertNotIn("v2-other-tenant", ids)
        self.assertEqual(version_at("2026-08-31"), "2026-01")
        with self.assertRaises(ContractError):
            version_at("2026-10-01")

    def test_rrf_uses_ranks_not_raw_scores(self):
        one = [{"id": "a", "score": 100.0}, {"id": "b", "score": 1.0}]
        two = [{"id": "b", "score": 0.01}, {"id": "a", "score": 0.001}]
        fused = rrf([one, two])
        self.assertEqual([r["id"] for r in fused], ["a", "b"])
        self.assertAlmostEqual(fused[0]["score"], 1/61 + 1/62)
        with self.assertRaises(ContractError):
            rrf([[one[0], one[0]]])

    def test_precision_recall_and_no_answer(self):
        self.assertEqual(measures(["a", "x", "b"], ["a", "b"]),
                         {"precision_at_k": 0.666667, "recall_at_k": 1.0,
                          "false_positive_count": None})
        self.assertEqual(measures(["x"], []),
                         {"precision_at_k": None, "recall_at_k": None,
                          "false_positive_count": 1})


class ExpansionModeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def lexical(conn, case, expanded):
            self.calls.append(("lexical", case["id"], expanded))
            return list(SIMULATED.get((case["id"], expanded), []))

        def dense(conn, case):
            self.calls.append(("dense", case["id"]))
            return list(DENSE)

        for patcher in (mock.patch.dict(sys.modules, {"psycopg": FAKE_PSYCOPG}),
                        mock.patch.object(lab, "_lexical", lexical),
                        mock.patch.object(lab, "_dense", dense)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_modes_and_mcp_schema(self):
        self.assertEqual(MODES, ("lexical", "lexical_expanded", "dense",
                                 "hybrid", "hybrid_expanded"))
        import mcp_stdio
        listed = mcp_stdio.handle({"id": 1, "method": "tools/list", "params": {
            "_meta": {"io.modelcontextprotocol/protocolVersion": mcp_stdio.VERSION}}})
        schema = listed["result"]["tools"][0]["inputSchema"]
        self.assertEqual(schema["properties"]["mode"]["enum"], list(MODES))

    def test_fts_branch_with_and_without_expansion(self):
        plain = retrieve("rkk-frist", "lexical")
        expanded = retrieve("rkk-frist", "lexical_expanded")
        self.assertEqual(self.calls, [("lexical", "rkk-frist", False),
                                      ("lexical", "rkk-frist", True)])
        self.assertEqual(plain["hits"], [])
        self.assertEqual([h["id"] for h in expanded["hits"]], ["v2-travel"])
        self.assertEqual(expanded["hits"][0]["score"], 0.5)  # FTS-Score, kein RRF-Wert
        self.assertEqual(expanded["metrics"], {"precision_at_k": 0.333333,
                                               "recall_at_k": 1.0,
                                               "false_positive_count": None})

    def test_fusion_hides_repaired_fts_branch(self):
        hybrid = retrieve("rkk-frist", "hybrid")
        expanded = retrieve("rkk-frist", "hybrid_expanded")
        self.assertEqual([h["id"] for h in hybrid["hits"]],
                         [h["id"] for h in expanded["hits"]])
        self.assertEqual(hybrid["metrics"], expanded["metrics"])
        self.assertAlmostEqual(hybrid["hits"][0]["score"], 1 / 61)
        self.assertAlmostEqual(expanded["hits"][0]["score"], 2 / 61)

    def test_evaluate_covers_all_modes(self):
        report = evaluate()
        self.assertEqual(len(report["cases"]), 35)
        self.assertEqual(len(report["cases"]), len(CASES) * len(MODES))
        self.assertEqual(set(report["summary"]), set(MODES))


class RkkFixtureTests(unittest.TestCase):
    def test_short_code_absent_expanded_term_present(self):
        case = CASES["rkk-frist"]
        scope = [r for r in CORPUS if visible(r, case)]
        self.assertIn("RKK", case["lexical_query"])
        self.assertIn("Reisekostenbelege", case["expanded_query"])
        self.assertFalse([r["id"] for r in scope if "rkk" in r["text"].lower()])
        self.assertEqual([r["id"] for r in scope if "Reisekostenbelege" in r["text"]],
                         ["v2-travel"])


if __name__ == "__main__":
    unittest.main()
