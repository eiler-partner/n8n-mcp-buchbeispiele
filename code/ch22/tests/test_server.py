from __future__ import annotations

import pytest
from mcp import Client

from n8n_mcp_lab.server import create_server


@pytest.mark.anyio
async def test_reference_server_publishes_positive_and_negative_fixture() -> None:
    server = create_server("http://127.0.0.1:8022/mcp", "fixture-token")
    async with Client(server, mode="legacy") as client:
        result = await client.list_tools(cache_mode="refresh")
    assert {tool.name for tool in result.tools} == {"catalog_lookup", "maintenance_reset"}


@pytest.mark.anyio
async def test_catalog_lookup_returns_structured_read_only_result() -> None:
    server = create_server("http://127.0.0.1:8022/mcp", "fixture-token")
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool("catalog_lookup", {"query": "n8n", "limit": 2})
    assert result.is_error is False
    assert result.structured_content == {
        "result": [
            {"item_id": "N8N-022", "title": "n8n-MCP-Integrationsmuster", "status": "approved"}
        ]
    }


@pytest.mark.anyio
async def test_negative_fixture_never_executes() -> None:
    server = create_server("http://127.0.0.1:8022/mcp", "fixture-token")
    async with Client(server, mode="legacy") as client:
        result = await client.call_tool("maintenance_reset", {"confirm": True})
    assert result.is_error is True
