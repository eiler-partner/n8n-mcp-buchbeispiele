"""Nur an Docker/Host-Loopback veröffentlichter Ingestionsdienst."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .core import ContractError
from .pipeline import Store, inspect


class Handler(BaseHTTPRequestHandler):
    store = Store(os.environ.get("CH31_DB", "/data/ch31.sqlite3"))

    def log_message(self, *_args):
        pass

    def send_json(self, status: int, value: dict):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path == "/health":
            return self.send_json(200, {"status": "ok"})
        return self.send_json(404, {"code": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/inspect", "/ingest"}:
            return self.send_json(404, {"code": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                return self.send_json(413, {"code": "body_size"})
            payload = json.loads(self.rfile.read(length))
            if path == "/inspect":
                if not isinstance(payload, dict) or set(payload) - {"case_id", "declared_mime"}:
                    raise ContractError("invalid_request")
                result, _ = inspect(payload.get("case_id"),
                                    payload.get("declared_mime", "application/pdf"))
            else:
                result = self.store.ingest(payload)
        except (TypeError, ValueError) as exc:
            code = str(exc) if isinstance(exc, ContractError) else "invalid_json"
            return self.send_json(422, {"code": code})
        self.send_json(200, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8131), Handler).serve_forever()
