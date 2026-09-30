import pytest
from mcp import Client

from policy_mcp.server import mcp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_hash_tool_contract() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("hash_text", {"text": "MCP"})
    assert result.is_error is False
    assert result.structured_content == {
        "algorithm": "sha256",
        "digest": "53f13ae99ed53bd346eb8e1c8cefb7ef8260683b50401caf101360967ea052aa",
        "byte_length": 3,
    }


@pytest.mark.anyio
async def test_policy_resource_uses_untyped_context() -> None:
    """Regression: Context[AppContext] in einer Resource-Vorlage liesse jeden Aufruf scheitern."""
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.read_resource("policy://POL-101")
    text = result.contents[0].text
    assert "ID: `POL-101`" in text
