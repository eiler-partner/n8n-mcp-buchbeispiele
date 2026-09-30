"""Datierter End-to-End-Prüflauf mit echtem n8n, Poppler, OCR und MCP-Resource-Subset."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEBHOOK = "http://127.0.0.1:15731/webhook/ch31-ingest"
API = "http://127.0.0.1:8131"


def post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


observed = []
for case_id, status, method in (("digital", "accepted", "text"),
                                ("scan_good", "accepted", "ocr"),
                                ("scan_cropped", "quarantined", "ocr")):
    code, report = post(WEBHOOK, {"case_id": case_id, "declared_mime": "application/pdf"})
    assert code == 200, (case_id, code, report)
    assert (report["status"], report["method"]) == (status, method), report
    assert len(report["source_sha256"]) == 64
    if status == "accepted":
        assert not report["reason_codes"], report
    else:
        assert "missing_required_phrase" in report["reason_codes"], report
        assert "15 Arbeitstage" in report["missing_phrases"]
    observed.append(report)
    print(f"PASS n8n {case_id}: {status}, {method}, CER={report['character_error_rate']}")

code, duplicate = post(WEBHOOK, {"case_id": "digital", "declared_mime": "application/pdf"})
assert code == 200 and duplicate["duplicate"] is True and duplicate["status"] == "accepted"
print("PASS duplicate bytes: no second record")

negative = []
for payload, expected in (({"case_id": "digital", "declared_mime": "text/plain"}, "mime_mismatch"),
                          ({"case_id": "unknown"}, "unknown_case")):
    code, response = post(f"{API}/inspect", payload)
    assert (code, response["code"]) == (422, expected), response
    negative.append(expected)
code, response = post(f"{API}/ingest", {"case_id": "digital", "expected_sha256": "0" * 64})
assert (code, response["code"]) == (422, "source_changed"), response
negative.append("source_changed")

meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "ch31-verifier", "version": "0.1.0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def mcp(message: dict) -> dict:
    proc = subprocess.run(["docker", "compose", "exec", "-T", "ingestion",
                           "python", "-m", "ch31_lab.mcp_stdio"],
                          input=json.dumps(message) + "\n", capture_output=True,
                          text=True, check=True, timeout=30)
    return json.loads(proc.stdout.strip())


listing = mcp({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {"_meta": meta}})
resources = listing["result"]["resources"]
current_hashes = {row["source_sha256"][:16] for row in observed if row["status"] == "accepted"}
current_resources = [item for item in resources
                     if item["uri"].rsplit("/", 1)[-1] in current_hashes]
assert len(current_resources) == 2, resources
assert {item["name"] for item in current_resources} == {"digital", "scan_good"}
assert all(item["name"] != "scan_cropped" for item in resources), resources
reading = mcp({"jsonrpc": "2.0", "id": 2, "method": "resources/read",
               "params": {"_meta": meta, "uri": current_resources[0]["uri"]}})
assert "15 Arbeitstage" in reading["result"]["contents"][0]["text"]
bad_uri = ("ingest://RICHTLINIE-31/2026-09/" +
           next(row for row in observed if row["case_id"] == "scan_cropped")["source_sha256"][:16])
denied = mcp({"jsonrpc": "2.0", "id": 3, "method": "resources/read",
              "params": {"_meta": meta, "uri": bad_uri}})
assert denied["error"]["code"] == -32602
print("PASS MCP: accepted list/read, quarantined read denied")


def version(*args: str) -> str:
    proc = subprocess.run(["docker", "compose", "exec", "-T", "ingestion", *args],
                          capture_output=True, text=True, check=True, timeout=20)
    return (proc.stdout or proc.stderr).splitlines()[0]


report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
          "synthetic_data_only": True,
          "tools": {"pdftotext": version("pdftotext", "-v"),
                    "tesseract": version("tesseract", "--version")},
          "cases": observed, "duplicate_check": True,
          "negative_contract_checks": negative,
          "mcp_resource_checks": ["list_accepted_only", "read_accepted", "deny_quarantined"]}
Path("reports").mkdir(exist_ok=True)
Path("reports/live-observation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("PASS chapter 31 live; report: reports/live-observation.json")
