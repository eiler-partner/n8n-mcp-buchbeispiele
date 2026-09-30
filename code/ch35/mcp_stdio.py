"""Enges MCP-Resource-Lehrsubset mit festem Prozessscope (nicht produktiv)."""
from __future__ import annotations

import json
import os
import sys

from lab import BY_ID, CASES, context

VERSION = "2026-07-28"
META = "io.modelcontextprotocol/protocolVersion"


def handle(message: dict) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method = message["method"]
        params = message.get("params", {})
        if params.get("_meta", {}).get(META) != VERSION:
            raise ValueError("unsupported_protocol_version")
        case = CASES["urlaub"]
        if (os.getenv("CH35_ROLE", "employee") != case["role"]
                or os.getenv("CH35_TENANT", "buchlabor") != case["tenant"]):
            raise ValueError("server_scope_unavailable")
        selected = context("urlaub")["selected"]
        allowed = {f"lab://ch35/{item['chunk_id']}": item for item in selected}
        if method == "resources/list":
            result = {"resources": [{"uri": uri, "name": item["chunk_id"],
                                     "mimeType": "text/plain"}
                                    for uri, item in allowed.items()]}
        elif method == "resources/read":
            uri = params.get("uri")
            if uri not in allowed:
                raise ValueError("resource_outside_server_scope")
            result = {"contents": [{"uri": uri, "mimeType": "text/plain",
                                    "text": BY_ID[allowed[uri]["chunk_id"]]["text"]}]}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch35-citations", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        response["error"] = {"code": -32601 if str(exc) == "method_not_found" else -32602,
                             "message": str(exc)}
    return response


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            result = handle(json.loads(line))
        except (ValueError, TypeError):
            result = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(result, ensure_ascii=False), flush=True)
