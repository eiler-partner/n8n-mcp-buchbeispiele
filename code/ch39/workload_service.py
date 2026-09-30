"""Bounded synthetic I/O workload; no external API, model, or real data."""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {"active": 0, "max_active": 0, "completed": 0, "ids": []}
ID_PATTERN = re.compile(r"[a-z0-9-]{1,48}\Z")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body: dict) -> None:
        raw = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(200, {"ok": True})
        elif self.path == "/stats":
            with LOCK:
                self.reply(200, dict(STATE))
        else:
            self.reply(404, {"code": "not_found"})

    def do_POST(self) -> None:
        if self.path == "/reset":
            with LOCK:
                if STATE["active"]:
                    self.reply(409, {"code": "busy"})
                    return
                STATE.update(active=0, max_active=0, completed=0, ids=[])
            self.reply(200, {"ok": True})
            return
        if self.path != "/work":
            self.reply(404, {"code": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 1024:
                raise ValueError("size")
            data = json.loads(self.rfile.read(length))
            job_id = data["id"]
            delay_ms = data["delay_ms"]
            if (not isinstance(job_id, str) or not ID_PATTERN.fullmatch(job_id)
                    or type(delay_ms) is not int or not 50 <= delay_ms <= 1000):
                raise ValueError("contract")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.reply(400, {"code": "invalid_request"})
            return
        with LOCK:
            STATE["active"] += 1
            STATE["max_active"] = max(STATE["max_active"], STATE["active"])
        try:
            time.sleep(delay_ms / 1000)
            with LOCK:
                STATE["completed"] += 1
                STATE["ids"].append(job_id)
            self.reply(200, {"id": job_id, "ok": True})
        finally:
            with LOCK:
                STATE["active"] -= 1


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8139), Handler).serve_forever()
