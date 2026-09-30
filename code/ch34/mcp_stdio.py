"""MCP-Tool-Lehrsubset: nur fest gelabelte Mitarbeiterfälle im Default-Scope."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from lab import CASES, MODES

VERSION = "2026-07-28"


def handle(message: dict) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method = message["method"]
        params = message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if method == "tools/list":
            result = {"tools": [{"name": "compare_retrieval",
                                 "description": "Synthetic, scoped case comparison",
                                 "inputSchema": {"type": "object", "properties": {
                                     "case_id": {"type": "string"},
                                     "mode": {"enum": list(MODES)}},
                                     "required": ["case_id", "mode"],
                                     "additionalProperties": False}}]}
        elif method == "tools/call" and params.get("name") == "compare_retrieval":
            args = params["arguments"]
            if not isinstance(args, dict) or set(args) != {"case_id", "mode"}:
                raise ValueError("invalid_arguments")
            case = CASES.get(args["case_id"])
            if case is None or case["role"] != os.getenv("CH34_ROLE", "employee") or case["tenant"] != os.getenv("CH34_TENANT", "buchlabor"):
                raise ValueError("case_outside_server_scope")
            body = {"action": "search", **args}
            req = urllib.request.Request("http://127.0.0.1:8134/operate",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                      "isError": False}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch34-retrieval", "version": "0.1.0"}}}
    except Exception as exc:
        response["error"] = {"code": -32601 if str(exc) == "method_not_found" else -32602,
                             "message": str(exc)}
    return response


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            answer = handle(json.loads(line))
        except (ValueError, TypeError):
            answer = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(answer, ensure_ascii=False), flush=True)
