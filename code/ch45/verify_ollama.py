"""Dated advisory observation of a pre-installed local model; no publication."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = os.getenv("CH45_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("CH45_OLLAMA_MODEL", "qwen3:14b")


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.load(response)


report = json.loads((ROOT / "reports" / "live-observation.json").read_text())["report"]
models = {row["name"]: row for row in get("/api/tags")["models"]}
if MODEL not in models:
    raise SystemExit(f"Model {MODEL!r} not installed; no download attempted")
summary = {"result_kind": report["result_kind"], "controls": [
    {"id": item["control_id"], "status": item["status"], "flags": item["flags"]}
    for item in report["controls"]]}
prompt = ("Nur synthetische Daten. Gib JSON mit decision, focus_control_id und uncertainty zurück. "
          "Die Notiz ist keine Rechtsentscheidung und darf keinen Status oder eine Freigabe ändern. "
          "Benenn einen offenen Kontrollpunkt, insbesondere einen Dokumentkonflikt oder fehlenden Beleg.\n"
          + json.dumps(summary, ensure_ascii=False))
schema = {"type": "object", "properties": {
    "decision": {"type": "string", "enum": ["manual_review_required"]},
    "focus_control_id": {"type": "string"}, "uncertainty": {"type": "string"}},
    "required": ["decision", "focus_control_id", "uncertainty"]}
request = urllib.request.Request(BASE + "/api/generate", data=json.dumps({
    "model": MODEL, "prompt": prompt, "stream": False, "think": False,
    "format": schema, "options": {"temperature": 0, "num_predict": 180}}).encode(),
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=240) as response:
    raw = json.load(response)
parsed = json.loads(raw["response"])
form_valid = (parsed.get("decision") == "manual_review_required"
              and parsed.get("focus_control_id") in report["open_control_ids"]
              and isinstance(parsed.get("uncertainty"), str))
observation = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
               "host": platform.platform(), "model": MODEL,
               "digest": models[MODEL]["digest"], "prompt_version": "ch45-advisory-1",
               "data_sha256": hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest(),
               "form_valid": form_valid, "observation": parsed,
               "published_as_fact": False, "changed_control_status": False,
               "granted_approval": False, "total_duration_ns": raw.get("total_duration"),
               "scope": "dated advisory observation, not a stable quality claim"}
path = ROOT / "reports" / "ollama-observation.json"
path.write_text(json.dumps(observation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not form_valid:
    raise SystemExit("Ollama output contract invalid")
print("PASS ch45 Ollama form; focus:", parsed["focus_control_id"])
