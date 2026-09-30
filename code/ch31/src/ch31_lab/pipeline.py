"""Begrenzter PDF-Pfad: Textlayer oder Raster+Tesseract, danach Qualitäts-Gate."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from .core import ContractError, decide, normalize, sha256

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "fixtures"


def _run(*args: str) -> str:
    try:
        completed = subprocess.run(args, check=True, capture_output=True, text=True,
                                   timeout=30)
        return completed.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ContractError("parser_failed") from exc


def _ocr(pdf: Path) -> tuple[str, float | None]:
    with tempfile.TemporaryDirectory(prefix="ch31-ocr-") as temp:
        prefix = Path(temp) / "page"
        _run("pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-r", "300",
             "-png", str(pdf), str(prefix))
        image = prefix.with_suffix(".png")
        text = _run("tesseract", str(image), "stdout", "-l", "deu", "--psm", "6")
        tsv = _run("tesseract", str(image), "stdout", "-l", "deu", "--psm", "6", "tsv")
        confidence = []
        for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
            if row.get("level") == "5" and row.get("text", "").strip():
                value = float(row["conf"])
                if value >= 0:
                    confidence.append(value)
        return text, round(sum(confidence) / len(confidence), 2) if confidence else None


def inspect(case_id: str, declared_mime: str = "application/pdf") -> tuple[dict, str]:
    if case_id not in CASES["cases"]:
        raise ContractError("unknown_case")
    if declared_mime != "application/pdf":
        raise ContractError("mime_mismatch")
    fixture = FIXTURES / CASES["cases"][case_id]["file"]
    payload = fixture.read_bytes()
    if not payload.startswith(b"%PDF-") or len(payload) > 8_000_000:
        raise ContractError("invalid_pdf")
    info = _run("pdfinfo", str(fixture))
    if not re.search(r"^Pages:\s+1\s*$", info, re.MULTILINE):
        raise ContractError("page_limit")
    extracted = _run("pdftotext", "-enc", "UTF-8", "-layout", str(fixture), "-")
    if len(normalize(extracted)) >= 30:
        method, text, confidence = "text", extracted, None
    else:
        method = "ocr"
        text, confidence = _ocr(fixture)
    reference = " ".join(CASES["lines"])
    quality = decide(text, reference, CASES["required_phrases"], method, confidence)
    normalized = normalize(text)
    report = {
        "case_id": case_id, "source_id": CASES["source_id"],
        "document_id": CASES["document_id"], "version": CASES["version"],
        "file_name": fixture.name, "declared_mime": declared_mime,
        "source_sha256": sha256(payload), "method": method,
        "page_count": 1, "language": "deu" if method == "ocr" else "not_applicable",
        **quality,
    }
    return report, normalized


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS records (
                source_sha256 TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                report_json TEXT NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def ingest(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"case_id", "declared_mime", "expected_sha256"}:
            raise ContractError("invalid_request")
        report, text = inspect(payload.get("case_id"),
                               payload.get("declared_mime", "application/pdf"))
        if payload.get("expected_sha256") is not None and payload["expected_sha256"] != report["source_sha256"]:
            raise ContractError("source_changed")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT report_json FROM records WHERE source_sha256=?",
                                  (report["source_sha256"],)).fetchone()
            if existing:
                return json.loads(existing[0]) | {"duplicate": True}
            db.execute("""INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)""",
                       (report["source_sha256"], report["case_id"],
                        report["document_id"], report["version"],
                        report["status"], text if report["status"] == "accepted" else "",
                        json.dumps(report, ensure_ascii=False)))
        return report | {"duplicate": False}

    def accepted(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT source_sha256, case_id, document_id, version,
                                      normalized_text FROM records WHERE status='accepted'
                                      ORDER BY case_id""").fetchall()
        return [dict(zip(("source_sha256", "case_id", "document_id", "version", "text"), row))
                for row in rows]
