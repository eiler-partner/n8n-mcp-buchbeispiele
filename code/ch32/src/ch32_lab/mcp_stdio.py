"""MCP-Resource-Lehrsubset; Scope kommt aus dem Serverprozess, nie aus clientInfo."""

from __future__ import annotations

import json
import os
import sys

from .store import Store

VERSION = "2026-07-28"


def uri(row: dict) -> str:
    return f"policy://{row['document_id']}/{row['version_id']}/{row['chunk_id']}"


def handle(message: dict, store: Store, *, role: str, as_of: str) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        params = message["params"]
        meta = params["_meta"]
        if meta["io.modelcontextprotocol/protocolVersion"] != VERSION:
            raise ValueError("unsupported_protocol_version")
        visible = store.visible(as_of, role)["chunks"]
        method = message["method"]
        if method == "resources/list":
            if set(params) != {"_meta"}:
                raise ValueError("invalid_params")
            result = {"resources": [
                {"uri": uri(row), "name": row["heading"],
                 "description": f"{row['version_id']} / {row['section_id']}",
                 "mimeType": "text/plain"} for row in visible]}
        elif method == "resources/read":
            if set(params) != {"_meta", "uri"}:
                raise ValueError("invalid_params")
            record = next((row for row in visible if uri(row) == params["uri"]), None)
            if record is None:
                raise ValueError("resource_not_found")
            result = {"contents": [{"uri": uri(record), "mimeType": "text/plain",
                                    "text": record["heading"] + "\n" + record["text"]}]}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "ttlMs": 0, "cacheScope": "private",
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch32-policy-resources", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        reason = str(exc)
        response["error"] = {"code": -32601 if reason == "method_not_found" else -32602,
                             "message": reason}
    return response


def main():
    store = Store(os.environ.get("CH32_DB", "/data/ch32.sqlite3"))
    role = os.environ.get("CH32_ROLE", "employee")
    as_of = os.environ.get("CH32_AS_OF", "2026-09-29")
    for line in sys.stdin:
        try:
            result = handle(json.loads(line), store, role=role, as_of=as_of)
        except (ValueError, TypeError):
            result = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "parse_error"}}
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
