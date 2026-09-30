"""Kleiner Router/Worker/Reviewer-Vergleich ohne Modellbehauptung.

Die Rollen sind deterministische Fixtures. Sie bilden Übergabeverträge ab,
nicht die Qualität oder Autonomie eines realen LLM-Agenten.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = {item["id"]: item for item in json.loads((ROOT / "data/cases.json").read_text())}
KNOWLEDGE = json.loads((ROOT / "data/knowledge.json").read_text())
ROUTES = {"billing", "privacy", "general"}
HANDOFF_KEYS = {
    "schema_version", "case_id", "tenant_id", "trace_id", "route",
    "context", "input_hash", "budget_remaining",
}
WORKER_KEYS = {"route", "source_id", "source_version", "answer"}


class ContractError(Exception):
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code = code
        self.status = status


def _case(case_id: object) -> dict:
    if not isinstance(case_id, str) or case_id not in CASES:
        raise ContractError("unknown_case", 404)
    return CASES[case_id]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def classify(text: str) -> str:
    lower = text.casefold()
    if "lösch" in lower or "aufbewahrung" in lower:
        return "privacy"
    if "rechnung" in lower:
        return "billing"
    return "general"


def _input(payload: dict) -> dict:
    if type(payload) is not dict or set(payload) != {"case_id", "tenant_id"}:
        raise ContractError("input_contract")
    case = _case(payload["case_id"])
    if payload["tenant_id"] != case["tenant_id"]:
        raise ContractError("tenant_mismatch")
    return case


def _source(case: dict, route: str) -> dict:
    record = KNOWLEDGE[case["source_id"]]
    if record["route"] != route:
        raise ContractError("route_mismatch")
    return record


def baseline(payload: dict) -> dict:
    case = _input(payload)
    route = classify(case["text"])
    record = _source(case, route)
    return {
        "case_id": case["id"], "route": route, "status": "accepted",
        "source_id": case["source_id"], "answer": record["answer"],
        "stage_calls": 1, "context_bytes": 0,
    }


def route(payload: dict) -> dict:
    case = _input(payload)
    text = case["text"]
    return {
        "schema_version": 1, "case_id": case["id"],
        "tenant_id": case["tenant_id"],
        "trace_id": _hash(f'{case["tenant_id"]}:{case["id"]}:{text}')[:16],
        "route": classify(text), "context": text[:120],
        "input_hash": _hash(text), "budget_remaining": 2,
    }


def validate_handoff(value: object) -> dict:
    if type(value) is not dict or set(value) != HANDOFF_KEYS:
        raise ContractError("handoff_shape")
    case = _case(value["case_id"])
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ContractError("handoff_version")
    if value["tenant_id"] != case["tenant_id"]:
        raise ContractError("tenant_mismatch")
    if type(value["context"]) is not str or len(value["context"].encode()) > 256:
        raise ContractError("context_budget")
    if value["context"] != case["text"][:120] or value["input_hash"] != _hash(case["text"]):
        raise ContractError("context_mismatch")
    expected_trace = _hash(f'{case["tenant_id"]}:{case["id"]}:{case["text"]}')[:16]
    if value["trace_id"] != expected_trace:
        raise ContractError("trace_mismatch")
    if (type(value["route"]) is not str or value["route"] not in ROUTES
            or value["route"] != classify(case["text"])):
        raise ContractError("route_mismatch")
    if type(value["budget_remaining"]) is not int or value["budget_remaining"] < 1:
        raise ContractError("budget_exhausted")
    return case


def work(handoff: dict) -> dict:
    case = validate_handoff(handoff)
    if handoff["budget_remaining"] < 2:
        raise ContractError("budget_exhausted")
    record = _source(case, handoff["route"])
    return {
        "handoff": {**handoff, "budget_remaining": handoff["budget_remaining"] - 1},
        "worker": {
            "route": handoff["route"], "source_id": case["source_id"],
            "source_version": record["version"], "answer": record["answer"],
        },
    }


def review(payload: dict) -> dict:
    if type(payload) is not dict or set(payload) != {"handoff", "worker"}:
        raise ContractError("review_shape")
    handoff, worker = payload["handoff"], payload["worker"]
    case = validate_handoff(handoff)
    if type(worker) is not dict or set(worker) != WORKER_KEYS:
        raise ContractError("worker_shape")
    record = _source(case, handoff["route"])
    if (worker["route"] != handoff["route"]
        or worker["source_id"] != case["source_id"]
        or worker["source_version"] != record["version"]
        or worker["answer"] != record["answer"]):
        raise ContractError("worker_result_mismatch")
    return {
        "case_id": case["id"], "trace_id": handoff["trace_id"],
        "route": worker["route"], "status": "accepted",
        "source_id": worker["source_id"], "answer": worker["answer"],
        "stage_calls": 3,
        "context_bytes": len(handoff["context"].encode()),
    }


def compare() -> dict:
    rows = []
    for case in CASES.values():
        payload = {"case_id": case["id"], "tenant_id": case["tenant_id"]}
        simple = baseline(payload)
        multi = review(work(route(payload)))
        def good(result: dict) -> bool:
            return (result["status"] == "accepted"
                    and result["route"] == case["expected_route"]
                    and result["source_id"] == case["source_id"]
                    and result["answer"] == case["expected_answer"])
        rows.append({
            "case_id": case["id"], "baseline_pass": good(simple),
            "multi_pass": good(multi), "baseline_stages": simple["stage_calls"],
            "multi_stages": multi["stage_calls"],
            "handoff_context_bytes": multi["context_bytes"],
        })
    base_pass = sum(row["baseline_pass"] for row in rows)
    multi_pass = sum(row["multi_pass"] for row in rows)
    gain = multi_pass - base_pass
    return {
        "dataset_sha256": hashlib.sha256((ROOT / "data/cases.json").read_bytes()).hexdigest(),
        "knowledge_sha256": hashlib.sha256((ROOT / "data/knowledge.json").read_bytes()).hexdigest(),
        "fixture_not_model_measurement": True,
        "cases": rows, "baseline_pass": base_pass, "multi_pass": multi_pass,
        "quality_gain": gain,
        "total_baseline_stages": sum(row["baseline_stages"] for row in rows),
        "total_multi_stages": sum(row["multi_stages"] for row in rows),
        "decision": "multi" if gain >= 1 and multi_pass == len(rows) else "baseline",
        "reason": "kein messbarer Qualitätsgewinn" if gain < 1
                  else "mindestens ein zusätzlicher korrekter Fall ohne Regression",
    }
