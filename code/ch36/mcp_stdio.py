"""Enges MCP-Tool-Subset: nur aggregierter synthetischer 2x2-Bericht."""
from __future__ import annotations

import json
import sys

from evaluate import evaluate_all

VERSION = "2026-07-28"


def handle(message: dict) -> dict:
    result = {"jsonrpc": "2.0", "id": message.get("id")}
    try:
        method, params = message["method"], message.get("params", {})
        if params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion") != VERSION:
            raise ValueError("unsupported_protocol_version")
        if method == "tools/list":
            data = {"tools": [{"name": "compare_rag_variants",
                               "description": "Compare four fixed synthetic RAG variants",
                               "inputSchema": {"type": "object", "properties": {},
                                               "additionalProperties": False}}]}
        elif method == "tools/call" and params.get("name") == "compare_rag_variants":
            if params.get("arguments") != {}:
                raise ValueError("invalid_arguments")
            report = evaluate_all()
            summary = {"corpus_sha256": report["corpus_sha256"],
                       "golden_sha256": report["golden_sha256"],
                       "evaluator_sha256": report["evaluator_sha256"],
                       "results": [{"variant": row["variant"], "metrics": row["metrics"],
                                    "release": row["release"]} for row in report["results"]]}
            data = {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False)}],
                    "isError": False}
        else:
            raise ValueError("method_not_found")
        result["result"] = {"resultType": "complete", **data,
                            "_meta": {"io.modelcontextprotocol/serverInfo":
                                      {"name": "ch36-rag-eval", "version": "0.1.0"}}}
    except (KeyError, TypeError, ValueError) as exc:
        result["error"] = {"code": -32601 if str(exc) == "method_not_found" else -32602,
                           "message": str(exc)}
    return result


if __name__ == "__main__":
    for line in sys.stdin:
        try:
            response = handle(json.loads(line))
        except (ValueError, TypeError):
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse_error"}}
        print(json.dumps(response, ensure_ascii=False), flush=True)
