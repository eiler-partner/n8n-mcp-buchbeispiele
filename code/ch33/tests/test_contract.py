import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab
from lab import (ContractError, DATA, PG_ORDER_BY, QDRANT_TIE_MARGIN, SPACES,
                 query, tie_order, validate_query, vector_for, version_at)


class FakeQdrant:
    """Liefert Punkte wie Qdrant: nur `limit` Stück, Gleichstände in beliebiger Reihenfolge."""

    def __init__(self, points):
        self.points = points
        self.limits = []
        self.bodies = []

    def __call__(self, method, path, body=None):
        self.limits.append(body["limit"])
        self.bodies.append(body)
        return {"result": {"points": self.points[:body["limit"]]}}


def point(chunk_id, score):
    return {"score": score, "payload": {
        "chunk_id": chunk_id, "section_id": "s", "audience": "all",
        "version_id": "2026-09", "text_sha256": "h", "text": "t"}}


class ContractTests(unittest.TestCase):
    def test_version_intervals(self):
        self.assertEqual(version_at("2026-08-31"), "2026-01")
        self.assertEqual(version_at("2026-09-01"), "2026-09")
        for day in ("2026-10-01", "2026-02-30"):
            with self.assertRaises(ContractError):
                version_at(day)

    def test_dimensions_and_scope(self):
        base = {"store": "pgvector", "model_id": "fixture-v1", "vector": [1, 0, 0, 0],
                "tenant_id": "buchlabor", "role": "employee", "as_of": "2026-09-29"}
        self.assertEqual(validate_query(base)[0], 4)
        for field, value in (("vector", [1, 0]), ("vector", [0, 0, 0, 0]),
                             ("tenant_id", "fremd"), ("role", "admin"),
                             ("model_id", "unknown"), ("store", "unknown")):
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                validate_query({**base, field: value})

    def test_corpus_and_vectors(self):
        self.assertEqual(len(DATA["chunks"]), 8)
        self.assertEqual(len({r["chunk_id"] for r in DATA["chunks"]}), 8)
        for model, (dim, _, _) in SPACES.items():
            self.assertTrue(all(len(vector_for(r, model)) == dim for r in DATA["chunks"]))
        self.assertEqual({r["audience"] for r in DATA["chunks"]}, {"all", "hr"})


class TieBreakTests(unittest.TestCase):
    QUERY = {"store": "qdrant", "model_id": "fixture-v1", "vector": [1.0, 1.0, 0.1, 0.1],
             "tenant_id": "buchlabor", "role": "employee", "as_of": "2026-09-29"}

    def test_same_rule_as_sql(self):
        self.assertEqual(PG_ORDER_BY, 'ORDER BY distance, chunk_id COLLATE "C"')
        hits = [{"chunk_id": "v2-vacation", "score": 0.8},
                {"chunk_id": "v2-scope", "score": 0.5},
                {"chunk_id": "v2-travel", "score": 0.8}]
        self.assertEqual([h["chunk_id"] for h in tie_order(hits)],
                         ["v2-travel", "v2-vacation", "v2-scope"])
        # Bytereihenfolge wie COLLATE "C", nicht sprachabhängig: "-" < "0" < "A" < "a"
        self.assertEqual([h["chunk_id"] for h in tie_order(
            [{"chunk_id": c, "score": 1.0} for c in ("v1a", "v10", "V1", "v1-a")])],
            ["V1", "v1-a", "v10", "v1a"])

    def test_qdrant_equal_scores_sorted_by_chunk_id(self):
        fake = FakeQdrant([point("v2-vacation", 0.8), point("v2-travel", 0.8),
                           point("v2-scope", 0.5)])
        with mock.patch.object(lab, "qrequest", fake):
            one = query({**self.QUERY, "top_k": 1})
            two = query({**self.QUERY, "top_k": 2})
        self.assertEqual([h["chunk_id"] for h in one["hits"]], ["v2-travel"])
        self.assertEqual([h["chunk_id"] for h in two["hits"]], ["v2-travel", "v2-vacation"])
        self.assertEqual(fake.limits, [1 + QDRANT_TIE_MARGIN, 2 + QDRANT_TIE_MARGIN])
        self.assertIn({"key": "audience", "match": {"value": "all"}},
                      fake.bodies[0]["filter"]["must"])

    def test_qdrant_widens_limit_while_tie_reaches_window_end(self):
        # Neun gleiche Scores; die kleinsten chunk_ids liefert Qdrant zuletzt.
        tied = [point(f"c{i}", 0.5) for i in range(9, 0, -1)]
        fake = FakeQdrant([point("a0", 0.9)] + tied)
        with mock.patch.object(lab, "qrequest", fake):
            result = query({**self.QUERY, "top_k": 2})
        self.assertEqual([h["chunk_id"] for h in result["hits"]], ["a0", "c1"])
        self.assertEqual(fake.limits, [6, 12])

    def test_qdrant_stops_when_window_ends_below_boundary(self):
        fake = FakeQdrant([point("b", 0.9), point("a", 0.9)] +
                          [point(f"z{i}", 0.1) for i in range(8)])
        with mock.patch.object(lab, "qrequest", fake):
            result = query({**self.QUERY, "top_k": 2})
        self.assertEqual([h["chunk_id"] for h in result["hits"]], ["a", "b"])
        self.assertEqual(fake.limits, [6])


if __name__ == "__main__":
    unittest.main()
