"""Datensparsame Ereignis- und SLO-Auswertung für synthetische Kapitel-40-Daten."""
from __future__ import annotations

from collections import Counter

STAGES = ("n8n", "mcp", "retrieval", "model")
PARENTS = {"n8n": None, "mcp": "n8n", "retrieval": "mcp", "model": "mcp"}


def inspect_trace(events: list[dict], request_id: str) -> dict:
    rows = [row for row in events if row.get("request_id") == request_id]
    counts = Counter(row.get("stage") for row in rows)
    faults = []
    for stage in STAGES:
        if counts[stage] != 1:
            faults.append(f"{stage}_count_{counts[stage]}")
    ids = {row.get("correlation_id") for row in rows}
    if not rows or None in ids or len(ids) != 1:
        faults.append("correlation_broken")
    by_stage = {row.get("stage"): row for row in rows}
    for stage, parent in PARENTS.items():
        if stage in by_stage and by_stage[stage].get("parent_stage") != parent:
            faults.append(f"{stage}_parent_broken")
    for row in rows:
        if not isinstance(row.get("duration_ms"), (int, float)) or row["duration_ms"] < 0:
            faults.append("invalid_duration")
    return {"request_id": request_id, "complete": not faults,
            "faults": sorted(set(faults)), "stages": [row.get("stage") for row in rows],
            "correlation_id": next(iter(ids)) if len(ids) == 1 else None}


def synthetic_cost_micro_usd(input_tokens: int, output_tokens: int) -> int:
    """Lehrtarif: 0,20/0,80 USD je 1 Mio. Tokens; kein Anbieterpreis."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("negative_tokens")
    return round(input_tokens * 0.20 + output_tokens * 0.80)


def service_sli(reports: list[dict]) -> dict:
    total = len(reports)
    good = sum(bool(row.get("complete") and row.get("business_ok")) for row in reports)
    unverifiable = sum(not row.get("complete") for row in reports)
    known_failed = sum(bool(row.get("complete") and not row.get("business_ok")) for row in reports)
    return {"good": good, "total": total,
            "verified_success_ratio": good / total if total else None,
            "error_budget_99_percent": total * 0.01,
            "bad": total - good, "unverifiable": unverifiable,
            "known_failed": known_failed}
