"""Loopback-only teaching API. No external data and no persistent state."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from data import CASES, envelope


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - standard library interface
        path = urlparse(self.path).path
        if path == "/health":
            body, status = {"status": "ok"}, 200
        elif path.startswith("/cases/") and path[7:] in CASES:
            body, status = envelope(path[7:]), 200
        else:
            body, status = {"error": "not_found"}, 404
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8077), Handler).serve_forever()
