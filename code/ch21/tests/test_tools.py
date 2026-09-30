from __future__ import annotations

import pytest

from controlled_research_agent.tools import ToolRegistry, ToolRejected


def test_registry_exposes_exactly_two_read_only_tools(registry: ToolRegistry) -> None:
    assert [tool.name for tool in registry.contracts] == ["search_catalog", "read_document"]


def test_search_is_bounded(registry: ToolRegistry) -> None:
    result = registry.execute("search_catalog", {"query": "Schrittbudgets Anwendung", "max_hits": 2})

    assert len(result["hits"]) <= 2
    assert result["hits"][0]["document_id"] == "agent-control-note"


def test_unknown_tool_is_rejected(registry: ToolRegistry) -> None:
    with pytest.raises(ToolRejected, match="tool_not_allowed"):
        registry.execute("publish_report", {"text": "no"})


def test_extra_argument_is_rejected(registry: ToolRegistry) -> None:
    with pytest.raises(ToolRejected, match="schema"):
        registry.execute(
            "search_catalog",
            {"query": "MCP", "max_hits": 2, "callback_url": "https://attacker.invalid"},
        )


def test_invalid_document_id_is_rejected(registry: ToolRegistry) -> None:
    with pytest.raises(ToolRejected, match="schema"):
        registry.execute("read_document", {"document_id": "../../etc/passwd"})


def test_missing_document_is_rejected(registry: ToolRegistry) -> None:
    with pytest.raises(ToolRejected, match="document_not_found"):
        registry.execute("read_document", {"document_id": "not-there"})
