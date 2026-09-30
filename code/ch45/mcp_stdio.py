"""Narrow read-only MCP Resources subset, protocol revision 2026-07-28."""
from __future__ import annotations

import json
import sys
from core import read_resource, resource_uris

VERSION = "2026-07-28"


def handle(message: dict) -> dict:
    reply = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method, params = message["method"], message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if method == "resources/list":
            if set(params) - {"_meta"}:
                raise ValueError("invalid_arguments")
            data = {"resources": [{"uri": uri, "name": uri.rsplit("/", 1)[-1],
                                    "mimeType": "application/json"} for uri in resource_uris()]}
        elif method == "resources/read":
            if set(params) != {"uri", "_meta"}:
                raise ValueError("invalid_arguments")
            uri = params["uri"]
            data = {"contents": [{"uri": uri, "mimeType": "application/json",
                                   "text": read_resource(uri)}]}
        else:
            raise ValueError("method_not_found")
        reply["result"] = {"resultType": "complete", **data,
                           "_meta": {"io.modelcontextprotocol/serverInfo":
                                     {"name": "ch45-versioned-controls", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        code = -32601 if str(exc) == "method_not_found" else -32602
        reply["error"] = {"code": code, "message": str(exc)}
    return reply


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            result = handle(json.loads(line))
        except (TypeError, ValueError):
            result = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(result, ensure_ascii=False), flush=True)
