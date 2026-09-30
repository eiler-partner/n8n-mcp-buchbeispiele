from __future__ import annotations

import anyio
import pytest
from mcp import Client

from mcp_contract_lab.servers import fault_server, policy_server


@pytest.mark.anyio
async def test_progress_callback_receives_each_step() -> None:
    events: list[tuple[float, float | None, str | None]] = []

    async def record(progress: float, total: float | None, message: str | None) -> None:
        events.append((progress, total, message))

    async with Client(policy_server) as client:
        result = await client.call_tool(
            "check_documents",
            {"document_ids": ["DOC-1", "DOC-2"]},
            progress_callback=record,
        )
    assert result.structured_content == {"checked": 2}
    assert events == [(1.0, 2.0, "DOC-1"), (2.0, 2.0, "DOC-2")]


@pytest.mark.anyio
async def test_business_error_is_a_tool_result() -> None:
    async with Client(fault_server) as client:
        result = await client.call_tool("controlled_failure", {"kind": "business"})
    assert result.is_error is True
    assert "Kontrollierter Fachfehler" in result.content[0].text


@pytest.mark.anyio
async def test_unexpected_error_is_sanitized() -> None:
    async with Client(fault_server) as client:
        result = await client.call_tool("controlled_failure", {"kind": "unexpected"})
    assert result.is_error is True
    rendered = result.content[0].text
    assert "Interner Testfehler" not in rendered


@pytest.mark.anyio
async def test_client_timeout_is_observable() -> None:
    async with Client(fault_server) as client:
        with pytest.raises(TimeoutError):
            with anyio.fail_after(0.01):
                await client.call_tool(
                    "delayed_echo",
                    {"text": "zu langsam", "delay_seconds": 0.2},
                )
