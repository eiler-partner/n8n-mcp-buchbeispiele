"""Loopback-HTTP-Hülle um den lokalen Kapitel-27-Zustandsautomaten."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import LabError, RunStore


class Handler(BaseHTTPRequestHandler):
    store: RunStore

    def _send(self, status: int, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"ok": True})
            return
        if parsed.path.startswith("/runs/"):
            run_id = parsed.path.removeprefix("/runs/")
            tenant = parse_qs(parsed.query).get("tenant_id", [None])[0]
            try:
                self._send(200, self.store.status(run_id, tenant))
            except LabError as exc:
                self._send(exc.status, {"error": exc.code})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path not in ("/start", "/resume", "/forget"):
            self._send(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise LabError("invalid_body_size", 422)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise LabError("invalid_body", 422)
            if self.path == "/start":
                result = self.store.start(payload)
            elif self.path == "/resume":
                result = self.store.resume(payload)
                if payload.get("simulate_lost_ack") is True and not result["replay"]:
                    # Der COMMIT ist bereits erfolgt; nur die Bestätigung fällt aus.
                    self._send(503, {"error": "ack_lost_after_commit"})
                    return
            else:
                result = self.store.forget_session(payload)
            self._send(200, result)
        except (ValueError, UnicodeError):
            self._send(422, {"error": "invalid_json"})
        except LabError as exc:
            self._send(exc.status, {"error": exc.code})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8127)
    parser.add_argument("--db", default=os.environ.get("CH27_DB", "data/ch27.sqlite"))
    args = parser.parse_args()
    Handler.store = RunStore(args.db)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
