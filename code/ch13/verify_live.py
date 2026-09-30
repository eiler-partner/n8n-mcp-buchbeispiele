"""Exercise the direct HTTP API; no MCP server or external service is used."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = f"http://127.0.0.1:{int(os.environ.get('CH13_PORT', '18072'))}"


def request(path: str, *, payload: dict[str, str] | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    http_request = Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urlopen(http_request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main() -> None:
    status, body = request("/health")
    assert (status, body) == (200, {"status": "ok"})
    status, body = request("/documents/DOC-101")
    assert status == 200 and body["version"] == "3"
    print("PASS fixed direct API lookup")

    status, body = request("/search?q=Freigabe")
    assert status == 200 and [hit["document_id"] for hit in body["hits"]] == ["DOC-101"]
    status, body = request("/search")
    assert (status, body["error"]) == (400, "invalid_query")
    print("PASS bounded search and negative case")

    status, body = request(
        "/approvals", payload={"document_id": "DOC-101", "decision": "approve"}
    )
    assert status == 201 and body["simulation_only"] is True
    status, body = request(
        "/approvals", payload={"document_id": "DOC-101", "decision": "publish"}
    )
    assert (status, body["error"]) == (400, "invalid_decision")
    print("PASS simulated write and rejection; no real approval system")


if __name__ == "__main__":
    main()
