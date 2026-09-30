"""Modern MCP subset with one read-only, allowlisted source tool."""
from __future__ import annotations

import json
import sys
from source_io import SOURCES, read_source

VERSION = "2026-07-28"


def handle(message: dict) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method, params = message["method"], message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if method == "tools/list":
            data = {"tools": [{"name": "read_source",
                               "description": "Read one approved synthetic source by fixed ID; no arbitrary URL or writes",
                               "inputSchema": {"type": "object", "properties": {
                                   "source_id": {"type": "string", "enum": list(SOURCES)}},
                                   "required": ["source_id"], "additionalProperties": False}}]}
        elif method == "tools/call" and params.get("name") == "read_source":
            args = params.get("arguments", {})
            if set(args) != {"source_id"}:
                raise ValueError("invalid_arguments")
            record = read_source(args["source_id"])
            data = {"content": [{"type": "text", "text": json.dumps(record, ensure_ascii=False)}],
                    "structuredContent": record, "isError": False}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **data,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch44-readonly-research", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        response["error"] = {"code": -32601 if str(exc) == "method_not_found" else -32602,
                             "message": str(exc)}
    return response


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            output = handle(json.loads(line))
        except (ValueError, TypeError):
            output = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(output, ensure_ascii=False), flush=True)
