"""Nur an Loopback publizierter Lehrdienst; Eingaben sind synthetisch."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from decide import all_decisions, decide, profiles


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(200, {"status": "ok"}) if self.path == "/health" else self.respond(404, {"code": "not_found"})

    def do_POST(self):
        if self.path != "/decide":
            self.respond(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("invalid_body_size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("invalid_body")
            if body == {"action": "all"}:
                answer = all_decisions()
            elif set(body) == {"action", "profile_id"} and body["action"] == "profile":
                row = profiles().get(body["profile_id"])
                if row is None:
                    raise ValueError("unknown_profile")
                answer = decide(row)
            elif set(body) == {"action", "profile"} and body["action"] == "custom":
                answer = decide(body["profile"])
            else:
                raise ValueError("invalid_request")
            self.respond(200, answer)
        except (ValueError, TypeError, KeyError) as exc:
            self.respond(422, {"code": str(exc)})

    def respond(self, status: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8137), Handler).serve_forever()
