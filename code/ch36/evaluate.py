"""Deterministischer 2x2-RAG-Prüflauf; Fixture-Texte sind keine LLM-Ausgaben."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((ROOT / "data/golden.json").read_text(encoding="utf-8"))
CASES = {case["case_id"]: case for case in GOLDEN}
VARIANTS = [(chunking, retrieval) for chunking in ("short", "wide")
            for retrieval in ("lexical", "expanded")]
# Laborgrenzen vor jeder Ergebnissichtung festgelegt; keine Produktions-SLOs.
GATES = {"context_recall_min": 0.75, "answer_coverage_min": 0.75,
         "answer_precision_min": 0.80, "no_answer_accuracy_min": 1.0,
         "citation_validity_min": 1.0, "max_scope_violations": 0}
ALIASES = {"rkk": "auslandsreisekosten", "ausland": "auslandsreisekosten",
           "reisespesen": "reisekostenbelege", "inland": "inländische",
           "dienstreise": "dienstreiseanträge"}
STOP = {"wie", "was", "wer", "wann", "welche", "welcher", "gilt", "gibt", "es",
        "für", "ich", "ein", "eine", "muss", "sind", "der", "die", "das", "und",
        "vor", "habe", "hoch", "ist", "lautet", "früh", "viele", "lange", "kann"}


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w]+", text.lower())) - STOP


def visible(document: dict, case: dict) -> bool:
    return (document["tenant"] == case["tenant"]
            and document["version"] == case["version"]
            and document["status"] == "approved"
            and (document["audience"] == "all" or case["role"] == "hr"))


def chunks(chunking: str, case: dict) -> list[dict]:
    if chunking not in ("short", "wide"):
        raise ValueError("unknown_chunking")
    output = []
    for document in CORPUS:
        if not visible(document, case):
            continue
        groups = [[fact] for fact in document["facts"]] if chunking == "short" else [document["facts"]]
        for index, group in enumerate(groups, 1):
            output.append({"chunk_id": f"{document['document_id']}:{index}:{chunking}",
                           "document_id": document["document_id"],
                           "fact_ids": [fact["id"] for fact in group],
                           "text": " ".join(fact["text"] for fact in group),
                           "facts": group})
    return output


def retrieve(case: dict, chunking: str, retrieval: str, top_k: int = 3) -> list[dict]:
    if retrieval not in ("lexical", "expanded"):
        raise ValueError("unknown_retrieval")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 10:
        raise ValueError("invalid_top_k")
    query = tokens(case["question"])
    if retrieval == "expanded":
        query |= {ALIASES[token] for token in query if token in ALIASES}
    ranked = []
    for chunk in chunks(chunking, case):
        score = len(query & tokens(chunk["text"]))
        if score:
            ranked.append((score, chunk))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
    return [chunk for _, chunk in ranked[:top_k]]


def fixture_answer(hits: list[dict]) -> list[dict]:
    """Naiver, reproduzierbarer Antwortadapter: zitiert alle Fakten aus Top-1."""
    if not hits:
        return []
    top = hits[0]
    return [{"fact_id": fact["id"], "sentence": fact["text"],
             "citation_chunk_id": top["chunk_id"]} for fact in top["facts"]]


def valid_citation(claim: dict, hits: list[dict]) -> bool:
    return any(claim.get("citation_chunk_id") == chunk["chunk_id"]
               and any(claim.get("fact_id") == fact["id"]
                       and claim.get("sentence") == fact["text"] for fact in chunk["facts"])
               for chunk in hits)


def evaluate_case(case: dict, chunking: str, retrieval: str) -> dict:
    hits = retrieve(case, chunking, retrieval)
    claims = fixture_answer(hits)
    gold = set(case["gold"])
    found = set().union(*(set(hit["fact_ids"]) for hit in hits)) if hits else set()
    answered = {claim["fact_id"] for claim in claims}
    relevant_chunks = sum(bool(set(hit["fact_ids"]) & gold) for hit in hits)
    scope_violations = sum(not any(visible(doc, case) and doc["document_id"] == hit["document_id"]
                                   for doc in CORPUS) for hit in hits)
    return {"case_id": case["case_id"], "cohort": case["cohort"],
            "gold": sorted(gold), "hits": [{"chunk_id": hit["chunk_id"],
                                           "fact_ids": hit["fact_ids"]} for hit in hits],
            "claims": claims,
            "context_recall": len(found & gold) / len(gold) if gold else None,
            "retrieval_precision": relevant_chunks / len(hits) if gold and hits else (0.0 if gold else None),
            "context_fact_purity": len(found & gold) / len(found) if gold and found else (0.0 if gold else None),
            "answer_coverage": len(answered & gold) / len(gold) if gold else None,
            "answer_precision": len(answered & gold) / len(answered) if gold and answered else (0.0 if gold else None),
            "no_answer_correct": not claims if not gold else None,
            "valid_citations": sum(valid_citation(claim, hits) for claim in claims),
            "claim_count": len(claims), "scope_violations": scope_violations}


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_variant(chunking: str, retrieval: str) -> dict:
    cases = [evaluate_case(case, chunking, retrieval) for case in GOLDEN]
    positives = [case for case in cases if case["gold"]]
    negatives = [case for case in cases if not case["gold"]]
    metrics = {"context_recall": mean([case["context_recall"] for case in positives]),
               "retrieval_precision": mean([case["retrieval_precision"] for case in positives]),
               "context_fact_purity": mean([case["context_fact_purity"] for case in positives]),
               "answer_coverage": mean([case["answer_coverage"] for case in positives]),
               "answer_precision": mean([case["answer_precision"] for case in positives]),
               "no_answer_accuracy": mean([float(case["no_answer_correct"]) for case in negatives]),
               "citation_validity": (sum(case["valid_citations"] for case in cases) /
                                     sum(case["claim_count"] for case in cases)
                                     if sum(case["claim_count"] for case in cases) else 1.0),
               "scope_violations": sum(case["scope_violations"] for case in cases)}
    gate = {"context_recall": metrics["context_recall"] >= GATES["context_recall_min"],
            "answer_coverage": metrics["answer_coverage"] >= GATES["answer_coverage_min"],
            "answer_precision": metrics["answer_precision"] >= GATES["answer_precision_min"],
            "no_answer_accuracy": metrics["no_answer_accuracy"] >= GATES["no_answer_accuracy_min"],
            "citation_validity": metrics["citation_validity"] >= GATES["citation_validity_min"],
            "scope_violations": metrics["scope_violations"] <= GATES["max_scope_violations"]}
    return {"variant": f"{chunking}+{retrieval}", "metrics": metrics,
            "gate_checks": gate, "release": "pass" if all(gate.values()) else "hold",
            "cases": cases}


def evaluate_all() -> dict:
    results = [evaluate_variant(*variant) for variant in VARIANTS]
    baseline = results[0]["metrics"]
    for result in results:
        result["delta_answer_coverage_vs_short_lexical"] = (
            result["metrics"]["answer_coverage"] - baseline["answer_coverage"])
    return {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "fixture_only": True, "model_calls": 0, "top_k": 3,
            "case_count": len(GOLDEN), "positive_cases": sum(bool(c["gold"]) for c in GOLDEN),
            "no_answer_cases": sum(not c["gold"] for c in GOLDEN),
            "corpus_sha256": digest(CORPUS), "golden_sha256": digest(GOLDEN),
            "evaluator_sha256": hashlib.sha256((ROOT / "evaluate.py").read_bytes()).hexdigest(),
            "aliases_sha256": digest(ALIASES),
            "gate_policy": GATES, "results": results}


if __name__ == "__main__":
    report = evaluate_all()
    target = ROOT / "reports" / "fixture-observation.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in report["results"]:
        print(row["variant"], row["release"], json.dumps(row["metrics"], ensure_ascii=False))
