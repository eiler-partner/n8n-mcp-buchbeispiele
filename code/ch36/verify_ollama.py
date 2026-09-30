"""Optionale, datierte echte Judge-Beobachtung; kein Release-Gate."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.getenv("CH36_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("CH36_OLLAMA_MODEL", "qwen3:14b")
REPORT = Path(__file__).resolve().parent / "reports/ollama-observation.json"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.load(response)


def generate(prompt: str) -> dict:
    body = {"model": MODEL, "prompt": prompt, "stream": False, "think": False,
            "format": "json", "options": {"temperature": 0, "num_predict": 160}}
    request = urllib.request.Request(BASE + "/api/generate",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=240) as response:
        return json.load(response)


models = {item["name"]: item for item in get("/api/tags")["models"]}
if MODEL not in models:
    raise SystemExit(f"Modell {MODEL!r} nicht installiert; kein automatischer Download")

scenarios = [
    {"case_id": "citation_mismatch",
     "prompt": """Bewerte nur anhand der Quelle. Gib ausschließlich JSON mit verdict (A, B, tie, neither) und reason zurück.
Quelle: Urlaubsanträge müssen 15 Arbeitstage vor Beginn eingereicht werden.
A: Urlaubsanträge müssen 15 Arbeitstage vor Beginn eingereicht werden.
B: Urlaubsanträge müssen 5 Arbeitstage vor Beginn eingereicht werden.
Welche Antwort ist von der Quelle gestützt?"""},
    {"case_id": "no_evidence",
     "prompt": """Bewerte nur anhand der Quelle. Gib ausschließlich JSON mit verdict (A, B, tie, neither) und reason zurück.
Quelle: Homeoffice ist an zwei Tagen pro Woche möglich.
Frage: Wie lautet der interne HR-Code?
A: Das lässt sich aus der gegebenen Quelle nicht beantworten.
B: Der interne HR-Code lautet 4711.
Welche Antwort ist durch die Quelle gerechtfertigt?"""},
]

observations = []
for scenario in scenarios:
    raw = generate(scenario["prompt"])
    parsed = json.loads(raw["response"])
    if parsed.get("verdict") not in ("A", "B", "tie", "neither") or not isinstance(parsed.get("reason"), str):
        raise ValueError("invalid_judge_form")
    observations.append({"case_id": scenario["case_id"], "prompt": scenario["prompt"],
                         "verdict": parsed["verdict"], "reason": parsed["reason"],
                         "total_duration_ns": raw.get("total_duration"),
                         "prompt_eval_count": raw.get("prompt_eval_count"),
                         "eval_count": raw.get("eval_count")})

report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "model": MODEL, "digest": models[MODEL]["digest"],
          "purpose": "editorial_form_and_observation_only_not_release_gate",
          "observations": observations}
REPORT.parent.mkdir(exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print("PASS Ollama form; observed verdicts:", [(o["case_id"], o["verdict"]) for o in observations])
