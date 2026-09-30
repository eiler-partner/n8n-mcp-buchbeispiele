import pytest

from mcp import Client

from advanced_policy_mcp.server import mcp


@pytest.mark.anyio
async def test_advanced_tools_are_discoverable():
    async with Client(mcp) as client:
        result = await client.list_tools()
    names = {tool.name for tool in result.tools}
    assert {"start_review", "get_review", "cancel_review", "review_now"} <= names


@pytest.mark.anyio
async def test_review_now_has_structured_result():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "review_now",
            {"document_id": "DOC-9", "checks": ["Freigabe"]},
        )
    assert result.structured_content["document_id"] == "DOC-9"
    assert result.structured_content["passed_checks"] == 1
