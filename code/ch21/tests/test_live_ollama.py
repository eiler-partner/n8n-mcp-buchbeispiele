from __future__ import annotations

import os
from pathlib import Path

import pytest
from ollama import Client

from controlled_research_agent.controller import AgentController
from controlled_research_agent.domain import RunRequest, RunStatus
from controlled_research_agent.providers import OllamaPlanner
from controlled_research_agent.tools import ToolRegistry


@pytest.mark.live
def test_live_ollama_agent() -> None:
    if os.getenv("RUN_LIVE_AGENT_TESTS") != "1":
        pytest.skip("set RUN_LIVE_AGENT_TESTS=1 explicitly")
    model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        pytest.skip("OLLAMA_MODEL is not configured")
    registry = ToolRegistry.from_path(Path(__file__).parents[1] / "examples" / "catalog.json")
    planner = OllamaPlanner(Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")), model)

    report = AgentController(planner, registry).run(
        RunRequest(question="Welche Kontrollen verlangt der MCP-Toolvertrag?")
    )

    assert report.status is RunStatus.COMPLETED
    assert report.document_ids
