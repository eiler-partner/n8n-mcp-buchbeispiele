"""Synthetischer, extraktiver Wissenspfad. Keine Produktions-Identitaet oder Embeddings."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import time
from pathlib import Path

DATA = Path(__file__).parent / "data" / "handbook.json"
WORD = re.compile(r"[\wäöüÄÖÜß]+", re.UNICODE)
REFUSAL = "Dazu liegt mir keine freigegebene, belastbare Textstelle vor."
PROTOCOL = "2026-07-28"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sign(claims: dict, key: bytes) -> str:
    raw = base64.urlsafe_b64encode(canonical(claims)).rstrip(b"=").decode()
    mac = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{mac}"


def identity(token: str, key: bytes) -> dict:
    try:
        raw, mac = token.split(".")
        expected = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("invalid_token")
        claims = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        groups = claims.get("groups")
        if (claims.get("aud") != "ch43-knowledge" or claims.get("exp", 0) <= time.time()
                or not isinstance(claims.get("tenant"), str) or not claims["tenant"]
                or not isinstance(groups, list) or not groups
                or not all(isinstance(group, str) and group for group in groups)
                or not claims.get("sub")):
            raise ValueError("invalid_token")
        return claims
    except (AttributeError, TypeError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise ValueError("invalid_token") from exc


def corpus(path: Path = DATA) -> tuple[list[dict], list[dict]]:
    source = json.loads(path.read_text(encoding="utf-8"))
    if source.get("schema") != "ch43-handbook-v1":
        raise ValueError("invalid_schema")
    current = set()
    chunks, quarantine = [], []
    for doc in source["documents"]:
        key = (doc["tenant"], doc["id"])
        if doc["current"]:
            if key in current:
                raise ValueError("duplicate_current_version")
            current.add(key)
        if not doc["current"]:
            continue
        if doc["source_type"] not in ("text", "ocr"):
            quarantine.append({"source_id": doc["id"], "reason": "untrusted_source"})
            continue
        if doc["source_type"] == "ocr" and doc["ocr_confidence"] < 0.85:
            quarantine.append({"source_id": doc["id"], "reason": "ocr_quality"})
            continue
        if not doc["groups"] or not doc["tenant"]:
            raise ValueError("missing_acl")
        for section in doc["sections"]:
            text = section["text"].strip()
            if not text:
                raise ValueError("empty_section")
            chunks.append({"source_id": doc["id"], "version": doc["version"],
                           "tenant": doc["tenant"], "groups": doc["groups"],
                           "title": doc["title"], "section": section["id"],
                           "text": text, "sha256": digest(text)})
    return chunks, quarantine


def words(value: str) -> set[str]:
    return set(WORD.findall(value.casefold()))


def trigrams(value: str) -> set[str]:
    compact = " ".join(WORD.findall(value.casefold()))
    return {compact[i:i + 3] for i in range(max(0, len(compact) - 2))}


def authorized(chunk: dict, actor: dict) -> bool:
    return chunk["tenant"] == actor["tenant"] and bool(set(chunk["groups"]) & set(actor["groups"]))


def retrieve(question: str, actor: dict, *, path: Path = DATA, limit: int = 3) -> list[dict]:
    if not isinstance(question, str) or not 2 <= len(question.strip()) <= 300:
        raise ValueError("invalid_question")
    qwords, qgrams = words(question), trigrams(question)
    all_chunks, _ = corpus(path)
    ranked = []
    # SECURITY: ACL before either scorer or result truncation; no raw document endpoint.
    for chunk in (c for c in all_chunks if authorized(c, actor)):
        cwords = words(chunk["title"] + " " + chunk["text"])
        lexical = len(qwords & cwords) / max(1, len(qwords))
        cgrams = trigrams(chunk["title"] + " " + chunk["text"])
        character = len(qgrams & cgrams) / math.sqrt(max(1, len(qgrams) * len(cgrams)))
        if lexical < 0.18 and character < 0.42:
            continue
        score = round(0.7 * lexical + 0.3 * character, 6)
        ranked.append((score, chunk))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["source_id"], pair[1]["section"]))
    return [dict(chunk, score=score) for score, chunk in ranked[:limit]]


def validate_answer(answer: dict, candidates: list[dict], actor: dict, *, path: Path = DATA) -> bool:
    if not isinstance(answer, dict) or not isinstance(answer.get("quote"), str):
        return False
    citation = answer.get("citation")
    if not isinstance(citation, dict) or set(citation) != {"source_id", "version", "section", "sha256"}:
        return False
    matching = [c for c in candidates if all(c.get(k) == v for k, v in citation.items())]
    if len(matching) != 1 or not authorized(matching[0], actor):
        return False
    fresh, _ = corpus(path)
    key = (citation["source_id"], citation["version"], citation["section"], citation["sha256"])
    if not any((c["source_id"], c["version"], c["section"], c["sha256"]) == key
               and authorized(c, actor) for c in fresh):
        return False
    return answer["quote"] == matching[0]["text"] and digest(answer["quote"]) == citation["sha256"]


def forbidden_candidates(candidates: list[dict], actor: dict, *, path: Path = DATA) -> list[dict]:
    """Candidates outside the actor's view: other tenant, missing group, old version or blocked source."""
    fresh, _ = corpus(path)
    allowed = {(c["source_id"], c["version"], c["section"], c["sha256"])
               for c in fresh if authorized(c, actor)}
    return [{k: c.get(k) for k in ("source_id", "version", "section")} for c in candidates
            if (c.get("source_id"), c.get("version"), c.get("section"), c.get("sha256")) not in allowed]


def unauthorized_retrieval(runs: dict[str, tuple[dict, list[dict]]], *, path: Path = DATA) -> dict:
    """Queries with >= 1 forbidden candidate before the answer gate / ALL queries (positive and negative)."""
    if not runs:
        raise ValueError("no_queries")
    leaks = {}
    for name, (actor, candidates) in runs.items():
        forbidden = forbidden_candidates(candidates, actor, path=path)
        if forbidden:
            leaks[name] = forbidden
    return {"queries": len(runs), "queries_with_forbidden_candidate": len(leaks),
            "rate": round(len(leaks) / len(runs), 4), "forbidden_candidates": leaks}


def answer(question: str, actor: dict, candidates: list[dict], *, path: Path = DATA) -> dict:
    if not candidates:
        return {"status": "refused", "answer": REFUSAL, "citations": []}
    top = candidates[0]
    output = {"quote": top["text"], "citation": {k: top[k] for k in ("source_id", "version", "section", "sha256")}}
    if not validate_answer(output, candidates, actor, path=path):
        return {"status": "refused", "answer": REFUSAL, "citations": []}
    return {"status": "answered", "answer": output["quote"], "citations": [output["citation"]]}


def signing_key() -> bytes:
    value = os.getenv("CH43_SIGNING_KEY", "")
    if len(value) < 32:
        raise RuntimeError("CH43_SIGNING_KEY must be at least 32 characters")
    return value.encode()
