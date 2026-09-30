from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RETRYABLE_FAILURES = {"timeout", "transport", "rate_limit"}


class SelectionError(ValueError):
    """Ein Vertrag oder eine Auswahlregel ist nicht erfüllt."""


def load_data(data_dir: Path = DATA_DIR) -> tuple[list[dict], list[dict], dict]:
    cases = json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))
    profiles = json.loads((data_dir / "profiles.json").read_text(encoding="utf-8"))
    scenarios = json.loads((data_dir / "scenarios.json").read_text(encoding="utf-8"))
    if len(cases) != 12 or len({item["id"] for item in cases}) != 12:
        raise SelectionError("Datensatz muss zwölf eindeutige Fälle enthalten")
    if len(profiles) != 3 or len({item["id"] for item in profiles}) != 3:
        raise SelectionError("Es werden drei eindeutige Fixture-Profile erwartet")
    if not scenarios:
        raise SelectionError("Szenarien fehlen")
    return cases, profiles, scenarios


def dataset_digest(cases: list[dict]) -> str:
    payload = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_scenario(scenario: dict) -> None:
    weights = scenario.get("weights", {})
    if set(weights) != {"quality", "latency", "cost"}:
        raise SelectionError("Gewichte für Qualität, Latenz und Kosten fehlen")
    if any(not isinstance(value, (int, float)) or value < 0 for value in weights.values()):
        raise SelectionError("Gewichte müssen nichtnegative Zahlen sein")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise SelectionError("Gewichte müssen zusammen 1 ergeben")
    for key in ("max_cost_units", "max_latency_ms"):
        if not isinstance(scenario.get(key), (int, float)) or scenario[key] <= 0:
            raise SelectionError(f"{key} muss positiv sein")
    minimum = scenario.get("min_accuracy")
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not 0 <= minimum <= 1:
        raise SelectionError("min_accuracy muss zwischen 0 und 1 liegen")
    if not scenario.get("allowed_regions") or not scenario.get("required_capabilities"):
        raise SelectionError("Regionen und Fähigkeiten müssen angegeben sein")


def evaluate(
    scenario_name: str,
    cases: list[dict],
    profiles: list[dict],
    scenarios: dict,
) -> dict[str, Any]:
    if scenario_name not in scenarios:
        raise SelectionError(f"Unbekanntes Szenario: {scenario_name}")
    scenario = scenarios[scenario_name]
    validate_scenario(scenario)
    task_cases = [case for case in cases if case["task"] == scenario["task"]]
    if not task_cases:
        raise SelectionError("Kein Testfall für die Aufgabe vorhanden")

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for profile in profiles:
        reasons: list[str] = []
        if not set(scenario["required_capabilities"]) <= set(profile["capabilities"]):
            reasons.append("fähigkeit")
        if profile["region"] not in scenario["allowed_regions"]:
            reasons.append("datenweg")
        if profile["synthetic_cost_units"] > scenario["max_cost_units"]:
            reasons.append("kostenbudget")
        if profile["synthetic_latency_ms"] > scenario["max_latency_ms"]:
            reasons.append("latenzbudget")
        if reasons:
            excluded.append({"profile": profile["id"], "reason": ",".join(reasons)})
            continue

        missing = [case["id"] for case in task_cases if case["id"] not in profile["outputs"]]
        if missing:
            raise SelectionError(f"Messwerte fehlen für {profile['id']}: {missing}")
        correct = sum(profile["outputs"][case["id"]] == case["expected"] for case in task_cases)
        accuracy = correct / len(task_cases)
        if accuracy < scenario["min_accuracy"]:
            excluded.append({"profile": profile["id"], "reason": "qualitätsgrenze"})
            continue
        weights = scenario["weights"]
        score = (
            weights["quality"] * accuracy
            + weights["latency"] * (1 - profile["synthetic_latency_ms"] / scenario["max_latency_ms"])
            + weights["cost"] * (1 - profile["synthetic_cost_units"] / scenario["max_cost_units"])
        )
        candidates.append({
            "profile": profile["id"],
            "correct": correct,
            "cases": len(task_cases),
            "accuracy": round(accuracy, 6),
            "synthetic_latency_ms": profile["synthetic_latency_ms"],
            "synthetic_cost_units": profile["synthetic_cost_units"],
            "score": round(score, 6),
        })
    candidates.sort(key=lambda item: (-item["score"], item["profile"]))
    excluded.sort(key=lambda item: item["profile"])
    return {
        "scenario": scenario_name,
        "dataset_sha256": dataset_digest(cases),
        "measurement_kind": "synthetic_fixture_not_real_model_benchmark",
        "selected": candidates[0]["profile"] if candidates else None,
        "ranked_candidates": candidates,
        "excluded": excluded,
    }


def fallback(report: dict, failed_profile: str, failure_kind: str) -> str:
    if failure_kind not in RETRYABLE_FAILURES:
        raise SelectionError("Fach- oder Policyfehler erlauben keinen automatischen Fallback")
    ranked = [item["profile"] for item in report["ranked_candidates"]]
    if failed_profile not in ranked:
        raise SelectionError("Ausgefallenes Profil ist kein zulässiger Kandidat")
    if failed_profile != report["selected"]:
        raise SelectionError("Nur das ausgewählte Profil darf ausfallen")
    alternatives = [profile for profile in ranked if profile != failed_profile]
    if not alternatives:
        raise SelectionError("Kein kompatibler Fallback vorhanden")
    return alternatives[0]


def full_report(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    cases, profiles, scenarios = load_data(data_dir)
    return {"schema_version": 1, "scenarios": {
        name: evaluate(name, cases, profiles, scenarios) for name in sorted(scenarios)
    }}
