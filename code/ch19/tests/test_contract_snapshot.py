from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mcp_contract_lab.contract import (
    ContractMismatch,
    compare_snapshot,
    load_snapshot,
    snapshot_server,
)
from mcp_contract_lab.servers import policy_server


CONTRACT = Path(__file__).parents[1] / "contracts" / "policy-server.json"


@pytest.mark.anyio
async def test_server_matches_reviewed_contract() -> None:
    actual = await snapshot_server(policy_server)
    compare_snapshot(actual, load_snapshot(CONTRACT))


@pytest.mark.anyio
async def test_breaking_schema_change_is_visible() -> None:
    actual = await snapshot_server(policy_server)
    changed = deepcopy(actual)
    search_tool = next(tool for tool in changed["tools"] if tool["name"] == "search_policies")
    search_tool["inputSchema"]["required"].append("limit")
    with pytest.raises(ContractMismatch, match="MCP-Vertrag hat sich geändert"):
        compare_snapshot(changed, actual)
