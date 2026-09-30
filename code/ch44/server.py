"""Internal n8n bridge; no arbitrary URLs, no model-generated facts."""
from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline import Budget, build_report, validate_report

HERE = Path(__file__).parent
SOURCE_IDS = ("api-quarter", "web-briefing", "file-regions",
              "web-robots-blocked", "web-tdm-blocked", "web-terms-blocked",
              "web-redirect-blocked")


def mcp_read(source_id: str) -> dict:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "read_source", "arguments": {"source_id": source_id},
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                  "io.modelcontextprotocol/clientInfo": {"name": "ch44-gateway", "version": "0.1.0"}}}}
    child = subprocess.run([sys.executable, str(HERE / "mcp_stdio.py")],
                           input=json.dumps(message) + "\n", text=True, capture_output=True,
                           timeout=7, check=True)
    reply = json.loads(child.stdout.strip())
    if "error" in reply:
        raise ValueError("source_tool_failed:" + reply["error"]["message"])
    return reply["result"]["structuredContent"]


def process(body: dict) -> dict:
    if body != {"action": "run"}:
        raise ValueError("invalid_request")
    budget = Budget()
    records = []
    for source_id in SOURCE_IDS:
        budget.reserve_step()
        record = mcp_read(source_id)
        budget.add_bytes(record["transfer_bytes"])
        records.append(record)
    report = build_report(records)
    if not validate_report(report, records):
        raise ValueError("lineage_invalid")
    return {**report, "budget": budget.observation(), "path": "n8n-mcp-readonly"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(200, {"status": "ok"}) if self.path == "/health" else self.respond(404, {"code": "not_found"})

    def do_POST(self):
        if self.path != "/research":
            self.respond(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("invalid_body_size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("invalid_request")
            self.respond(200, process(body))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.respond(422, {"code": str(exc)})
        except (subprocess.SubprocessError, TimeoutError):
            self.respond(503, {"code": "source_unavailable"})

    def respond(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8145), Handler).serve_forever()
