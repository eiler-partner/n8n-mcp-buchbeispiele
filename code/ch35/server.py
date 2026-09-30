"""Nur loopback-exponierter, nicht authentifizierter Lehrdienst."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lab import ContractError, answer, context, validate_claims


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "ok"})
        else:
            self.respond(404, {"code": "not_found"})

    def do_POST(self):
        if self.path != "/operate":
            self.respond(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ContractError("invalid_body_size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ContractError("invalid_body")
            case_id, budget = body.get("case_id"), body.get("budget", 450)
            action = body.get("action")
            if action == "answer":
                result = answer(case_id, budget)
            elif action == "context":
                result = context(case_id, budget)
            elif action == "verify":
                claims = body.get("claims")
                if not isinstance(claims, list) or len(claims) > 20:
                    raise ContractError("invalid_claims")
                result = validate_claims(case_id, claims, budget)
            else:
                raise ContractError("unknown_action")
            self.respond(200, result)
        except (ContractError, ValueError, TypeError, KeyError) as exc:
            self.respond(422, {"code": str(exc)})

    def respond(self, status: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8135), Handler).serve_forever()
