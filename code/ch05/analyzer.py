"""Small, unauthenticated HTTP fixture for a loopback-only teaching lab."""

from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os

MAX_BYTES = 32_768
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_notes.txt"


def analyze(document: object) -> dict:
    if not isinstance(document, dict):
        raise ValueError("Expected a JSON object.")
    filename, content = document.get("filename"), document.get("text")
    if not isinstance(filename, str) or not filename or len(filename) > 120:
        raise ValueError("filename must be a nonempty string of at most 120 characters.")
    if "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain a path.")
    if not isinstance(content, str):
        raise ValueError("text must be a string.")
    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("text exceeds the teaching limit.")
    return {
        "filename": filename,
        "line_count": len(content.splitlines()),
        "nonempty_lines": sum(bool(line.strip()) for line in content.splitlines()),
        "sha256": sha256(content.encode("utf-8")).hexdigest(),
        "verdict": "review" if "TODO" in content else "ready",
    }


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._reply(200, {"status": "ok"})
        elif self.path == "/fixture":
            self._reply(200, {"filename": FIXTURE.name, "text": FIXTURE.read_text(encoding="utf-8")})
        else:
            self._reply(404, {"error": "unknown endpoint"})

    def do_POST(self) -> None:
        if self.path != "/analyze":
            self._reply(404, {"error": "unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BYTES:
            self._reply(413, {"error": "missing or oversized request body"})
            return
        try:
            document = json.loads(self.rfile.read(length))
            result = analyze(document)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._reply(400, {"error": str(exc)})
            return
        self._reply(200, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8055"))), Handler).serve_forever()
