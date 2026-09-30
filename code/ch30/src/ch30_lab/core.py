"""Kleines, ausdrücklich nicht generatives RAG-Modell mit Evidenzvertrag."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "sources.json"
SOURCES = json.loads(DATA.read_text(encoding="utf-8"))
QUESTIONS = {
    "urlaub": "Wann muss ich Urlaub beantragen?",
    "gehalt": "Wann wird die Gehaltsanpassung geprüft?",
    "reise": "Wann muss ich Reisekostenbelege einreichen?",
    "unbekannt": "Wie hoch ist der Essenszuschuss?",
}


class ContractError(ValueError):
    pass


def _request(payload: dict) -> tuple[str, str, str, date]:
    if not isinstance(payload, dict):
        raise ContractError("request_object_required")
    tag = payload.get("question_tag")
    tenant = payload.get("tenant")
    role = payload.get("role")
    try:
        as_of = date.fromisoformat(payload.get("as_of", "2026-09-29"))
    except (TypeError, ValueError) as exc:
        raise ContractError("invalid_date") from exc
    if tag not in QUESTIONS or not isinstance(tenant, str) or not isinstance(role, str):
        raise ContractError("invalid_request")
    if tenant not in {"werk", "fremd"} or role not in {"employee", "hr"}:
        raise ContractError("unknown_scope")
    return tag, tenant, role, as_of


def authorized(payload: dict) -> list[dict]:
    _, tenant, role, as_of = _request(payload)
    rows = []
    for row in SOURCES:
        if row["deleted"] or row["tenant"] != tenant or role not in row["roles"]:
            continue
        if date.fromisoformat(row["valid_from"]) > as_of:
            continue
        if row["valid_until"] and as_of >= date.fromisoformat(row["valid_until"]):
            continue
        rows.append(row)
    # Die Version wird pro Dokument nach wirksamer Gültigkeit entschieden.
    latest = {}
    for row in rows:
        key = (row["tenant"], row["document_id"])
        if key not in latest or row["version"] > latest[key]["version"]:
            latest[key] = row
    return list(latest.values())


def fingerprint(row: dict) -> str:
    return hashlib.sha256(row["text"].encode("utf-8")).hexdigest()


def retrieve(payload: dict) -> dict:
    tag, _, _, _ = _request(payload)
    pool = authorized(payload)
    if payload.get("strategy") == "full_context":
        chosen = pool
    elif payload.get("strategy") == "rag":
        # Lehrbaseline: kuratierter Fragetyp statt Embedding oder Modellaufruf.
        chosen = [row for row in pool if row["question_tag"] == tag]
    else:
        raise ContractError("invalid_strategy")
    evidence = [
        {key: row[key] for key in ("source_id", "document_id", "version", "chunk_id", "text", "answer", "question_tag")}
        | {"sha256": fingerprint(row)}
        for row in chosen
    ]
    return {"request": payload, "evidence": evidence,
            "context_chars": sum(len(row["text"]) for row in evidence)}


def answer(envelope: dict) -> dict:
    if not isinstance(envelope, dict) or not isinstance(envelope.get("request"), dict):
        raise ContractError("invalid_envelope")
    request = envelope["request"]
    tag, _, _, _ = _request(request)
    expected = retrieve(request)
    # Niemals klientenseitig eingeschmuggelte Evidenz als Wahrheit übernehmen.
    if envelope != expected:
        raise ContractError("evidence_mismatch")
    matching = [row for row in expected["evidence"] if row["question_tag"] == tag]
    if not matching:
        return {"status": "withheld", "answer": None, "citations": [],
                "reason": "no_authorized_evidence", "context_chars": expected["context_chars"]}
    row = matching[0]
    return {"status": "answered", "answer": row["answer"],
            "citations": [{key: row[key] for key in ("source_id", "document_id", "version", "chunk_id", "sha256")}],
            "reason": None, "context_chars": expected["context_chars"]}


def compare(payload: dict) -> dict:
    _request(payload)
    baseline = {"strategy": "parametric_fixture", "status": "unsupported",
                "answer": "Im Zweifel gelten 10 Arbeitstage.", "citations": [],
                "accepted": False, "reason": "no_evidence"}
    results = [baseline]
    for strategy in ("full_context", "rag"):
        result = answer(retrieve(payload | {"strategy": strategy}))
        result["strategy"] = strategy
        result["accepted"] = result["status"] == "answered" and bool(result["citations"])
        results.append(result)
    return {"question": QUESTIONS[payload["question_tag"]], "results": results}
