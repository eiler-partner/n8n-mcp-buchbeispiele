"""Nur auf Loopback veröffentlichter HTTP-Adapter für das Kapitel-29-Labor."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .store import PolicyError, Store


def handler_for(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Keine Formularwerte oder Vorschlagsinhalte in HTTP-Logs schreiben.
            pass

        def _send(self, status: int, body: dict):
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/health":
                    return self._send(200, {"status": "ok"})
                if path.startswith("/state/"):
                    return self._send(200, store.state(unquote(path.removeprefix("/state/"))))
                return self._send(404, {"code": "not_found"})
            except PolicyError as error:
                return self._send(error.status, {"code": error.code})

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send(400, {"code": "body_size"})
            if length < 1 or length > 4096:
                return self._send(413, {"code": "body_size"})
            try:
                payload = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"code": "invalid_json"})
            dispatch = {
                "/propose": store.propose,
                "/decide": store.decide,
                "/tick": store.tick,
                "/commit": store.commit,
            }
            if path not in dispatch:
                return self._send(404, {"code": "not_found"})
            try:
                return self._send(200, dispatch[path](payload))
            except PolicyError as error:
                return self._send(error.status, {"code": error.code})

    return Handler


def main():
    db_path = os.environ.get("CH29_DB", "/data/ch29.sqlite3")
    store = Store(db_path)
    ThreadingHTTPServer(("0.0.0.0", 8129), handler_for(store)).serve_forever()


if __name__ == "__main__":
    main()
