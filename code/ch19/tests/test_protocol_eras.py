from __future__ import annotations

import pytest
from mcp import Client
from mcp.types import InputRequiredResult

from mcp_contract_lab.servers import mrtr_server, policy_server


@pytest.mark.anyio
async def test_modern_client_observes_and_resumes_input_required() -> None:
    async with Client(mrtr_server, mode="2026-07-28") as client:
        first = await client.session.call_tool(
            "confirm_modern_contract",
            {},
            allow_input_required=True,
        )
        assert isinstance(first, InputRequiredResult)
        assert first.result_type == "input_required"
        assert first.request_state is not None

        terminal = await client.session.call_tool(
            "confirm_modern_contract",
            {},
            request_state=first.request_state,
            allow_input_required=True,
        )

    assert not isinstance(terminal, InputRequiredResult)
    assert terminal.structured_content == {"confirmed": True}


@pytest.mark.anyio
async def test_legacy_client_negotiates_2025_11_25_contract() -> None:
    async with Client(policy_server, mode="legacy") as client:
        assert client.session.protocol_version == "2025-11-25"
        tools = await client.list_tools(cache_mode="refresh")

    assert "search_policies" in {tool.name for tool in tools.tools}
