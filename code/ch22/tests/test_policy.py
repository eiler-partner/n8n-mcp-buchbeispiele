from __future__ import annotations

import pytest

from n8n_mcp_lab.policy import ContractViolation, ProtocolObservation, ToolPolicy


TOOLS = [
    {"name": "catalog_lookup", "description": "read"},
    {"name": "maintenance_reset", "description": "write"},
]


def test_selected_mode_exposes_only_explicit_read_tool() -> None:
    selected = ToolPolicy(frozenset({"catalog_lookup"})).select(TOOLS)
    assert [tool["name"] for tool in selected] == ["catalog_lookup"]


def test_missing_allowed_tool_fails_closed() -> None:
    with pytest.raises(ContractViolation, match="fehlen"):
        ToolPolicy(frozenset({"missing_tool"})).select(TOOLS)


def test_unapproved_call_is_rejected_again_at_execution_boundary() -> None:
    with pytest.raises(ContractViolation, match="nicht freigegeben"):
        ToolPolicy(frozenset({"catalog_lookup"})).require_call("maintenance_reset")


def test_protocol_observation_uses_wire_values() -> None:
    observed = ProtocolObservation.from_initialize_and_tools(
        endpoint="http://n8n:5678/mcp/example",
        transport="streamable-http",
        initialize={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": "n8n MCP Server Trigger", "version": "2.0"},
            },
        },
        tools_result={
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": [{"name": "catalog_lookup"}]},
        },
    )
    assert observed.protocol_version == "2025-11-25"
    assert observed.tools == ("catalog_lookup",)


def test_call_summary_keeps_ids_not_raw_text() -> None:
    from n8n_mcp_lab.probe import summarize_call

    result = {"result": {"isError": False, "structuredContent": {"hits": [
        {"item_id": "N8N-022", "title": "n8n-MCP-Integrationsmuster", "status": "approved"}]}}}
    assert summarize_call("n8n", result) == {
        "tool": "catalog_lookup", "query": "n8n", "is_error": False, "item_ids": ["N8N-022"]}
