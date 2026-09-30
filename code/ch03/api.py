"""Small local teaching API. Do not expose it to untrusted networks."""

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent
REVIEW_SCHEMA = json.loads((ROOT / "review-request.schema.json").read_text())
Draft202012Validator.check_schema(REVIEW_SCHEMA)
REVIEW_VALIDATOR = Draft202012Validator(REVIEW_SCHEMA)
DOCUMENTS = {
    "doc-1": {"id": "doc-1", "title": "Reiserichtlinie", "version": 3, "published": True},
    "doc-2": {"id": "doc-2", "title": "Entwurf Homeoffice", "version": 1, "published": False},
}


class Handler(BaseHTTPRequestHandler):
    data_dir = Path(os.environ.get("DATA_DIR", "/tmp/ch03-reviews"))

    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == "/health":
            return self.send_json(200, {"status": "ok"})
        if path.path == "/documents":
            params = parse_qs(path.query)
            try:
                limit = int(params.get("limit", ["2"])[0])
                cursor = int(params.get("cursor", ["0"])[0])
                if not 1 <= limit <= 5 or cursor < 0:
                    raise ValueError
            except ValueError:
                return self.send_json(400, {"error": "invalid_pagination"})
            items = list(DOCUMENTS.values())[cursor:cursor + limit]
            next_cursor = cursor + limit if cursor + limit < len(DOCUMENTS) else None
            return self.send_json(200, {"items": items, "next_cursor": next_cursor})
        if path.path.startswith("/documents/"):
            document = DOCUMENTS.get(path.path.removeprefix("/documents/"))
            if document is None:
                return self.send_json(404, {"error": "document_not_found"})
            return self.send_json(200, document)
        if path.path == "/reviews":
            return self.send_json(405, {"error": "method_not_allowed"}, {"Allow": "POST"})
        if path.path.startswith("/reviews/"):
            review_id = path.path.removeprefix("/reviews/")
            if len(review_id) != 32 or any(ch not in "0123456789abcdef" for ch in review_id):
                return self.send_json(404, {"error": "review_not_found"})
            record = self.data_dir / f"{review_id}.json"
            if not record.is_file():
                return self.send_json(404, {"error": "review_not_found"})
            return self.send_json(200, json.loads(record.read_text(encoding="utf-8")))
        return self.send_json(404, {"error": "route_not_found"})

    def do_POST(self):
        if urlsplit(self.path).path != "/reviews":
            return self.send_json(404, {"error": "route_not_found"})
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            return self.send_json(415, {"error": "json_required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_json(400, {"error": "invalid_length"})
        if not 0 < length <= 8192:
            return self.send_json(413, {"error": "body_size_invalid"})
        try:
            data = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.send_json(400, {"error": "invalid_json"})
        errors = sorted(REVIEW_VALIDATOR.iter_errors(data), key=lambda error: str(error.path))
        if errors:
            return self.send_json(422, {"error": "schema_mismatch"})
        if data["document_id"] not in DOCUMENTS:
            return self.send_json(404, {"error": "document_not_found"})
        review_id = uuid.uuid4().hex
        record = {"id": review_id, **data}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / f"{review_id}.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        return self.send_json(201, record, {"Location": f"/reviews/{review_id}"})


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Chapter 3 API listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
