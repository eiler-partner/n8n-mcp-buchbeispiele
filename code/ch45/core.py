"""Deterministic, synthetic control checks; no legal interpretation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CATALOG_FILES = {
    "catalog://supplier-review/v1": DATA / "catalog-v1.json",
    "catalog://supplier-review/v2": DATA / "catalog-v2.json",
}
DOCUMENT_FILES = (DATA / "supplier-profile.md", DATA / "supplier-contract.md")
REGULATORY_FILE = DATA / "regulatory-sources.json"
STATUS = {"fulfilled", "partial", "not_evidenced", "not_applicable"}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def resource_uris() -> list[str]:
    sources = json.loads(REGULATORY_FILE.read_text(encoding="utf-8"))["sources"]
    return [*CATALOG_FILES, *(item["uri"] for item in sources)]


def read_resource(uri: str) -> str:
    if uri in CATALOG_FILES:
        return CATALOG_FILES[uri].read_text(encoding="utf-8")
    sources = json.loads(REGULATORY_FILE.read_text(encoding="utf-8"))["sources"]
    for item in sources:
        if uri == item["uri"]:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)
    raise ValueError("resource_not_allowlisted")


def parse_document(raw: bytes) -> dict:
    if len(raw) > 65536:
        raise ValueError("document_too_large")
    text = raw.decode("utf-8", errors="strict")
    lines = text.splitlines()
    if len(lines) < 4:
        raise ValueError("document_header_missing")
    meta = {}
    for key, line in zip(("DOC-ID", "VERSION", "ISSUED-AT"), lines[:3]):
        if not line.startswith(key + ": "):
            raise ValueError("document_header_invalid")
        meta[key] = line.split(": ", 1)[1]
    if not re.fullmatch(r"[a-z0-9-]+", meta["DOC-ID"]):
        raise ValueError("document_id_invalid")
    if not re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", meta["ISSUED-AT"]):
        raise ValueError("issued_at_invalid")
    article = paragraph = None
    entries = []
    seen = set()
    for line in lines[3:]:
        if not line.strip():
            continue
        if match := re.fullmatch(r"## § ([0-9]+) .+", line):
            article, paragraph = match.group(1), None
        elif match := re.fullmatch(r"### Absatz ([0-9]+)", line):
            if article is None:
                raise ValueError("paragraph_without_article")
            paragraph = match.group(1)
        elif match := re.fullmatch(r"- Ziffer ([0-9]+): (.+)", line):
            if article is None or paragraph is None:
                raise ValueError("item_without_structure")
            locator = f"§ {article}/Abs. {paragraph}/Ziff. {match.group(1)}"
            if locator in seen:
                raise ValueError("duplicate_locator")
            seen.add(locator)
            entries.append({"locator": locator, "text": match.group(2)})
        else:
            raise ValueError("unstructured_document_line")
    if not entries:
        raise ValueError("document_empty")
    return {"document_id": meta["DOC-ID"], "version": meta["VERSION"],
            "issued_at_utc": meta["ISSUED-AT"], "raw_sha256": digest(raw),
            "entries": entries}


def validate_catalog(catalog: dict, sources: dict) -> None:
    if catalog.get("mapping_status") != "illustrative_internal_rules_not_legal_interpretation":
        raise ValueError("catalog_mapping_status_missing")
    by_uri = {row["uri"]: row for row in sources["sources"]}
    ids = set()
    for control in catalog["controls"]:
        if control["id"] in ids:
            raise ValueError("duplicate_control")
        ids.add(control["id"])
        ref = by_uri.get(control["source_uri"])
        if not ref or control["source_locator"] not in ref["locators"]:
            raise ValueError("regulatory_source_unversioned_or_missing")
        if not control.get("required_terms") or not control.get("topic"):
            raise ValueError("control_contract_invalid")


def evidence(document: dict, entry: dict) -> dict:
    return {"document_id": document["document_id"], "document_version": document["version"],
            "raw_sha256": document["raw_sha256"], "locator": entry["locator"],
            "quote": entry["text"]}


def evaluate(control: dict, documents: list[dict], source: dict) -> dict:
    rows = [(doc, entry) for doc in documents for entry in doc["entries"]
            if control["topic"] in entry["text"].casefold()]
    applicable = control.get("not_applicable_if")
    exclusions = [(doc, entry) for doc, entry in rows
                  if applicable and applicable in entry["text"].casefold()]
    flags = []
    if exclusions:
        status, support, coverage = "not_applicable", exclusions, 1.0
        flags.append("applicability_requires_human_confirmation")
    elif not rows:
        status, support, coverage = "not_evidenced", [], 0.0
    else:
        terms = control["required_terms"]
        scored = [(sum(term in entry["text"].casefold() for term in terms), doc, entry)
                  for doc, entry in rows]
        best = max(score for score, _, _ in scored)
        status = "fulfilled" if best == len(terms) else "partial"
        support = rows
        coverage = round(best / len(terms), 2)
        if pattern := control.get("conflict_pattern"):
            values = {match.group(1) for _, entry in rows
                      if (match := re.search(pattern, entry["text"].casefold()))}
            if len(values) > 1:
                status = "partial"
                flags.append("contradictory_documents")
    if status in {"fulfilled", "partial", "not_applicable"} and not support:
        raise ValueError("evidence_required")
    return {"control_id": control["id"], "title": control["title"], "status": status,
            "evidence_coverage": coverage, "flags": flags,
            "source": {"uri": source["uri"], "version": source["version"],
                       "eli": source["eli"], "locator": control["source_locator"],
                       "mapping_status": source["mapping_status"]},
            "evidence": [evidence(doc, entry) for doc, entry in support],
            "assessment_kind": "deterministic_candidate_not_legal_decision"}


def build_report(catalog: dict, sources: dict, documents: list[dict]) -> dict:
    validate_catalog(catalog, sources)
    by_uri = {row["uri"]: row for row in sources["sources"]}
    controls = [evaluate(c, documents, by_uri[c["source_uri"]]) for c in catalog["controls"]]
    body = {"catalog_id": catalog["catalog_id"], "catalog_version": catalog["version"],
            "catalog_sha256": digest(canonical(catalog)),
            "document_manifest": [{key: doc[key] for key in
                ("document_id", "version", "issued_at_utc", "raw_sha256")} for doc in documents],
            "controls": controls,
            "open_control_ids": [c["control_id"] for c in controls if c["status"] != "fulfilled"],
            "result_kind": "review_draft_not_compliance_certification"}
    body["document_set_sha256"] = digest(canonical(body["document_manifest"]))
    body["report_sha256"] = digest(canonical(body))
    return body


def load_documents() -> list[dict]:
    return [parse_document(path.read_bytes()) for path in DOCUMENT_FILES]


def local_report(catalog_uri: str = "catalog://supplier-review/v1") -> dict:
    catalog = json.loads(read_resource(catalog_uri))
    sources = {"sources": [json.loads(read_resource(uri)) for uri in resource_uris()
                            if uri.startswith("regulation://")]}
    return build_report(catalog, sources, load_documents())
