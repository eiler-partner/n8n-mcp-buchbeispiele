"""Loopback-only teaching HTTP service with deterministic fault injection."""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from contract import Store


STORE = Store(os.environ.get("LAB_DATABASE", "/data/ch10.sqlite3"))
MAX_BODY = 8_192


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The deliberate timeout-after-commit closes the client connection.

    def body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if size < 1 or size > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok"})
        if self.path.startswith("/state/"):
            doc_id = unquote(self.path.removeprefix("/state/"))
            state = STORE.state(doc_id)
            return self.reply(200, state) if state else self.reply(404, {"code": "not_found"})
        if self.path == "/alerts/count":
            return self.reply(200, {"count": STORE.alert_count()})
        self.reply(404, {"code": "not_found"})

    def do_POST(self):
        data = self.body()
        if not isinstance(data, dict):
            return self.reply(400, {"code": "invalid_json"})
        if self.path == "/analyze":
            status, payload = STORE.analyze(data)
        elif self.path == "/quarantine":
            status, payload = STORE.quarantine(data.get("doc_id"), data.get("reason"))
        elif self.path == "/approval-link":
            status, payload = STORE.approval_link(data.get("doc_id"), data.get("url"))
        elif self.path == "/deny":
            status, payload = STORE.deny(data.get("doc_id"))
        elif self.path == "/approve":
            status, payload = STORE.approve(data.get("doc_id"))
        elif self.path == "/publish":
            status, payload, delay = STORE.publish(data.get("doc_id"))
            if delay:
                time.sleep(2.5)
        elif self.path == "/alert":
            status, payload = STORE.alert(
                data.get("workflow_id"), data.get("execution_id"), data.get("message")
            )
        else:
            status, payload = 404, {"code": "not_found"}
        self.reply(status, payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8079), Handler).serve_forever()
