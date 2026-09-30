"""Lokaler Bridge-/Telemetry-Dienst; nur synthetische Daten, keine Provider-API."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from core import inspect_trace, service_sli, synthetic_cost_micro_usd

EVENTS: list[dict] = []
LOCK = threading.Lock()


def record(body: dict) -> None:
    row = {key: body.get(key) for key in
           ("request_id", "correlation_id", "stage", "parent_stage", "duration_ms", "status")}
    row["at_utc"] = datetime.now(timezone.utc).isoformat()
    with LOCK:
        EVENTS.append(row)
    print(json.dumps({"event": "trace_stage", **row}), flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return  # Kein Request-Body und keine Querywerte in Access-Logs.

    def send(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        if n < 0 or n > 8192:
            raise ValueError("body_size")
        value = json.loads(self.rfile.read(n))
        if not isinstance(value, dict):
            raise ValueError("body_shape")
        return value

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send(200, {"ok": True})
        elif self.path.startswith("/report/"):
            rid = unquote(self.path.removeprefix("/report/"))
            with LOCK:
                rows = list(EVENTS)
            report = inspect_trace(rows, rid)
            report["business_ok"] = any(r.get("request_id") == rid and r.get("stage") == "model"
                                        and r.get("status") == "ok" for r in rows)
            self.send(200, report)
        elif self.path == "/events":
            with LOCK:
                rows = list(EVENTS)
            self.send(200, {"events": rows})
        elif self.path == "/sli":
            with LOCK:
                rows = list(EVENTS)
            ids = sorted({r["request_id"] for r in rows if r.get("stage") == "n8n"})
            reports = []
            for rid in ids:
                report = inspect_trace(rows, rid)
                report["business_ok"] = any(r.get("request_id") == rid and r.get("stage") == "model"
                                            and r.get("status") == "ok" for r in rows)
                reports.append(report)
            self.send(200, service_sli(reports))
        else:
            self.send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            body = self.read_body()
            if self.path == "/reset":
                with LOCK:
                    EVENTS.clear()
                self.send(200, {"ok": True})
                return
            if self.path == "/trace/start":
                if not body.get("request_id") or not body.get("correlation_id"):
                    raise ValueError("missing_correlation")
                record({"request_id": body["request_id"],
                        "correlation_id": body["correlation_id"], "stage": "n8n",
                        "parent_stage": None, "duration_ms": 0, "status": "accepted"})
                self.send(200, {"request_id": body["request_id"],
                                "correlation_id": body["correlation_id"],
                                "break_trace": bool(body.get("break_trace")),
                                "model_error": bool(body.get("model_error"))})
                return
            if self.path == "/internal/event":
                record(body)
                self.send(200, {"ok": True})
                return
            if self.path == "/internal/retrieve":
                start = time.monotonic()
                record({"request_id": body["request_id"],
                        "correlation_id": body["correlation_id"], "stage": "retrieval",
                        "parent_stage": "mcp", "duration_ms": (time.monotonic()-start)*1000,
                        "status": "ok"})
                self.send(200, {"evidence_id": "synthetic-policy-v1"})
                return
            if self.path == "/internal/model":
                bad = bool(body.get("model_error"))
                record({"request_id": body["request_id"],
                        "correlation_id": None if body.get("break_trace") else body["correlation_id"],
                        "stage": "model", "parent_stage": "mcp", "duration_ms": 3,
                        "status": "error" if bad else "ok"})
                self.send(200, {"status": "error" if bad else "ok",
                                "answer": None if bad else "Die synthetische Frist beträgt 14 Tage.",
                                "evidence_id": body["evidence_id"],
                                "usage": {"input_tokens": 120, "output_tokens": 30,
                                          "synthetic_cost_micro_usd": synthetic_cost_micro_usd(120, 30)}})
                return
            if self.path == "/mcp/execute":
                if not body.get("request_id") or not body.get("correlation_id"):
                    raise ValueError("missing_correlation")
                messages = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "ch40-bridge", "version": "0.1.0"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                        "name": "answer_from_fixture", "arguments": body}},
                ]
                run = subprocess.run(["python", "mcp_stdio.py"],
                    input="\n".join(json.dumps(m) for m in messages)+"\n",
                    text=True, capture_output=True, timeout=15, check=True)
                outputs = [json.loads(line) for line in run.stdout.splitlines()]
                if len(outputs) != 3 or outputs[0].get("result", {}).get("protocolVersion") != "2025-06-18":
                    raise ValueError("mcp_handshake_failed")
                if outputs[1]["result"]["tools"][0]["name"] != "answer_from_fixture":
                    raise ValueError("mcp_discovery_failed")
                result = outputs[2]["result"]
                model = json.loads(result["content"][0]["text"])
                self.send(200, {"request_id": body["request_id"], "correlation_id": body["correlation_id"],
                                "mcp_error": result["isError"], **model})
                return
            self.send(404, {"error": "not_found"})
        except (ValueError, KeyError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            self.send(400, {"error": type(exc).__name__})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8140), Handler).serve_forever()
