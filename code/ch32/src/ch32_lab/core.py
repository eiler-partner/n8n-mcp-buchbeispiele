"""Deterministische Chunk-Grenzen und vergleichbare Zeichen-Basislinie."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SPLITTER_VERSION = "structure-v1"
MAX_CHARS = 170


class ContractError(ValueError):
    pass


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_policy(version_id: str) -> dict:
    if version_id not in {"2026-01", "2026-09"}:
        raise ContractError("unknown_version")
    policy = json.loads((DATA / f"policy_{version_id}.json").read_text(encoding="utf-8"))
    if policy["version_id"] != version_id:
        raise ContractError("fixture_version_mismatch")
    return policy


def source_hash(policy: dict) -> str:
    raw = json.dumps(policy, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return digest(raw)


def sentences(text: str) -> list[str]:
    # Bewusst begrenzte Heuristik für die synthetischen deutschen Sätze.
    return [normalize(part) for part in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", normalize(text))]


def paragraph_chunks(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    result: list[str] = []
    group: list[str] = []
    for sentence in sentences(text):
        if len(sentence) > max_chars:
            raise ContractError("oversize_sentence")
        if group and len(" ".join(group + [sentence])) > max_chars:
            result.append(" ".join(group))
            # Höchstens einen ganzen Satz überlappen, nie ein halbes Wort.
            previous = group[-1]
            group = [previous] if len(previous + " " + sentence) <= max_chars else []
        group.append(sentence)
    if group:
        result.append(" ".join(group))
    return result


def structural_chunks(policy: dict, max_chars: int = MAX_CHARS) -> list[dict]:
    chunks: list[dict] = []
    for section_order, section in enumerate(policy["sections"], 1):
        section_id = section["section_id"]
        parent_id = f"{policy['document_id']}/{section_id}"
        ordinal = 0
        for block in section["blocks"]:
            if block["kind"] == "paragraph":
                parts = paragraph_chunks(block["text"], max_chars)
            elif block["kind"] == "table":
                parts = ["\n".join(normalize(row) for row in block["rows"])]
                if len(parts[0]) > max_chars:
                    raise ContractError("oversize_table")
            else:
                raise ContractError("unknown_block")
            for part in parts:
                ordinal += 1
                text = normalize(part) if block["kind"] == "paragraph" else part
                key = f"{policy['document_id']}|{policy['version_id']}|{section_id}|{ordinal}|{text}"
                chunks.append({
                    "chunk_id": digest(key.encode("utf-8"))[:20],
                    "source_id": policy["source_id"],
                    "document_id": policy["document_id"],
                    "version_id": policy["version_id"],
                    "section_id": section_id,
                    "section_order": section_order,
                    "parent_id": parent_id,
                    "heading": section["heading"],
                    "ordinal": ordinal,
                    "block_kind": block["kind"],
                    "audience": section["audience"],
                    "splitter_version": SPLITTER_VERSION,
                    "text_sha256": digest(text.encode("utf-8")),
                    "text": text,
                })
    return chunks


def fixed_char_preview(policy: dict, size: int = MAX_CHARS) -> dict:
    flat = "\n".join(
        section["heading"] + "\n" + "\n".join(
            block["text"] if block["kind"] == "paragraph" else "\n".join(block["rows"])
            for block in section["blocks"])
        for section in policy["sections"])
    cuts = list(range(size, len(flat), size))
    mid_word = sum(flat[pos - 1].isalpha() and flat[pos].isalpha() for pos in cuts)
    return {"chunk_count": len(cuts) + 1, "mid_word_cuts": mid_word,
            "size_unit": "characters", "character_limit": size}


def preview(version_id: str) -> dict:
    policy = load_policy(version_id)
    chunks = structural_chunks(policy)
    return {"version_id": version_id, "structural_chunk_count": len(chunks),
            "structural_max_chars": max(len(row["text"]) for row in chunks),
            "table_chunk_count": sum(row["block_kind"] == "table" for row in chunks),
            "fixed_baseline": fixed_char_preview(policy),
            "splitter_version": SPLITTER_VERSION}
