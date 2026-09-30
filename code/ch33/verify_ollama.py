"""Optionaler echter Embedding-Formtest; lädt nie selbst ein Modell herunter."""
from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = os.environ.get("CH33_EMBED_MODEL", "all-minilm:latest")
BASE = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


def api(method: str, path: str, body: dict | None = None) -> dict:
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=raw, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


tags = api("GET", "/api/tags")["models"]
model = next((m for m in tags if m["name"] == MODEL), None)
if model is None:
    raise SystemExit(f"Modell {MODEL!r} nicht installiert; kein Download im Prüfer")
corpus = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))["chunks"]
query_text = "Wie viele Arbeitstage vor dem Urlaub muss der Antrag eingehen?"
texts = [r["text"] for r in corpus] + [query_text]
response = api("POST", "/api/embed", {"model": MODEL, "input": texts})
vectors = response["embeddings"]
assert len(vectors) == len(texts)
dimension = len(vectors[0])
assert dimension > 0 and all(len(v) == dimension for v in vectors)
assert all(math.isfinite(x) for v in vectors for x in v)
norms = [math.sqrt(sum(x*x for x in v)) for v in vectors]
assert all(abs(n - 1.0) < 0.01 for n in norms)
query = vectors[-1]
scored = sorted(((sum(a*b for a, b in zip(v, query)), row["chunk_id"])
                 for row, v in zip(corpus, vectors[:-1])
                 if row["version_id"] == "2026-09" and row["audience"] == "all"),
                reverse=True)
report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "model_name": model["name"], "model_digest": model["digest"],
          "dimension": dimension, "l2_norm_min": min(norms),
          "l2_norm_max": max(norms), "query": query_text,
          "input_count": len(texts), "top_ids": [item[1] for item in scored[:3]],
          "top_scores": [round(item[0], 6) for item in scored[:3]],
          "scope": "synthetic 2026-09 employee chunks",
          "claim_limit": "dated form and ranking observation; no general retrieval-quality claim"}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports/ollama-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
