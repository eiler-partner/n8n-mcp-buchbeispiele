"""Loopback teaching service for pagination and verified webhook writes."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from contract import MAX_BODY, ingest, order_count, page, validate


DATABASE = Path(os.environ.get("LAB_DATABASE", "/data/orders.sqlite3"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, body: dict, headers: dict | None = None) -> None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):  # noqa: N802 - http.server interface
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self.send_json(200, {"status": "ok"})
        if parsed.path == "/orders/count":
            return self.send_json(200, {"count": order_count(DATABASE)})
        if parsed.path == "/records":
            query = parse_qs(parsed.query)
            if set(query) - {"page"} or len(query.get("page", ["1"])) != 1:
                return self.send_json(400, {"error": "invalid_page"})
            try:
                number = int(query.get("page", ["1"])[0])
                result = page(number, "http://api:8078")
            except ValueError:
                return self.send_json(400, {"error": "invalid_page"})
            return self.send_json(200, result)
        if parsed.path == "/throttle":
            return self.send_json(429, {"error": "rate_limited"}, {"Retry-After": "2"})
        return self.send_json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802 - http.server interface
        if urlparse(self.path).path != "/ingest":
            return self.send_json(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= MAX_BODY:
            return self.send_json(413, {"accepted": False, "error": "invalid_body_size"})
        raw = self.rfile.read(length)
        headers = {key.lower(): value for key, value in self.headers.items()}
        try:
            event, delivery_id = validate(raw, headers, SECRET)
        except PermissionError as error:
            return self.send_json(401, {"accepted": False, "error": str(error)})
        except ValueError as error:
            return self.send_json(400, {"accepted": False, "error": str(error)})
        status, result = ingest(DATABASE, event, delivery_id, raw)
        return self.send_json(status, result)


if __name__ == "__main__":
    if len(SECRET) < 32:
        raise SystemExit("WEBHOOK_SECRET must contain at least 32 characters")
    ThreadingHTTPServer(("0.0.0.0", 8078), Handler).serve_forever()
