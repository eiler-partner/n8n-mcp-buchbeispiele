"""Internal-only bridge: n8n -> fresh MCP subprocess -> strict answer gate."""
from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from core import PROTOCOL, answer, identity, signing_key

HERE = Path(__file__).parent


def process(body: dict) -> dict:
    if set(body) != {"question", "actor_token"}:
        raise ValueError("invalid_request")
    actor = identity(body["actor_token"], signing_key())
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "search_evidence", "arguments": body,
        "_meta": {"io.modelcontextprotocol/protocolVersion": PROTOCOL,
                  "io.modelcontextprotocol/clientInfo": {"name": "ch43-gateway", "version": "0.1.0"}}}}
    child = subprocess.run([sys.executable, str(HERE / "mcp_stdio.py")],
                           input=json.dumps(message) + "\n", text=True, capture_output=True,
                           timeout=8, check=True)
    reply = json.loads(child.stdout.strip())
    if "error" in reply:
        raise ValueError("retrieval_rejected")
    candidates = reply["result"]["structuredContent"]["candidates"]
    result = answer(body["question"], actor, candidates)
    return {**result, "retrieved_count": len(candidates), "path": "n8n-mcp-extractive"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(200, {"status": "ok"}) if self.path == "/health" else self.respond(404, {"code": "not_found"})

    def do_POST(self):
        if self.path != "/ask":
            self.respond(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("invalid_body_size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("invalid_request")
            self.respond(200, process(body))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.respond(422, {"code": str(exc)})
        except (subprocess.SubprocessError, TimeoutError):
            self.respond(503, {"code": "retrieval_unavailable"})

    def respond(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args):
        # Do not log tokens or questions in this teaching server.
        return


if __name__ == "__main__":
    signing_key()
    ThreadingHTTPServer(("0.0.0.0", 8143), Handler).serve_forever()
