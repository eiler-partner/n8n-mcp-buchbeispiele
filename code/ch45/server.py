"""Loopback-only business gateway behind the chapter's n8n workflow."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from case_service import connect, key, safe_dispatch


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.respond({"status": "ok"})

    def do_POST(self):
        if self.path != "/dispatch":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 65536 or length < 2:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.respond({"ok": False, "code": "invalid_json"}, 400)
            return
        db = connect()
        try:
            result = safe_dispatch(payload, db)
        finally:
            db.close()
        self.respond(result)

    def respond(self, value: dict, status: int = 200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Never log tokens or document text in the teaching gateway.


if __name__ == "__main__":
    key()
    with connect():
        pass
    ThreadingHTTPServer(("0.0.0.0", 8146), Handler).serve_forever()
