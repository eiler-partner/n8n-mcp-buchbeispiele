"""Kleiner HTTP-Adapter für n8n; nur auf localhost veröffentlichen."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lab import ContractError, query, seed


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.respond(200, {"status": "ok"})

    def do_POST(self):
        if self.path != "/operate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16384:
                raise ContractError("body_too_large")
            payload = json.loads(self.rfile.read(length))
            action = payload.get("action")
            if action == "seed":
                result = seed(payload.get("model_id"))
            elif action == "query":
                result = query(payload)
            else:
                raise ContractError("unknown_action")
            self.respond(200, result)
        except (ValueError, TypeError, KeyError) as exc:
            self.respond(422, {"code": str(exc)})
        except Exception as exc:
            self.respond(500, {"code": type(exc).__name__})

    def respond(self, status: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8133), Handler).serve_forever()
