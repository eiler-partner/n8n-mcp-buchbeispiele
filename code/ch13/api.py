"""Local, synthetic HTTP API for the chapter-13 architecture exercise."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


DOCUMENTS = {
    "DOC-101": {
        "document_id": "DOC-101",
        "title": "Reiserichtlinie",
        "version": "3",
        "classification": "internal",
        "text": "Dienstreisen brauchen vor der Buchung eine Freigabe.",
    },
    "DOC-102": {
        "document_id": "DOC-102",
        "title": "Archivordnung",
        "version": "2",
        "classification": "internal",
        "text": "Prüfprotokolle werden geordnet im Archiv abgelegt.",
    },
}


class LabServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int]):
        super().__init__(server_address, LabHandler)
        self.approvals: list[dict[str, str]] = []
        self.approval_lock = threading.Lock()


class LabHandler(BaseHTTPRequestHandler):
    server: LabServer
    server_version = "Chapter12Lab/1.0"

    def log_message(self, format_string: str, *args: object) -> None:
        # Keep the synthetic lab quiet; never write request bodies to logs.
        return

    def respond(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            return self.respond(200, {"status": "ok"})
        if parsed.path.startswith("/documents/"):
            document_id = parsed.path.removeprefix("/documents/")
            document = DOCUMENTS.get(document_id)
            return self.respond(200, document) if document else self.respond(
                404, {"error": "document_not_found"}
            )
        if parsed.path == "/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip().lower()
            if not query or len(query) > 80:
                return self.respond(400, {"error": "invalid_query"})
            hits = [
                {
                    "document_id": doc["document_id"],
                    "version": doc["version"],
                    "classification": doc["classification"],
                    "snippet": doc["text"],
                }
                for doc in DOCUMENTS.values()
                if query in f"{doc['title']} {doc['text']}".lower()
            ]
            return self.respond(200, {"query": query, "hits": hits})
        return self.respond(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/approvals":
            return self.respond(404, {"error": "not_found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.respond(400, {"error": "invalid_length"})
        if size < 1 or size > 4096:
            return self.respond(400, {"error": "invalid_length"})
        try:
            request = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.respond(400, {"error": "invalid_json"})
        if not isinstance(request, dict):
            return self.respond(400, {"error": "invalid_request"})
        if request.get("document_id") not in DOCUMENTS:
            return self.respond(404, {"error": "document_not_found"})
        if request.get("decision") not in {"approve", "reject"}:
            return self.respond(400, {"error": "invalid_decision"})
        with self.server.approval_lock:
            approval_id = f"LAB-{len(self.server.approvals) + 1:03d}"
            record = {
                "approval_id": approval_id,
                "document_id": request["document_id"],
                "decision": request["decision"],
            }
            self.server.approvals.append(record)
        return self.respond(201, {**record, "simulation_only": True})


def main() -> None:
    host = os.environ.get("LAB_HOST", "127.0.0.1")
    port = int(os.environ.get("LAB_PORT", "18072"))
    server = LabServer((host, port))
    print(f"Chapter 13 synthetic API listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
