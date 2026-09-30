from __future__ import annotations

import httpx
import pytest

from n8n_mcp_lab.policy import ProtocolObservation
from n8n_mcp_lab.probe import decode_mcp_response, probe_modern_era


def test_decode_json_response() -> None:
    response = httpx.Response(200, headers={"content-type": "application/json"}, json={"id": 1})
    assert decode_mcp_response(response) == {"id": 1}


def test_decode_sse_response() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n',
    )
    assert decode_mcp_response(response)["jsonrpc"] == "2.0"


def test_decode_rejects_empty_stream() -> None:
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=": ping\n")
    with pytest.raises(ValueError, match="Keine JSON-RPC"):
        decode_mcp_response(response)


def _client(status: int, body: dict | None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Mcp-Method"] == "server/discover"
        assert request.headers["MCP-Protocol-Version"] == "2026-07-28"
        if body is None:
            return httpx.Response(status, text="Bad Request: No valid session ID")
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discover_result_identifies_modern_server() -> None:
    body = {"jsonrpc": "2.0", "id": "discover-1", "result": {
        "resultType": "complete", "supportedVersions": ["2026-07-28", "2025-11-25"],
        "capabilities": {}, "ttlMs": 0, "cacheScope": "public"}}
    observed = probe_modern_era(_client(200, body), "http://mcp.test/mcp")
    assert observed["era"] == "modern"
    assert observed["supported_versions"] == ["2026-07-28", "2025-11-25"]


def test_unsupported_version_error_still_means_modern() -> None:
    body = {"jsonrpc": "2.0", "id": "discover-1", "error": {
        "code": -32022, "message": "Unsupported protocol version",
        "data": {"supported": ["2027-01-01"], "requested": "2026-07-28"}}}
    observed = probe_modern_era(_client(400, body), "http://mcp.test/mcp")
    assert observed["era"] == "modern" and observed["error_code"] == -32022


def test_plain_400_identifies_legacy_server() -> None:
    observed = probe_modern_era(_client(400, None), "http://mcp.test/mcp")
    assert observed == {"http_status": 400, "era": "legacy"}


def test_era_combines_modern_probe_and_legacy_handshake() -> None:
    base = ProtocolObservation("http://x/mcp", "streamable-http", "2025-11-25", "srv", ("catalog_lookup",))
    assert base.era == "legacy"
    assert base.with_modern_probe({"era": "legacy"}).era == "legacy"
    assert base.with_modern_probe({"era": "modern"}).era == "dual"
