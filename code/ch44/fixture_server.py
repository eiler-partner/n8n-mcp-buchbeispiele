"""Stable synthetic HTTP API and web pages; never used as an external crawler."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

DATA = Path(__file__).parent / "data"
HITS: list[str] = []
LOCK = Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_body(b"ok", "text/plain")
            return
        if self.path == "/audit":
            with LOCK:
                hits = list(HITS)
            self.send_body(json.dumps({"hits": hits}).encode(), "application/json")
            return
        with LOCK:
            HITS.append(f"{self.command} {self.path}")
        if self.path == "/robots.txt":
            self.send_body(b"User-agent: ch44-lab\nDisallow: /web/private\nAllow: /\n", "text/plain")
        elif self.path == "/api/quarter":
            self.send_body((DATA / "api-quarter.json").read_bytes(), "application/json",
                           "2026-07-05T08:00:00Z", "0")
        elif self.path == "/web/briefing":
            self.send_body((DATA / "briefing.html").read_bytes(), "text/html",
                           "2026-07-06T07:00:00Z", "0")
        elif self.path == "/web/private":
            self.send_body((DATA / "private.html").read_bytes(), "text/html",
                           "2026-07-06T07:00:00Z", "0")
        elif self.path == "/web/tdm":
            self.send_body((DATA / "tdm.html").read_bytes(), "text/html",
                           "2026-07-06T07:00:00Z", "1")
        elif self.path == "/web/terms":
            self.send_body((DATA / "private.html").read_bytes(), "text/html",
                           "2026-07-06T07:00:00Z", "0")
        elif self.path == "/web/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
        else:
            self.send_error(404)

    def do_HEAD(self):
        # Same routing, status and headers as GET; send_body() and send_error() omit the body.
        self.do_GET()

    def send_body(self, raw: bytes, media_type: str, published: str | None = None,
                  tdm: str | None = None):
        self.send_response(200)
        self.send_header("Content-Type", media_type + "; charset=utf-8")
        if published:
            self.send_header("X-Published-At", published)
        if tdm is not None:
            self.send_header("tdm-reservation", tdm)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def log_message(self, format: str, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8144), Handler).serve_forever()
