"""Kapitel 34: gefilterte FTS-/Vektor-Baselines und explizite RRF-Fusion."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
CORPUS = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))["rows"]
CASES = {c["id"]: c for c in json.loads((ROOT / "data/cases.json").read_text(encoding="utf-8"))["cases"]}
DB = os.environ.get("DATABASE_URL", "postgresql://lab:lab-local-only@pgvector:5432/lab")
# lexical_expanded: nur der FTS-Zweig mit der freigegebenen erweiterten Query, ohne Fusion
MODES = ("lexical", "lexical_expanded", "dense", "hybrid", "hybrid_expanded")
RRF_K = 60
CANDIDATE_DEPTH = 6
DENSE_THRESHOLD = 0.50  # nur ein offengelegter Fixture-Parameter, kein Modellstandard
TOP_K = 3


class ContractError(ValueError):
    pass


def version_at(value: str) -> str:
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("invalid_date") from exc
    if day < date(2026, 1, 1) or day >= date(2026, 10, 1):
        raise ContractError("no_visible_version")
    return "2026-01" if day < date(2026, 9, 1) else "2026-09"


def visible(row: dict, case: dict) -> bool:
    return (row["tenant"] == case["tenant"] and row["status"] == "approved"
            and row["version"] == version_at(case["as_of"])
            and (case["role"] == "hr" or row["audience"] == "all"))


def validate_fixture() -> None:
    ids = [r["id"] for r in CORPUS]
    if len(ids) != len(set(ids)):
        raise ContractError("duplicate_chunk_id")
    for row in CORPUS:
        vector = row["vector"]
        if len(vector) != 4 or not all(math.isfinite(x) for x in vector) or not any(vector):
            raise ContractError("invalid_corpus_vector")
    for case in CASES.values():
        if case["role"] not in {"employee", "hr"} or case["tenant"] != "buchlabor":
            raise ContractError("invalid_case_scope")
        if len(case["vector"]) != 4:
            raise ContractError("invalid_query_vector")
        if not set(case["relevant"]).issubset({r["id"] for r in CORPUS if visible(r, case)}):
            raise ContractError("qrel_outside_scope")


def rrf(lists: list[list[dict]], limit: int = TOP_K, constant: int = RRF_K) -> list[dict]:
    if constant < 1 or limit < 1:
        raise ContractError("invalid_fusion_parameter")
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for hits in lists:
        if len({hit["id"] for hit in hits}) != len(hits):
            raise ContractError("duplicate_in_ranked_list")
        for rank, hit in enumerate(hits, 1):
            scores[hit["id"]] = scores.get(hit["id"], 0.0) + 1.0 / (constant + rank)
            by_id[hit["id"]] = hit
    ordered = sorted(scores, key=lambda item: (-scores[item], item))[:limit]
    return [{**by_id[item], "score": scores[item]} for item in ordered]


def measures(ids: list[str], relevant: list[str], k: int = TOP_K) -> dict:
    if not relevant:
        return {"precision_at_k": None, "recall_at_k": None,
                "false_positive_count": len(ids[:k])}
    found = len(set(ids[:k]) & set(relevant))
    return {"precision_at_k": round(found / k, 6),
            "recall_at_k": round(found / len(relevant), 6),
            "false_positive_count": None}


def seed() -> dict:
    import psycopg
    validate_fixture()
    with psycopg.connect(DB) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("""CREATE TABLE IF NOT EXISTS ch34_chunks (
            chunk_id text PRIMARY KEY, tenant_id text NOT NULL,
            version_id text NOT NULL, audience text NOT NULL,
            status text NOT NULL, content text NOT NULL,
            text_sha256 text NOT NULL, embedding vector(4) NOT NULL,
            fts tsvector GENERATED ALWAYS AS (to_tsvector('german'::regconfig, content)) STORED
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ch34_scope_idx ON ch34_chunks (tenant_id, version_id, status, audience)")
        conn.execute("CREATE INDEX IF NOT EXISTS ch34_fts_idx ON ch34_chunks USING GIN (fts)")
        for row in CORPUS:
            vec = "[" + ",".join(map(str, row["vector"])) + "]"
            sha = hashlib.sha256(row["text"].encode()).hexdigest()
            conn.execute("""INSERT INTO ch34_chunks
                (chunk_id,tenant_id,version_id,audience,status,content,text_sha256,embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                tenant_id=excluded.tenant_id,version_id=excluded.version_id,
                audience=excluded.audience,status=excluded.status,
                content=excluded.content,text_sha256=excluded.text_sha256,
                embedding=excluded.embedding""",
                (row["id"], row["tenant"], row["version"], row["audience"],
                 row["status"], row["text"], sha, vec))
    return {"status": "seeded", "count": len(CORPUS),
            "vector_space": "synthetic-fixture-4d", "fts_config": "german"}


def _lexical(conn, case: dict, expanded: bool) -> list[dict]:
    query_text = case["expanded_query"] if expanded else case["lexical_query"]
    rows = conn.execute("""SELECT chunk_id, content, text_sha256,
        ts_rank_cd(fts, q, 32) AS score
        FROM ch34_chunks, websearch_to_tsquery('german'::regconfig, %s) AS q
        WHERE tenant_id=%s AND version_id=%s AND status='approved'
          AND (%s='hr' OR audience='all') AND fts @@ q
        ORDER BY score DESC, chunk_id LIMIT %s""",
        (query_text, case["tenant"], version_at(case["as_of"]),
         case["role"], CANDIDATE_DEPTH)).fetchall()
    return [{"id": r[0], "text": r[1], "text_sha256": r[2], "score": float(r[3])}
            for r in rows]


def _dense(conn, case: dict) -> list[dict]:
    vec = "[" + ",".join(map(str, case["vector"])) + "]"
    rows = conn.execute("""SELECT chunk_id, content, text_sha256,
        1 - (embedding <=> %s::vector) AS score
        FROM ch34_chunks
        WHERE tenant_id=%s AND version_id=%s AND status='approved'
          AND (%s='hr' OR audience='all')
          AND 1 - (embedding <=> %s::vector) >= %s
        ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s""",
        (vec, case["tenant"], version_at(case["as_of"]), case["role"],
         vec, DENSE_THRESHOLD, vec, CANDIDATE_DEPTH)).fetchall()
    return [{"id": r[0], "text": r[1], "text_sha256": r[2], "score": float(r[3])}
            for r in rows]


def retrieve(case_id: str, mode: str, top_k: int = TOP_K) -> dict:
    import psycopg
    if case_id not in CASES:
        raise ContractError("unknown_case")
    if mode not in MODES:
        raise ContractError("unknown_mode")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= TOP_K:
        raise ContractError("invalid_top_k")
    case = CASES[case_id]
    with psycopg.connect(DB) as conn:
        if mode in ("lexical", "lexical_expanded"):
            hits = _lexical(conn, case, mode == "lexical_expanded")[:top_k]
        elif mode == "dense":
            hits = _dense(conn, case)[:top_k]
        else:
            hits = rrf([_lexical(conn, case, mode == "hybrid_expanded"),
                        _dense(conn, case)], top_k)
    return {"case_id": case_id, "mode": mode, "top_k": top_k,
            "question": case["question"], "scope": {"tenant": case["tenant"],
            "role": case["role"], "version": version_at(case["as_of"])},
            "hits": hits, "metrics": measures([h["id"] for h in hits],
                                                 case["relevant"], top_k)}


def evaluate() -> dict:
    results = []
    for case_id in CASES:
        for mode in MODES:
            results.append(retrieve(case_id, mode))
    summary = {}
    for mode in MODES:
        positives = [r["metrics"] for r in results
                     if r["mode"] == mode and r["metrics"]["recall_at_k"] is not None]
        negatives = [r["metrics"] for r in results
                     if r["mode"] == mode and r["metrics"]["recall_at_k"] is None]
        summary[mode] = {"macro_precision_at_3": round(sum(r["precision_at_k"] for r in positives) / len(positives), 6),
                         "macro_recall_at_3": round(sum(r["recall_at_k"] for r in positives) / len(positives), 6),
                         "no_answer_false_positives": sum(r["false_positive_count"] for r in negatives)}
    return {"fixture_only": True, "k": TOP_K, "candidate_depth": CANDIDATE_DEPTH,
            "rrf_constant": RRF_K, "dense_threshold": DENSE_THRESHOLD,
            "summary": summary, "cases": results}
