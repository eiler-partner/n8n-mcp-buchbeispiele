"""Synthetischer HTTP/SSE-Prüfdienst, ausdrücklich kein MCP-Server."""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_json({"status": "ok"})
        elif self.path == "/lab/headers":
            self.send_json({key: self.headers.get(key) for key in
                            ("Mcp-Protocol-Version", "Mcp-Method", "Mcp-Name",
                             "X-Forwarded-Proto", "X-Forwarded-Host", "X-Forwarded-For")})
        elif self.path == "/lab/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"data: first\n\n")
            self.wfile.flush()
            time.sleep(0.8)
            self.wfile.write(b"data: second\n\n")
            self.wfile.flush()
        else:
            self.send_json({"code": "not_found"}, 404)

    def send_json(self, body: dict, status: int = 200):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8138), Handler).serve_forever()
