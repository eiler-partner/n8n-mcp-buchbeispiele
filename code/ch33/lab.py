"""Eigenständiger Vektorspeicher-Vertrag: synthetische Werte, keine Modell-Embeddings."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import date
from pathlib import Path
from urllib import request, error


ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))
SPACES = {"fixture-v1": (4, "ch33_fixture_v1", "ch33_pg_v1"),
          "fixture-v2": (6, "ch33_fixture_v2", "ch33_pg_v2")}
QDRANT = os.environ.get("QDRANT_URL", "http://qdrant:6333")
DB = os.environ.get("DATABASE_URL", "postgresql://lab:lab-local-only@pgvector:5432/lab")
# Gleichstandsregel beider Speicher: Score absteigend (= Distanz aufsteigend),
# bei Gleichstand chunk_id aufsteigend in Bytereihenfolge (COLLATE "C" = Python-str-Vergleich).
PG_ORDER_BY = 'ORDER BY distance, chunk_id COLLATE "C"'
QDRANT_TIE_MARGIN = 4  # Zusatzkandidaten, damit ein Gleichstand an der Grenze sichtbar wird


class ContractError(ValueError):
    pass


def space(model_id: str):
    if model_id not in SPACES:
        raise ContractError("unknown_embedding_space")
    return SPACES[model_id]


def version_at(value: str) -> str:
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("invalid_date") from exc
    if day < date(2026, 1, 1) or day >= date(2026, 10, 1):
        raise ContractError("no_visible_version")
    return "2026-01" if day < date(2026, 9, 1) else "2026-09"


def vector_for(row: dict, model_id: str) -> list[float]:
    """Kontrollierte Testkoordinaten; ausdrücklich kein semantisches Modell."""
    dim = space(model_id)[0]
    base = {"scope": [0.2, 0.2, 0.9, 0.1],
            "vacation": [1.0, 0.1, 0.1, 0.1],
            "travel": [0.1, 1.0, 0.1, 0.1],
            "hr": [0.1, 0.1, 0.1, 1.0]}[row["section_id"]]
    return base if dim == 4 else base + [0.05, 0.02]


def validate_query(payload: dict) -> tuple[int, str, str, str, str, list[float]]:
    dim, table, collection = space(payload.get("model_id"))
    store = payload.get("store")
    if store not in {"pgvector", "qdrant"}:
        raise ContractError("unknown_store")
    if payload.get("tenant_id") != "buchlabor":
        raise ContractError("unknown_tenant")
    role = payload.get("role")
    if role not in {"employee", "hr"}:
        raise ContractError("unknown_role")
    version = version_at(payload.get("as_of"))
    vector = payload.get("vector")
    if (not isinstance(vector, list) or len(vector) != dim or
            not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    and math.isfinite(x) for x in vector) or
            not any(x != 0 for x in vector)):
        raise ContractError("invalid_query_vector")
    return dim, table, collection, version, role, vector


def qrequest(method: str, path: str, body: dict | None = None) -> dict:
    raw = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(QDRANT + path, data=raw, method=method,
                          headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except error.HTTPError as exc:
        raise RuntimeError(f"qdrant_http_{exc.code}: {exc.read()[:200]!r}") from exc


def tie_order(hits: list[dict]) -> list[dict]:
    """Dieselbe Regel wie PG_ORDER_BY: Score absteigend, dann chunk_id aufsteigend."""
    return sorted(hits, key=lambda hit: (-hit["score"], hit["chunk_id"]))


def qdrant_points(collection: str, body: dict, top_k: int) -> list[dict]:
    """Holt mehr als top_k Punkte, bis kein Gleichstand mit Platz top_k mehr abgeschnitten ist."""
    limit = top_k + QDRANT_TIE_MARGIN
    while True:
        points = qrequest("POST", f"/collections/{collection}/points/query",
                          {**body, "limit": limit})["result"]["points"]
        if len(points) < limit:
            return points  # Scope vollständig gelesen
        kth = sorted((p["score"] for p in points), reverse=True)[top_k - 1]
        if min(p["score"] for p in points) < kth:
            return points  # alle nicht gelieferten Punkte liegen unter Platz top_k
        limit *= 2


def _point_id(model_id: str, chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ch33:{model_id}:{chunk_id}"))


def seed(model_id: str) -> dict:
    import psycopg
    dim, table, collection = space(model_id)
    with psycopg.connect(DB) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (chunk_id text PRIMARY KEY, tenant_id text NOT NULL, version_id text NOT NULL, audience text NOT NULL, section_id text NOT NULL, text_sha256 text NOT NULL, content text NOT NULL, embedding vector({dim}) NOT NULL)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {table}_scope ON {table} (tenant_id, version_id, audience)")
        for row in DATA["chunks"]:
            vec = vector_for(row, model_id)
            vec_literal = "[" + ",".join(map(str, vec)) + "]"
            sha = hashlib.sha256(row["text"].encode()).hexdigest()
            conn.execute(f"INSERT INTO {table} (chunk_id,tenant_id,version_id,audience,section_id,text_sha256,content,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (chunk_id) DO UPDATE SET tenant_id=excluded.tenant_id, version_id=excluded.version_id, audience=excluded.audience, section_id=excluded.section_id, text_sha256=excluded.text_sha256, content=excluded.content, embedding=excluded.embedding",
                         (row["chunk_id"], DATA["tenant_id"], row["version_id"], row["audience"], row["section_id"], sha, row["text"], vec_literal))
    try:
        info = qrequest("GET", f"/collections/{collection}")
        config = info["result"]["config"]["params"]["vectors"]
        if config["size"] != dim or config["distance"] != "Cosine":
            raise ContractError("qdrant_space_mismatch")
    except RuntimeError as exc:
        if not str(exc).startswith("qdrant_http_404"):
            raise
        qrequest("PUT", f"/collections/{collection}", {"vectors": {"size": dim, "distance": "Cosine"}})
    for field in ("tenant_id", "version_id", "audience"):
        qrequest("PUT", f"/collections/{collection}/index?wait=true",
                 {"field_name": field, "field_schema": "keyword"})
    points = []
    for row in DATA["chunks"]:
        points.append({"id": _point_id(model_id, row["chunk_id"]),
                       "vector": vector_for(row, model_id),
                       "payload": {**row, "tenant_id": DATA["tenant_id"],
                                   "text_sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
                                   "model_id": model_id}})
    qrequest("PUT", f"/collections/{collection}/points?wait=true", {"points": points})
    return {"model_id": model_id, "dimension": dim, "count": len(points),
            "pg_table": table, "qdrant_collection": collection}


def query(payload: dict) -> dict:
    dim, table, collection, version, role, vector = validate_query(payload)
    top_k = payload.get("top_k", 3)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 8:
        raise ContractError("invalid_top_k")
    if payload["store"] == "pgvector":
        import psycopg
        literal = "[" + ",".join(map(str, vector)) + "]"
        with psycopg.connect(DB) as conn:
            rows = conn.execute(
                f"SELECT chunk_id, section_id, audience, version_id, text_sha256, content, embedding <=> %s::vector AS distance FROM {table} WHERE tenant_id=%s AND version_id=%s AND (%s='hr' OR audience='all') {PG_ORDER_BY} LIMIT %s",
                (literal, payload["tenant_id"], version, role, top_k)).fetchall()
        hits = [{"chunk_id": r[0], "section_id": r[1], "audience": r[2],
                 "version_id": r[3], "text_sha256": r[4], "text": r[5],
                 "score": 1.0 - float(r[6])} for r in rows]
    else:
        must = [{"key": "tenant_id", "match": {"value": payload["tenant_id"]}},
                {"key": "version_id", "match": {"value": version}}]
        if role == "employee":
            must.append({"key": "audience", "match": {"value": "all"}})
        points = qdrant_points(collection, {"query": vector, "filter": {"must": must},
                                            "with_payload": True}, top_k)
        hits = tie_order([{"chunk_id": p["payload"]["chunk_id"],
                           "section_id": p["payload"]["section_id"],
                           "audience": p["payload"]["audience"],
                           "version_id": p["payload"]["version_id"],
                           "text_sha256": p["payload"]["text_sha256"],
                           "text": p["payload"]["text"], "score": p["score"]}
                          for p in points])[:top_k]
    return {"store": payload["store"], "model_id": payload["model_id"],
            "dimension": dim, "version_id": version, "hits": hits}
