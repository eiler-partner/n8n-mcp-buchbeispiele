from __future__ import annotations

import json

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from conftest import LiveServer


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2026-07-28",
        "capabilities": {},
        "clientInfo": {"name": "chapter-20-test", "version": "1"},
    },
}
HTTP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


@pytest.mark.anyio
async def test_protected_resource_metadata_and_401(live_server: LiveServer) -> None:
    async with httpx2.AsyncClient() as http:
        metadata = await http.get(
            live_server.resource.replace("/mcp", "/.well-known/oauth-protected-resource/mcp")
        )
        denied = await http.post(live_server.url, headers=HTTP_HEADERS, json=INITIALIZE)

    assert metadata.status_code == 200
    document = metadata.json()
    assert document["resource"] == live_server.resource
    assert document["authorization_servers"] == [live_server.issuer + "/"]
    assert document["scopes_supported"] == ["documents:read"]
    assert denied.status_code == 401
    assert "resource_metadata=" in denied.headers["www-authenticate"]


@pytest.mark.anyio
async def test_missing_scope_returns_403_challenge(live_server: LiveServer) -> None:
    token = live_server.token(scope="profile")
    async with httpx2.AsyncClient() as http:
        response = await http.post(
            live_server.url,
            headers={**HTTP_HEADERS, "authorization": f"Bearer {token}"},
            json=INITIALIZE,
        )

    assert response.status_code == 403
    challenge = response.headers["www-authenticate"]
    assert 'error="insufficient_scope"' in challenge
    assert 'scope="documents:read"' in challenge


@pytest.mark.anyio
async def test_wrong_audience_is_rejected(live_server: LiveServer) -> None:
    token = live_server.token(audience="https://other.example/mcp")
    async with httpx2.AsyncClient() as http:
        response = await http.post(
            live_server.url,
            headers={**HTTP_HEADERS, "authorization": f"Bearer {token}"},
            json=INITIALIZE,
        )
    assert response.status_code == 401


async def _authenticated_client(server: LiveServer, token: str) -> tuple[httpx2.AsyncClient, Client]:
    http = httpx2.AsyncClient(headers={"authorization": f"Bearer {token}"})
    transport = streamable_http_client(server.url, http_client=http)
    return http, Client(transport)


@pytest.mark.anyio
async def test_tenant_a_cannot_observe_tenant_b_data(live_server: LiveServer) -> None:
    http, client = await _authenticated_client(live_server, live_server.token())
    async with http, client:
        tools = await client.list_tools()
        listed = await client.call_tool("list_documents", {})
        cross_tenant = await client.call_tool("read_document", {"document_id": "B-001"})

    assert {tool.name for tool in tools.tools} == {"list_documents", "read_document"}
    assert listed.structured_content == {
        "documents": [
            {"id": "A-001", "title": "Informationsschutz", "classification": "intern"},
            {"id": "A-002", "title": "Lieferantenprüfung", "classification": "vertraulich"},
        ]
    }
    assert cross_tenant.structured_content == {"found": False}
    rendered = json.dumps(listed.structured_content, ensure_ascii=False)
    assert "B-001" not in rendered
    assert "Standortstrategie" not in rendered


@pytest.mark.anyio
async def test_denied_consent_is_audited_and_has_no_result(live_server: LiveServer) -> None:
    token = live_server.token(consent="denied")
    http, client = await _authenticated_client(live_server, token)
    async with http, client:
        result = await client.call_tool("list_documents", {})

    assert result.is_error is True
    assert "kein aktiver Consent" in result.content[0].text


def test_audit_contains_identity_scope_consent_and_decision(live_server: LiveServer) -> None:
    rows = [json.loads(line) for line in live_server.audit_path.read_text(encoding="utf-8").splitlines()]
    tool_rows = [row for row in rows if row["event"] == "tool_call"]
    assert tool_rows
    assert any(
        row["subject"] == "alice"
        and row["tenant_id"] == "tenant-a"
        and row["scopes"] == ["documents:read"]
        and row["consent_status"] in {"granted", "denied"}
        and row["decision"] in {"allow", "deny"}
        and row["correlation_id"]
        for row in tool_rows
    )
    assert all("token" not in row for row in rows)
