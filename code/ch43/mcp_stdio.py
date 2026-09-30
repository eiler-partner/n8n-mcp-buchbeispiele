"""Stateless MCP 2026-07-28 subset for one read-only retrieval tool."""
from __future__ import annotations

import json
import sys
from core import PROTOCOL, identity, retrieve, signing_key


def handle(message: dict) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method, params = message["method"], message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != PROTOCOL:
            raise ValueError("unsupported_protocol_version")
        if method == "tools/list":
            data = {"tools": [{"name": "search_evidence", "description": "Search current, authorized handbook clauses",
                               "inputSchema": {"type": "object", "properties": {
                                   "question": {"type": "string"}, "actor_token": {"type": "string"}},
                                   "required": ["question", "actor_token"], "additionalProperties": False}}]}
        elif method == "tools/call" and params.get("name") == "search_evidence":
            args = params.get("arguments", {})
            if set(args) != {"question", "actor_token"}:
                raise ValueError("invalid_arguments")
            actor = identity(args["actor_token"], signing_key())
            candidates = retrieve(args["question"], actor)
            data = {"content": [{"type": "text", "text": json.dumps({"candidates": candidates}, ensure_ascii=False)}],
                    "structuredContent": {"candidates": candidates}, "isError": False}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **data,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch43-knowledge", "version": "0.1.0"}}}
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
