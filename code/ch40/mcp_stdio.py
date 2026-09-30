"""Enges stdio-MCP-Labor-Tool; HTTP-Bridge öffnet eine Sitzung je Anfrage."""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8140"
VERSION = "2025-06-18"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    if method == "notifications/initialized":
        return None
    response = {"jsonrpc": "2.0", "id": msg.get("id")}
    if method == "initialize":
        response["result"] = {"protocolVersion": VERSION,
                              "capabilities": {"tools": {}},
                              "serverInfo": {"name": "ch40-observability-fixture", "version": "0.1.0"}}
    elif method == "tools/list":
        response["result"] = {"tools": [{"name": "answer_from_fixture",
            "description": "Answer a fixed synthetic question with one evidence reference",
            "inputSchema": {"type": "object", "properties": {
                "request_id": {"type": "string"}, "correlation_id": {"type": "string"},
                "break_trace": {"type": "boolean"}, "model_error": {"type": "boolean"}},
                "required": ["request_id", "correlation_id"]}}]}
    elif method == "tools/call" and msg.get("params", {}).get("name") == "answer_from_fixture":
        args = msg["params"].get("arguments", {})
        post("/internal/event", {"request_id": args["request_id"],
             "correlation_id": args["correlation_id"], "stage": "mcp",
             "parent_stage": "n8n", "duration_ms": 2, "status": "accepted"})
        retrieval = post("/internal/retrieve", args)
        model = post("/internal/model", {**args, "evidence_id": retrieval["evidence_id"]})
        response["result"] = {"content": [{"type": "text", "text": json.dumps(model)}],
                              "isError": model["status"] != "ok"}
    else:
        response["error"] = {"code": -32601, "message": "method_not_found"}
    return response


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            output = handle(json.loads(line))
        except (KeyError, ValueError, TypeError) as exc:
            output = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32602, "message": str(exc)}}
        if output is not None:
            print(json.dumps(output), flush=True)
