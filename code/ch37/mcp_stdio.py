"""Enger MCP-stdio-Vertrag für die drei synthetischen Profile."""
from __future__ import annotations

import json
import sys

from decide import decide, profiles

VERSION = "2026-07-28"


def handle(message: dict) -> dict:
    reply = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        params = message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if message.get("method") == "tools/list":
            data = {"tools": [{"name": "decide_architecture",
                               "description": "Decide one fixed synthetic deployment profile",
                               "inputSchema": {"type": "object", "properties": {"profile_id": {"type": "string", "enum": list(profiles())}},
                                               "required": ["profile_id"], "additionalProperties": False}}]}
        elif message.get("method") == "tools/call" and params.get("name") == "decide_architecture":
            args = params.get("arguments", {})
            if not isinstance(args, dict) or set(args) != {"profile_id"} or args["profile_id"] not in profiles():
                raise ValueError("invalid_arguments")
            data = {"content": [{"type": "text", "text": json.dumps(decide(profiles()[args["profile_id"]]), ensure_ascii=False)}],
                    "isError": False}
        else:
            raise ValueError("method_not_found")
        reply["result"] = {"resultType": "complete", **data,
                           "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "ch37-architecture", "version": "0.1.0"}}}
    except (TypeError, KeyError, ValueError) as exc:
        reply["error"] = {"code": -32601 if str(exc) == "method_not_found" else -32602, "message": str(exc)}
    return reply


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            result = handle(json.loads(line))
        except (TypeError, ValueError):
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(result, ensure_ascii=False), flush=True)
