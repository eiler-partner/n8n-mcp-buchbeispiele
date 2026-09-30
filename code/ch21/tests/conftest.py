from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Sequence

import pytest

from controlled_research_agent.domain import PlannerDecision, ToolContract, ToolObservation
from controlled_research_agent.tools import ToolRegistry


class ScriptedPlanner:
    def __init__(self, *decisions: PlannerDecision) -> None:
        self.decisions = deque(decisions)
        self.seen_observations: list[tuple[ToolObservation, ...]] = []

    def decide(
        self,
        question: str,
        observations: Sequence[ToolObservation],
        tools: Sequence[ToolContract],
    ) -> PlannerDecision:
        self.seen_observations.append(tuple(observations))
        return self.decisions.popleft()


@pytest.fixture
def catalog_path() -> Path:
    return Path(__file__).parents[1] / "examples" / "catalog.json"


@pytest.fixture
def registry(catalog_path: Path) -> ToolRegistry:
    return ToolRegistry.from_path(catalog_path)


@pytest.fixture
def tiny_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "document_id": "doc-1",
                        "title": "Budget",
                        "text": "Ein Agent braucht ein Schrittbudget.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path
