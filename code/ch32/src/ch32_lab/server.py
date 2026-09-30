"""Loopback-Lehrdienst; Rollen im HTTP-Request sind NICHT authentifiziert."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .core import ContractError, preview
from .store import Store


class Handler(BaseHTTPRequestHandler):
    store = Store(os.environ.get("CH32_DB", "/data/ch32.sqlite3"))

    def log_message(self, *_args):
        pass

    def reply(self, status: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path == "/health":
            return self.reply(200, {"status": "ok"})
        return self.reply(404, {"code": "not_found"})

    def do_POST(self):
        if urlsplit(self.path).path != "/operate":
            return self.reply(404, {"code": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                return self.reply(413, {"code": "body_size"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ContractError("invalid_request")
            action = payload.get("action")
            fields = {"publish": {"action", "version_id"},
                      "visible": {"action", "as_of", "role"},
                      "withdraw": {"action", "effective_at"},
                      "preview": {"action", "version_id"},
                      "history": {"action"}}
            if action not in fields or set(payload) != fields[action]:
                raise ContractError("invalid_request")
            if action == "publish":
                result = self.store.publish(payload["version_id"])
            elif action == "visible":
                result = self.store.visible(payload["as_of"], payload["role"])
            elif action == "withdraw":
                result = self.store.withdraw(payload["effective_at"])
            elif action == "preview":
                result = preview(payload["version_id"])
            else:
                result = self.store.history()
        except (ValueError, TypeError) as exc:
            code = str(exc) if isinstance(exc, ContractError) else "invalid_json"
            return self.reply(422, {"code": code})
        return self.reply(200, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8132), Handler).serve_forever()
