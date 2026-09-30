from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Deterministic OpenAI-compatible tool-call fixture")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": "ch24-fixture", "object": "model"}]}


@app.post("/v1/chat/completions")
def chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stream"):
        raise HTTPException(status_code=400, detail="Fixture unterstützt absichtlich kein Streaming")
    messages = payload.get("messages", [])
    tools = payload.get("tools", [])
    has_result = any(item.get("role") == "tool" for item in messages if isinstance(item, dict))
    if tools and not has_result:
        names = [
            item.get("function", {}).get("name")
            for item in tools
            if isinstance(item, dict)
        ]
        selected = "search_documents" if "search_documents" in names else next(
            (name for name in names if name), "search_documents"
        )
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_ch24_search",
                    "type": "function",
                    "function": {
                        "name": selected,
                        "arguments": json.dumps({"query": "Compliance", "limit": 3}),
                    },
                }
            ],
        }
        finish_reason = "tool_calls"
    else:
        tool_trace = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        document_id = "SUP-2026-001" if "SUP-2026-001" in tool_trace else "MCP_RESULT_MISSING"
        message = {
            "role": "assistant",
            "content": (
                f"Das synthetische Dokument {document_id} wurde über das "
                "freigegebene MCP-Lesewerkzeug geprüft."
            ),
        }
        finish_reason = "stop"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "ch24-fixture",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("CH24_MODEL_PORT", "8026")))  # nosec B104


if __name__ == "__main__":
    main()
