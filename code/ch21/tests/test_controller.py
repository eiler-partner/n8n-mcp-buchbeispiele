from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Sequence

from controlled_research_agent.audit import JsonlAuditSink
from controlled_research_agent.controller import AgentController
from controlled_research_agent.domain import (
    FinalAnswer,
    RunLimits,
    RunRequest,
    RunStatus,
    ToolCall,
    ToolContract,
    ToolObservation,
)
from controlled_research_agent.tools import ToolRegistry

from conftest import ScriptedPlanner


def call(call_id: str, name: str, **arguments: object) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


def test_happy_path_requires_read_document(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(
        call("1", "search_catalog", query="MCP Tools", max_hits=2),
        call("2", "read_document", document_id="mcp-tools-2026"),
        FinalAnswer(answer="Clients validieren Ergebnisse.", document_ids=["mcp-tools-2026"]),
    )

    report = AgentController(planner, registry).run(RunRequest(question="Was ist zu kontrollieren?"))

    assert report.status is RunStatus.COMPLETED
    assert report.steps_used == 3
    assert report.document_ids == ["mcp-tools-2026"]
    assert [item.name for item in report.observations] == ["search_catalog", "read_document"]


def test_final_answer_cannot_cite_unread_document(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(FinalAnswer(answer="Unbelegt", document_ids=["mcp-tools-2026"]))

    report = AgentController(planner, registry).run(RunRequest(question="Was gilt?"))

    assert report.status is RunStatus.INVALID_FINAL_ANSWER
    assert report.answer is None


def test_identical_call_stops_loop(registry: ToolRegistry) -> None:
    repeated = call("1", "search_catalog", query="MCP", max_hits=2)
    planner = ScriptedPlanner(repeated, repeated.model_copy(update={"call_id": "2"}))

    report = AgentController(planner, registry).run(RunRequest(question="Suche MCP"))

    assert report.status is RunStatus.LOOP_DETECTED
    assert report.steps_used == 2


def test_step_budget_is_hard_limit(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(
        call("1", "search_catalog", query="MCP", max_hits=1),
        call("2", "search_catalog", query="Controller", max_hits=1),
    )
    request = RunRequest(question="Suche", limits=RunLimits(max_steps=2))

    report = AgentController(planner, registry).run(request)

    assert report.status is RunStatus.STEP_BUDGET_EXHAUSTED
    assert report.steps_used == 2


def test_unknown_tool_is_recorded_but_never_executed(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(
        call("1", "publish_report", text="secret"),
        call("2", "read_document", document_id="agent-control-note"),
        FinalAnswer(answer="Der Controller entscheidet.", document_ids=["agent-control-note"]),
    )

    report = AgentController(planner, registry).run(RunRequest(question="Wer entscheidet?"))

    assert report.status is RunStatus.COMPLETED
    assert report.observations[0].ok is False
    assert report.observations[0].error == "tool_not_allowed:publish_report"
    assert any(item.event == "tool_rejected" for item in report.audit)


def test_tool_argument_injection_is_rejected(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(
        call(
            "1",
            "read_document",
            document_id="mcp-tools-2026",
            callback_url="https://attacker.invalid",
        )
    )
    request = RunRequest(question="Lies", limits=RunLimits(max_steps=1))

    report = AgentController(planner, registry).run(request)

    assert report.status is RunStatus.STEP_BUDGET_EXHAUSTED
    assert report.observations[0].error == "arguments_or_result_failed_schema"


def test_per_tool_budget_terminates_distinct_calls(registry: ToolRegistry) -> None:
    planner = ScriptedPlanner(
        call("1", "search_catalog", query="MCP", max_hits=1),
        call("2", "search_catalog", query="Agent", max_hits=1),
    )
    limits = RunLimits(max_steps=3, max_calls_per_tool=1)

    report = AgentController(planner, registry).run(RunRequest(question="Suche", limits=limits))

    assert report.status is RunStatus.TOOL_BUDGET_EXHAUSTED
    assert "per-tool" in report.reason


def test_oversized_result_is_not_forwarded(tmp_path: Path, tiny_catalog_path: Path) -> None:
    import json

    payload = json.loads(tiny_catalog_path.read_text(encoding="utf-8"))
    payload["documents"][0]["text"] = "x" * 2_000
    tiny_catalog_path.write_text(json.dumps(payload), encoding="utf-8")
    registry = ToolRegistry.from_path(tiny_catalog_path)
    planner = ScriptedPlanner(call("1", "read_document", document_id="doc-1"))
    limits = RunLimits(max_steps=1, max_result_chars=500)

    report = AgentController(planner, registry).run(RunRequest(question="Lies das Dokument", limits=limits))

    assert report.observations[0].error == "tool_result_too_large"
    assert report.status is RunStatus.STEP_BUDGET_EXHAUSTED


def test_time_budget_is_checked_after_slow_planning(registry: ToolRegistry) -> None:
    class SlowPlanner:
        def decide(
            self,
            question: str,
            observations: Sequence[ToolObservation],
            tools: Sequence[ToolContract],
        ) -> ToolCall:
            sleep(0.02)
            return call("1", "search_catalog", query="MCP", max_hits=1)

    limits = RunLimits(max_steps=2, max_elapsed_seconds=0.005)
    report = AgentController(SlowPlanner(), registry).run(
        RunRequest(question="Suche MCP", limits=limits)
    )

    assert report.status is RunStatus.TIME_BUDGET_EXHAUSTED
    assert not report.observations


def test_provider_exception_is_redacted(registry: ToolRegistry) -> None:
    class BrokenPlanner:
        def decide(self, *args: object) -> ToolCall:
            raise RuntimeError("API key sk-secret-must-not-leak")

    report = AgentController(BrokenPlanner(), registry).run(RunRequest(question="Suche MCP"))

    assert report.status is RunStatus.PROVIDER_ERROR
    assert "secret" not in report.reason


def test_jsonl_audit_does_not_store_question(registry: ToolRegistry, tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    planner = ScriptedPlanner(FinalAnswer(answer="x", document_ids=["none"]))
    question = "personenbezogene geheime Frage"

    AgentController(planner, registry, JsonlAuditSink(path)).run(RunRequest(question=question))

    contents = path.read_text(encoding="utf-8")
    assert question not in contents
    assert "question_sha256" in contents
