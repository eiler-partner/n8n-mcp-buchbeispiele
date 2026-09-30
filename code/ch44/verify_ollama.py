"""Dated advisory model observation; never publishes model text as a fact."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = os.getenv("CH44_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("CH44_OLLAMA_MODEL", "qwen3:14b")


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.load(response)


def generate(prompt: str) -> dict:
    schema = {"type": "object", "properties": {
        "decision": {"type": "string", "enum": ["review_required", "ready_for_editorial_review"]},
        "focus_statement_id": {"type": "string"}, "uncertainty": {"type": "string"}},
        "required": ["decision", "focus_statement_id", "uncertainty"]}
    payload = {"model": MODEL, "prompt": prompt, "stream": False, "think": False,
               "format": schema, "options": {"temperature": 0, "num_predict": 200}}
    request = urllib.request.Request(BASE + "/api/generate", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=240) as response:
        return json.load(response)


artifact = json.loads((ROOT / "reports" / "live-observation.json").read_text())
briefing = artifact["report"]
models = {row["name"]: row for row in get("/api/tags")["models"]}
if MODEL not in models:
    raise SystemExit(f"Model {MODEL!r} not installed; no download attempted")
small = {"status": briefing["status"], "statements": [
    {"statement_id": row["statement_id"], "status": row["status"], "text": row["text"]}
    for row in briefing["statements"]]}
prompt = ("Du erhältst ausschließlich synthetische Daten. Gib JSON mit decision, "
          "focus_statement_id und uncertainty zurück. Bei widersprüchlichen Bestellzahlen "
          "wähle review_required und benenne orders. Erfinde keine zusätzliche Zahl. "
          "Diese Interpretation bleibt advisory und wird nicht als Fakt veröffentlicht.\n"
          + json.dumps(small, ensure_ascii=False))
raw = generate(prompt)
parsed = json.loads(raw["response"])
ids = {row["statement_id"] for row in briefing["statements"]}
form_valid = (parsed.get("decision") in ("review_required", "ready_for_editorial_review")
              and parsed.get("focus_statement_id") in ids
              and isinstance(parsed.get("uncertainty"), str))
report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL,
          "digest": models[MODEL]["digest"], "prompt_version": "ch44-advisory-1",
          "data_sha256": hashlib.sha256(json.dumps(small, sort_keys=True).encode()).hexdigest(),
          "form_valid": form_valid,
          "matches_deterministic_conflict": parsed.get("decision") == briefing["status"]
              and parsed.get("focus_statement_id") == "orders",
          "observation": parsed, "published_as_fact": False,
          "total_duration_ns": raw.get("total_duration"),
          "scope": "dated advisory observation, not a stable quality claim"}
destination = ROOT / "reports" / "ollama-observation.json"
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not form_valid:
    raise SystemExit("Ollama output contract invalid")
print("PASS Ollama form; matched deterministic conflict:", report["matches_deterministic_conflict"])
