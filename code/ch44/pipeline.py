"""Deterministic extraction, profiling, deduplication and lineage validation."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import StringIO

METRICS = {"orders": "Bestellungen", "returns": "Retouren",
           "delivery_days": "Lieferdauer"}
UNITS = {"count": "Anzahl", "days": "Tage"}


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def value_text(value: object) -> str:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_numeric_value") from exc
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("invalid_numeric_value")
    return format(decimal.normalize(), "f")


def timestamp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp_without_timezone")
    return value


class MetricHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metrics: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag != "span":
            return
        values = dict(attrs)
        if "data-metric" in values:
            self.metrics.append({"name": values.get("data-metric"),
                                 "value": values.get("data-value"),
                                 "unit": values.get("data-unit")})


def parsed_metrics(record: dict) -> tuple[list[dict], dict]:
    media = record["media_type"]
    raw = record["raw_text"]
    if media == "application/json":
        document = json.loads(raw)
        if document.get("dataset") != "synthetic-quarter-2026-q2":
            raise ValueError("wrong_dataset")
        if timestamp(document.get("published_at_utc")) != record["published_at_utc"]:
            raise ValueError("publication_mismatch")
        metrics = document["metrics"]
        return [dict(item, locator=f"/metrics/{index}", parse_step="parse_json")
                for index, item in enumerate(metrics)], {}
    if media == "text/html":
        parser = MetricHTML()
        parser.feed(raw)
        if not parser.metrics:
            raise ValueError("no_html_metrics")
        return [dict(item, locator=f"span[data-metric]/{index}", parse_step="parse_html")
                for index, item in enumerate(parser.metrics)], {}
    if media == "text/csv":
        rows = list(csv.DictReader(StringIO(raw)))
        if not rows or any(set(row) != {"region", "orders", "returns", "published_at_utc"} for row in rows):
            raise ValueError("invalid_csv_schema")
        if any(timestamp(row["published_at_utc"]) != record["published_at_utc"] for row in rows):
            raise ValueError("publication_mismatch")
        missing = sum(not value for row in rows for value in row.values())
        if missing:
            raise ValueError("missing_csv_cell")
        names = [row["region"] for row in rows]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_region")
        totals = {}
        for name in ("orders", "returns"):
            values = [int(row[name]) for row in rows]
            if any(value < 0 for value in values):
                raise ValueError("negative_csv_count")
            totals[name] = sum(values)
        metrics = [dict(name=name, value=total, unit="count", locator=f"sum({name})",
                        parse_step="sum_csv_rows") for name, total in totals.items()]
        return metrics, {"csv_rows": len(rows), "csv_missing_cells": missing}
    raise ValueError("unsupported_media_type")


def evidence(record: dict, metric: dict) -> dict:
    return {"source_id": record["source_id"], "uri": record["uri"],
            "retrieved_at_utc": record["retrieved_at_utc"],
            "published_at_utc": record["published_at_utc"],
            "raw_sha256": record["raw_sha256"], "locator": metric["locator"],
            "steps": ["read_source", metric["parse_step"], "normalize", "deduplicate"]}


def build_report(records: list[dict]) -> dict:
    ids = [record["source_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_source")
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    csv_rows = 0
    missing = 0
    manifest = []
    for record in records:
        timestamp(record["retrieved_at_utc"])
        if record["status"] == "blocked":
            if record.get("raw_text") or record.get("raw_sha256"):
                raise ValueError("blocked_source_leaked")
            manifest.append({"source_id": record["source_id"], "status": "blocked",
                             "reason": record["reason"],
                             "retrieved_at_utc": record["retrieved_at_utc"]})
            continue
        if record["status"] != "accepted":
            raise ValueError("invalid_source_status")
        timestamp(record["published_at_utc"])
        if hashlib.sha256(record["raw_text"].encode()).hexdigest() != record["raw_sha256"]:
            raise ValueError("source_digest_mismatch")
        metrics, profile = parsed_metrics(record)
        csv_rows += profile.get("csv_rows", 0)
        missing += profile.get("csv_missing_cells", 0)
        manifest.append({key: record[key] for key in ("source_id", "status", "uri",
                         "media_type", "retrieved_at_utc", "published_at_utc", "raw_sha256")})
        for metric in metrics:
            name, unit = metric["name"], metric["unit"]
            if name not in METRICS or unit not in UNITS:
                raise ValueError("unknown_metric_or_unit")
            if (name == "delivery_days" and unit != "days") or (name != "delivery_days" and unit != "count"):
                raise ValueError("unit_mismatch")
            key = (name, value_text(metric["value"]), unit)
            grouped.setdefault(key, []).append(evidence(record, metric))
    statements = []
    for name in sorted({key[0] for key in grouped}):
        claims = []
        for key in sorted(k for k in grouped if k[0] == name):
            ev = sorted(grouped[key], key=lambda row: (row["source_id"], row["locator"]))
            claims.append({"claim_id": hashlib.sha256(canonical(key)).hexdigest()[:16],
                           "value": key[1], "unit": key[2], "evidence": ev})
        if len(claims) > 1:
            status = "conflicted"
            values = " und ".join(claim["value"].replace(".", ",") for claim in claims)
            text = f"{METRICS[name]}: {values}; die Quellen widersprechen sich."
        else:
            status = "multi_source" if len(claims[0]["evidence"]) > 1 else "single_source"
            suffix = "in mehreren Quellen vorhanden" if status == "multi_source" else "nur eine Quelle"
            human_value = claims[0]["value"].replace(".", ",")
            if claims[0]["unit"] == "days":
                human_value += " Tage"
            text = f"{METRICS[name]}: {human_value} ({suffix})."
        statements.append({"statement_id": name, "status": status, "text": text, "claims": claims})
    if not statements:
        raise ValueError("no_accepted_facts")
    return {"schema": "ch44-briefing-v1", "status": "review_required" if any(
            row["status"] == "conflicted" for row in statements) else "ready_for_editorial_review",
            "statements": statements, "sources": manifest,
            "profile": {"source_count": len(records),
                        "accepted_count": sum(r["status"] == "accepted" for r in records),
                        "blocked_count": sum(r["status"] == "blocked" for r in records),
                        "duplicate_groups": sum(len(items) > 1 for items in grouped.values()),
                        "conflict_metrics": sum(s["status"] == "conflicted" for s in statements),
                        "csv_rows": csv_rows, "csv_missing_cells": missing}}


def validate_report(report: dict, records: list[dict]) -> bool:
    try:
        expected = build_report(records)
    except (KeyError, TypeError, ValueError):
        return False
    return report == expected


@dataclass
class Budget:
    max_steps: int = 7
    max_bytes: int = 131072
    max_seconds: float = 20.0
    started: float = field(default_factory=time.monotonic)
    steps: int = 0
    bytes_read: int = 0

    def reserve_step(self):
        if self.steps + 1 > self.max_steps or time.monotonic() - self.started > self.max_seconds:
            raise ValueError("budget_exceeded")
        self.steps += 1

    def add_bytes(self, count: int):
        self.bytes_read += count
        if self.bytes_read > self.max_bytes or time.monotonic() - self.started > self.max_seconds:
            raise ValueError("budget_exceeded")

    def observation(self) -> dict:
        return {"steps": self.steps, "bytes_read": self.bytes_read,
                "elapsed_ms": round((time.monotonic() - self.started) * 1000, 2),
                "limits": {"max_steps": self.max_steps, "max_bytes": self.max_bytes,
                           "max_seconds": self.max_seconds}}
