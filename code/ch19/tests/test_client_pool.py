from __future__ import annotations

import pytest

from mcp_contract_lab.client import ClientConfigurationError, ClientPool, ServerBinding
from mcp_contract_lab.servers import policy_server, risk_server


@pytest.mark.anyio
async def test_multiple_servers_use_qualified_allowlisted_names() -> None:
    bindings = (
        ServerBinding(
            alias="policy",
            target=policy_server,
            allowed_tools=frozenset({"search_policies"}),
        ),
        ServerBinding(
            alias="risk",
            target=risk_server,
            allowed_tools=frozenset({"classify_risk"}),
        ),
    )
    async with ClientPool(bindings) as clients:
        assert set(clients.tools) == {"policy/search_policies", "risk/classify_risk"}
        result = await clients.call_tool(
            "risk/classify_risk",
            {"document_id": "DOC-7", "findings": ["fehlende Freigabe"]},
        )
    assert result.is_error is False
    assert result.structured_content == {
        "document_id": "DOC-7",
        "risk": "medium",
        "reasons": ["fehlende Freigabe"],
    }


@pytest.mark.anyio
async def test_unknown_allowlist_entry_fails_at_connect() -> None:
    binding = ServerBinding(
        alias="policy",
        target=policy_server,
        allowed_tools=frozenset({"delete_everything"}),
    )
    with pytest.raises(ClientConfigurationError, match="unbekannte Tools"):
        async with ClientPool((binding,)):
            pass


@pytest.mark.anyio
async def test_unqualified_or_unapproved_tool_is_rejected() -> None:
    binding = ServerBinding(
        alias="policy",
        target=policy_server,
        allowed_tools=frozenset({"search_policies"}),
    )
    async with ClientPool((binding,)) as clients:
        with pytest.raises(ClientConfigurationError, match="nicht freigegeben"):
            await clients.call_tool("check_documents", {"document_ids": ["DOC-1"]})


@pytest.mark.anyio
async def test_resources_are_discovered_separately_from_tools() -> None:
    binding = ServerBinding(
        alias="policy",
        target=policy_server,
        allowed_tools=frozenset({"search_policies"}),
    )
    async with ClientPool((binding,)) as clients:
        resources = await clients.list_resources("policy")
    assert [str(resource.uri) for resource in resources] == ["policy://catalog"]
