"""Typprüfung, Normalisierung und synthetische Qualitätsregeln."""

from __future__ import annotations

import hashlib
import re
import unicodedata


class ContractError(ValueError):
    pass


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def character_error_rate(reference: str, candidate: str) -> float:
    """Levenshtein-Distanz je Referenzzeichen; nur bei bekanntem Goldtext."""
    reference, candidate = normalize(reference).casefold(), normalize(candidate).casefold()
    if not reference:
        raise ContractError("empty_reference")
    previous = list(range(len(candidate) + 1))
    for i, original in enumerate(reference, 1):
        current = [i]
        for j, observed in enumerate(candidate, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (original != observed)))
        previous = current
    return previous[-1] / len(reference)


def decide(text: str, reference: str, required_phrases: list[str], method: str,
           mean_confidence: float | None) -> dict:
    normalized = normalize(text)
    missing = [phrase for phrase in required_phrases
               if normalize(phrase).casefold() not in normalized.casefold()]
    cer = round(character_error_rate(reference, normalized), 4)
    problems = []
    if len(normalized) < 80:
        problems.append("too_short")
    if missing:
        problems.append("missing_required_phrase")
    if cer > 0.12:
        problems.append("high_character_error_rate")
    if method == "ocr" and (mean_confidence is None or mean_confidence < 70):
        problems.append("low_ocr_confidence")
    return {"status": "quarantined" if problems else "accepted",
            "reason_codes": problems, "missing_phrases": missing,
            "character_error_rate": cer,
            "mean_ocr_word_confidence": mean_confidence,
            "normalized_chars": len(normalized),
            "normalized_text_sha256": sha256(normalized.encode("utf-8"))}
