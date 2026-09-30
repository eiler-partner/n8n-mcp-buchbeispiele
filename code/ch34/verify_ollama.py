"""Optionaler echter Modellvergleich mit datiertem Digest, ohne Download."""
from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from lab import CASES, CORPUS, measures, visible

ROOT = Path(__file__).parent
MODEL = os.environ.get("CH34_EMBED_MODEL", "all-minilm:latest")
BASE = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


def api(method: str, path: str, body: dict | None = None) -> dict:
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=raw, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


model = next((m for m in api("GET", "/api/tags")["models"] if m["name"] == MODEL), None)
if model is None:
    raise SystemExit(f"Modell {MODEL!r} nicht installiert; Prüfer lädt nichts nach")
texts = [r["text"] for r in CORPUS] + [c["question"] for c in CASES.values()]
vectors = api("POST", "/api/embed", {"model": MODEL, "input": texts})["embeddings"]
assert len(vectors) == len(texts)
dimension = len(vectors[0])
assert dimension > 0 and all(len(v) == dimension for v in vectors)
assert all(math.isfinite(x) for v in vectors for x in v)
norms = [math.sqrt(sum(x*x for x in v)) for v in vectors]
assert all(abs(n-1.0) < 0.01 for n in norms)
doc_vectors = dict(zip((r["id"] for r in CORPUS), vectors[:len(CORPUS)]))
case_vectors = dict(zip(CASES, vectors[len(CORPUS):]))
observations = []
for case_id, case in CASES.items():
    query = case_vectors[case_id]
    scored = sorted(((sum(x*y for x, y in zip(query, doc_vectors[row["id"]])), row["id"])
                     for row in CORPUS if visible(row, case)), reverse=True)
    ids = [item[1] for item in scored[:3]]
    observations.append({"case_id": case_id, "top_ids": ids,
                         "top_scores": [round(item[0], 6) for item in scored[:3]],
                         "metrics": measures(ids, case["relevant"])})
report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "model_name": model["name"], "model_digest": model["digest"],
          "dimension": dimension, "input_count": len(texts),
          "l2_norm_min": min(norms), "l2_norm_max": max(norms),
          "scope": "synthetic labeled chapter-34 fixture; prefiltered",
          "claim_limit": "dated observation, not a production retrieval guarantee",
          "cases": observations}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports/ollama-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
