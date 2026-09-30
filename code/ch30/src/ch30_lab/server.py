"""HTTP-Orchestrierungsdienst für den n8n-Pfad; nur synthetische Daten."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .core import ContractError, answer, compare, retrieve


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, status: int, value: dict):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"code": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        dispatch = {"/retrieve": retrieve, "/answer": answer, "/compare": compare}
        if path not in dispatch:
            return self.send_json(404, {"code": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                return self.send_json(413, {"code": "body_size"})
            payload = json.loads(self.rfile.read(length))
            result = dispatch[path](payload)
        except (ValueError, TypeError) as exc:
            code = str(exc) if isinstance(exc, ContractError) else "invalid_json"
            return self.send_json(422, {"code": code})
        self.send_json(200, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8130), Handler).serve_forever()
