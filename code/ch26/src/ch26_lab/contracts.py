from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"
# Kernfelder des feldweisen Golden-Vergleichs; sie müssen exakt dem Sollwert entsprechen.
CORE_FIELDS = ("intent", "date", "needs_review")


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_registry() -> tuple[dict, list[dict], dict, dict]:
    schema = json.loads((DATA / "extraction.schema.json").read_text(encoding="utf-8"))
    cases = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    fixtures = json.loads((DATA / "fixture_outputs.json").read_text(encoding="utf-8"))
    prompts = {version: (PROMPTS / f"prompt-{version}.txt").read_text(encoding="utf-8")
               for version in ("v1", "v2")}
    Draft202012Validator.check_schema(schema)
    if len(cases) != 8 or len({case["id"] for case in cases}) != 8:
        raise ValueError("Acht eindeutige Golden-Fälle erforderlich")
    ids = {case["id"] for case in cases}
    if set(fixtures) != {"baseline", "candidate"}:
        raise ValueError("Baseline und Kandidat erforderlich")
    if any(set(outputs) != ids for outputs in fixtures.values()):
        raise ValueError("Fixture-Antworten müssen alle Fälle enthalten")
    for case in cases:
        validation = validate_output(case["golden"], case["text"], schema)
        if not validation["contract_pass"]:
            raise ValueError(f"Golden-Fall {case['id']} verletzt Vertrag: {validation['error_class']}")
    return schema, cases, fixtures, prompts


def validate_output(
    raw: str | dict,
    input_text: str,
    schema: dict,
    *,
    refusal: bool = False,
    truncated: bool = False,
) -> dict[str, Any]:
    if refusal:
        return {"contract_pass": False, "error_class": "refusal", "value": None}
    if truncated:
        return {"contract_pass": False, "error_class": "truncated", "value": None}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {"contract_pass": False, "error_class": "json_syntax", "value": None}
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: (list(map(str, error.path)), error.message),
    )
    if errors:
        return {"contract_pass": False, "error_class": "schema", "value": None,
                "detail": errors[0].message}
    if value["evidence"] not in input_text:
        return {"contract_pass": False, "error_class": "semantic_evidence", "value": None}
    date = value["date"]
    # Reiner Zeichenkettenvergleich: Alle Falltexte enthalten ihr Datum in ISO-Form.
    # Für "am 14. Oktober" müsste man zuerst normalisieren und dann vergleichen.
    if date is not None and date not in input_text:
        return {"contract_pass": False, "error_class": "semantic_date", "value": None}
    if value["intent"] == "information" and (date is not None or value["needs_review"]):
        return {"contract_pass": False, "error_class": "semantic_information", "value": None}
    if value["intent"] != "information" and value["needs_review"] != (date is None):
        return {"contract_pass": False, "error_class": "semantic_review", "value": None}
    return {"contract_pass": True, "error_class": None, "value": value}


def compare_with_golden(value: dict, case: dict) -> dict[str, bool]:
    """Feldweiser Golden-Vergleich, wie ihn das Release-Gate nutzt.

    Die Kernfelder müssen exakt dem Sollwert entsprechen. Der Beleg darf vom
    Sollbeleg abweichen, muss aber ein wörtlicher Ausschnitt der Eingabe sein.
    `exact_match` (ganzes Objekt gleich) ist nur zusätzliche Information.
    """
    core_fields_match = all(value[key] == case["golden"][key] for key in CORE_FIELDS)
    evidence_in_input = value["evidence"] in case["text"]
    return {
        "golden_pass": core_fields_match and evidence_in_input,
        "exact_match": value == case["golden"],
    }


def grade_case(case: dict, raw: str | dict, schema: dict) -> dict:
    validation = validate_output(raw, case["text"], schema)
    if not validation["contract_pass"]:
        return {"case_id": case["id"], "contract_pass": False, "golden_pass": False,
                "exact_match": False, "error_class": validation["error_class"]}
    comparison = compare_with_golden(validation["value"], case)
    return {
        "case_id": case["id"],
        "contract_pass": True,
        **comparison,
        "error_class": None if comparison["golden_pass"] else "golden_mismatch",
    }


def evaluate_variant(variant: str) -> dict:
    schema, cases, fixtures, prompts = load_registry()
    if variant not in fixtures:
        raise ValueError("Unbekannte Fixture-Variante")
    prompt_version = "v1" if variant == "baseline" else "v2"
    results = [grade_case(case, fixtures[variant][case["id"]], schema) for case in cases]
    return {
        "variant": variant,
        "prompt_version": prompt_version,
        "prompt_sha256": hashlib.sha256(prompts[prompt_version].encode("utf-8")).hexdigest(),
        "schema_sha256": sha256_json(schema),
        "dataset_sha256": sha256_json(cases),
        "fixture_sha256": sha256_json(fixtures[variant]),
        "contract_pass_count": sum(item["contract_pass"] for item in results),
        "golden_pass_count": sum(item["golden_pass"] for item in results),
        "exact_match_count": sum(item["exact_match"] for item in results),
        "total": len(cases),
        "results": results,
    }


def full_report() -> dict:
    baseline = evaluate_variant("baseline")
    candidate = evaluate_variant("candidate")
    return {
        "schema_version": 1,
        "measurement_kind": "deterministic_fixture_not_model_benchmark",
        "golden_comparison": {
            "exact_fields": list(CORE_FIELDS),
            "evidence": "verbatim_excerpt_of_input",
            "exact_match": "information_only",
        },
        "baseline": baseline,
        "candidate": candidate,
        # Gate: Vertrag und feldweiser Golden-Vergleich; exact_match zählt nicht.
        "release_ready": candidate["contract_pass_count"] == candidate["total"]
        and candidate["golden_pass_count"] == candidate["total"],
    }
