"""Lehr-Subset eines MCP-Tool-Adapters; Scope nur aus Serverprozess-Umgebung."""
from __future__ import annotations

import json
import os
import sys
from urllib import request

VERSION = "2026-07-28"
API = "http://127.0.0.1:8133/operate"


def handle(message: dict) -> dict:
    response = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method = message["method"]
        params = message.get("params", {})
        meta = params.get("_meta", {})
        if meta.get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if method == "tools/list":
            result = {"tools": [{"name": "search_fixture_vectors",
                                 "description": "Scoped search over synthetic test vectors only",
                                 "inputSchema": {"type": "object", "properties": {
                                     "store": {"enum": ["pgvector", "qdrant"]},
                                     "model_id": {"enum": ["fixture-v1", "fixture-v2"]},
                                     "vector": {"type": "array", "items": {"type": "number"}},
                                     "top_k": {"type": "integer"}},
                                     "required": ["store", "model_id", "vector"],
                                     "additionalProperties": False}}]}
        elif method == "tools/call" and params.get("name") == "search_fixture_vectors":
            arguments = params["arguments"]
            if not isinstance(arguments, dict) or set(arguments) - {"store", "model_id", "vector", "top_k"}:
                raise ValueError("invalid_arguments")
            body = {**arguments, "action": "query",
                    "tenant_id": os.environ.get("CH33_TENANT", "buchlabor"),
                    "role": os.environ.get("CH33_ROLE", "employee"),
                    "as_of": os.environ.get("CH33_AS_OF", "2026-09-29")}
            req = request.Request(API, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                      "isError": False}
        else:
            raise ValueError("method_not_found")
        response["result"] = {"resultType": "complete", **result,
                              "_meta": {"io.modelcontextprotocol/serverInfo":
                                        {"name": "ch33-fixture-vectors", "version": "0.1.0"}}}
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
