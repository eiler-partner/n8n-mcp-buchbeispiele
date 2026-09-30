"""Lokaler Lehrdienst; Evidence-Endpunkt nur an Loopback des Hosts binden."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from policy import Gate

gate = Gate("/data/gate.sqlite", Path("/run/secrets/actor_key").read_bytes(),
            Path("/run/secrets/approval_key").read_bytes())


class Handler(BaseHTTPRequestHandler):
    def reply(self, code: int, value: dict) -> None:
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(200, {"ok": True})
        elif self.path == "/evidence":
            self.reply(200, gate.evidence())
        else:
            self.reply(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/review":
            self.reply(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 10000:
                raise ValueError("size")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("body")
            self.reply(200, gate.review(body))
        except (ValueError, json.JSONDecodeError):
            self.reply(400, {"error": "invalid_request"})


ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8141"))), Handler).serve_forever()
