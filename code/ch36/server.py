"""Nicht authentifizierter, nur an Loopback veröffentlichter Lehrdienst."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evaluate import CASES, evaluate_all, evaluate_case


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(200, {"status": "ok"}) if self.path == "/health" else self.respond(404, {"code": "not_found"})

    def do_POST(self):
        if self.path != "/evaluate":
            self.respond(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("invalid_body_size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("invalid_body")
            if body.get("action") == "compare" and set(body) == {"action"}:
                result = evaluate_all()
            elif body.get("action") == "case" and set(body) == {"action", "case_id", "chunking", "retrieval"}:
                case = CASES.get(body["case_id"])
                if case is None:
                    raise ValueError("unknown_case")
                result = evaluate_case(case, body["chunking"], body["retrieval"])
            else:
                raise ValueError("invalid_request")
            self.respond(200, result)
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
    ThreadingHTTPServer(("0.0.0.0", 8136), Handler).serve_forever()
