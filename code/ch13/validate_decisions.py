"""Structural checks for architecture cards; does not replace human judgment."""

from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_OPERATIONS = {"get_document", "search_documents", "approve_document"}
DECISIONS = {"keep_direct", "mcp_candidate", "withhold_from_model"}
REQUIRED_TEXT = {
    "endpoint",
    "callers",
    "data_classification",
    "model_boundary",
    "consent_and_authorization",
    "rationale",
}


def validate_cards(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        return ["Top level must contain a cards array"]
    cards = payload["cards"]
    if len(cards) != 3:
        errors.append("Exactly three operation cards are required")
    seen: set[str] = set()
    for index, card in enumerate(cards, start=1):
        label = f"card {index}"
        if not isinstance(card, dict):
            errors.append(f"{label}: must be an object")
            continue
        operation = card.get("operation")
        if not isinstance(operation, str) or operation not in EXPECTED_OPERATIONS or operation in seen:
            errors.append(f"{label}: unknown or duplicate operation")
        elif isinstance(operation, str):
            seen.add(operation)
        for field in REQUIRED_TEXT:
            value = card.get(field)
            if not isinstance(value, str) or len(value.strip()) < 8:
                errors.append(f"{label}: {field} needs explanatory text")
        if not isinstance(card.get("side_effect"), str) or not card["side_effect"].strip():
            errors.append(f"{label}: side_effect must be named, or none")
        if not isinstance(card.get("independent_hosts"), int) or isinstance(card.get("independent_hosts"), bool) or card["independent_hosts"] < 1:
            errors.append(f"{label}: independent_hosts must be positive")
        if not isinstance(card.get("dynamic_discovery_needed"), bool):
            errors.append(f"{label}: dynamic_discovery_needed must be boolean")
        boundaries = card.get("trust_boundaries")
        if not isinstance(boundaries, list) or not boundaries or not all(
            isinstance(boundary, str) and "->" in boundary for boundary in boundaries
        ):
            errors.append(f"{label}: trust_boundaries must name directed flows")
        if card.get("decision") not in DECISIONS:
            errors.append(f"{label}: decision is not recognized")
        if card.get("decision") == "mcp_candidate" and card.get("side_effect") != "none":
            for field in ("authorization_design", "consent_design"):
                value = card.get(field)
                if not isinstance(value, str) or len(value.strip()) < 8:
                    errors.append(f"{label}: a write candidate needs a separate {field}")
    if seen != EXPECTED_OPERATIONS:
        errors.append("The three expected operations must each be present once")
    return errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("decisions.json")
    errors = validate_cards(json.loads(path.read_text(encoding="utf-8")))
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS three architecture cards are complete and structurally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
