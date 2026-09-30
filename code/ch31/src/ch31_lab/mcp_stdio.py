"""Resource-Lehrsubset der MCP-Version 2026-07-28 über stdio."""

from __future__ import annotations

import json
import os
import sys

from .pipeline import Store

VERSION = "2026-07-28"


def uri(record: dict) -> str:
    return (f"ingest://{record['document_id']}/{record['version']}/"
            f"{record['source_sha256'][:16]}")


def handle(message: dict, store: Store) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        params = message["params"]
        if params["_meta"]["io.modelcontextprotocol/protocolVersion"] != VERSION:
            raise ValueError("unsupported_protocol_version")
        method = message["method"]
        records = store.accepted()
        if method == "resources/list":
            result = {"resources": [
                {"uri": uri(record), "name": record["case_id"], "mimeType": "text/plain"}
                for record in records], "ttlMs": 0, "cacheScope": "private"}
        elif method == "resources/read":
            record = next((row for row in records if uri(row) == params["uri"]), None)
            if record is None:
                raise ValueError("resource_not_found")
            result = {"contents": [{"uri": uri(record), "mimeType": "text/plain",
                                    "text": record["text"]}],
                      "ttlMs": 0, "cacheScope": "private"}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch31-ingestion-resources", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        error = str(exc)
        response["error"] = {"code": -32601 if error == "method_not_found" else -32602,
                             "message": error}
    return response


def main():
    store = Store(os.environ.get("CH31_DB", "/data/ch31.sqlite3"))
    for line in sys.stdin:
        try:
            response = handle(json.loads(line), store)
        except (ValueError, TypeError):
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse_error"}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
