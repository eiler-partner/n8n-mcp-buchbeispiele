"""Kleiner MCP-2026-07-28-Resource-Adapter über stdio (Lehrsubset)."""

from __future__ import annotations

import json
import os
import sys

from .core import authorized, fingerprint

VERSION = "2026-07-28"
SERVER_INFO = {"name": "ch30-synthetic-resources", "version": "0.1.0"}


def _uri(row: dict) -> str:
    return f"rag://{row['tenant']}/{row['document_id']}/{row['version']}/{row['chunk_id']}"


def handle(message: dict, tenant: str, role: str) -> dict:
    request_id = message.get("id")
    response = {"jsonrpc": "2.0", "id": request_id}
    try:
        params = message["params"]
        meta = params["_meta"]
        if meta["io.modelcontextprotocol/protocolVersion"] != VERSION:
            raise ValueError("unsupported_protocol_version")
        method = message["method"]
        scope = {"question_tag": "urlaub", "tenant": tenant, "role": role}
        # Die Auswahl hängt nur vom festen Prozess-Scope ab, nie von einem vorherigen Request.
        rows = authorized(scope)
        if method == "resources/list":
            result = {"resources": [
                {"uri": _uri(row), "name": row["chunk_id"], "mimeType": "text/plain"}
                for row in rows], "ttlMs": 0, "cacheScope": "private"}
        elif method == "resources/read":
            uri = params["uri"]
            row = next((row for row in rows if _uri(row) == uri), None)
            if row is None:
                raise ValueError("resource_not_found")
            result = {"contents": [{"uri": uri, "mimeType": "text/plain", "text": row["text"]}],
                      "ttlMs": 0, "cacheScope": "private"}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO}}
    except (KeyError, TypeError, ValueError) as exc:
        message = str(exc)
        code = -32601 if message == "method_not_found" else -32602
        response["error"] = {"code": code, "message": message}
    return response


def main():
    tenant = os.environ.get("CH30_TENANT", "werk")
    role = os.environ.get("CH30_ROLE", "employee")
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = handle(message, tenant, role)
        except (ValueError, TypeError):
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse_error"}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
