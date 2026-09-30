from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from hashlib import sha256
from time import monotonic
from typing import Protocol, Sequence
from uuid import uuid4

from .audit import AuditSink, NullAuditSink
from .domain import (
    AuditEvent,
    FinalAnswer,
    PlannerDecision,
    RunReport,
    RunRequest,
    RunStatus,
    ToolCall,
    ToolContract,
    ToolObservation,
)
from .tools import ToolRegistry, ToolRejected


class Planner(Protocol):
    def decide(
        self,
        question: str,
        observations: Sequence[ToolObservation],
        tools: Sequence[ToolContract],
    ) -> PlannerDecision: ...


class AgentController:
    """Owns the loop. The model proposes; this class authorizes and executes."""

    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._planner = planner
        self._registry = registry
        self._audit_sink = audit_sink or NullAuditSink()

    def run(self, request: RunRequest) -> RunReport:
        run_id = uuid4().hex
        started = monotonic()
        observations: list[ToolObservation] = []
        events: list[AuditEvent] = []
        fingerprints: set[str] = set()
        calls_per_tool: Counter[str] = Counter()
        read_documents: set[str] = set()

        def emit(event: str, detail: dict[str, object]) -> None:
            item = AuditEvent(sequence=len(events) + 1, event=event, detail=detail)  # type: ignore[arg-type]
            events.append(item)
            self._audit_sink.record(run_id, item)

        def finish(
            status: RunStatus,
            reason: str,
            *,
            steps: int,
            answer: FinalAnswer | None = None,
        ) -> RunReport:
            emit("run_finished", {"status": status.value, "reason": reason})
            return RunReport(
                run_id=run_id,
                status=status,
                answer=answer.answer if answer else None,
                document_ids=answer.document_ids if answer else [],
                observations=observations,
                audit=events,
                steps_used=steps,
                elapsed_ms=max(0, round((monotonic() - started) * 1000)),
                reason=reason,
            )

        emit(
            "run_started",
            {
                "question_sha256": sha256(request.question.encode("utf-8")).hexdigest(),
                "limits": request.limits.model_dump(mode="json"),
                "allowed_tools": [tool.name for tool in self._registry.contracts],
            },
        )

        for step in range(1, request.limits.max_steps + 1):
            remaining = request.limits.max_elapsed_seconds - (monotonic() - started)
            if remaining <= 0:
                return finish(
                    RunStatus.TIME_BUDGET_EXHAUSTED,
                    "time budget exhausted before planner call",
                    steps=step - 1,
                )
            try:
                decision = self._planner.decide(
                    request.question,
                    tuple(observations),
                    self._registry.contracts,
                )
            except Exception:
                return finish(
                    RunStatus.PROVIDER_ERROR,
                    "planner failed without exposing provider details",
                    steps=step,
                )

            if isinstance(decision, FinalAnswer):
                cited = set(decision.document_ids)
                if not cited or not cited.issubset(read_documents):
                    return finish(
                        RunStatus.INVALID_FINAL_ANSWER,
                        "final answer cites documents that were not read",
                        steps=step,
                    )
                return finish(
                    RunStatus.COMPLETED,
                    "validated final answer",
                    steps=step,
                    answer=decision,
                )

            call = ToolCall.model_validate(decision)
            fingerprint = _fingerprint(call)
            if fingerprint in fingerprints:
                return finish(
                    RunStatus.LOOP_DETECTED,
                    "identical tool call repeated",
                    steps=step,
                )
            fingerprints.add(fingerprint)
            calls_per_tool[call.name] += 1
            if calls_per_tool[call.name] > request.limits.max_calls_per_tool:
                return finish(
                    RunStatus.TOOL_BUDGET_EXHAUSTED,
                    "per-tool call budget exceeded",
                    steps=step,
                )

            remaining = request.limits.max_elapsed_seconds - (monotonic() - started)
            if remaining <= 0:
                return finish(
                    RunStatus.TIME_BUDGET_EXHAUSTED,
                    "time budget exhausted before tool call",
                    steps=step,
                )
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._registry.execute, call.name, call.arguments)
                    result = future.result(timeout=remaining)
                encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
                if len(encoded) > request.limits.max_result_chars:
                    raise ToolRejected("tool_result_too_large")
                observation = ToolObservation(
                    call_id=call.call_id,
                    name=call.name,
                    arguments=call.arguments,
                    ok=True,
                    result=result,
                )
                if call.name == "read_document":
                    read_documents.add(str(result["document_id"]))
                emit(
                    "tool_completed",
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "result_chars": len(encoded),
                    },
                )
            except FutureTimeout:
                return finish(
                    RunStatus.TIME_BUDGET_EXHAUSTED,
                    "tool call exceeded remaining time budget",
                    steps=step,
                )
            except ToolRejected as exc:
                observation = ToolObservation(
                    call_id=call.call_id,
                    name=call.name,
                    arguments=call.arguments,
                    ok=False,
                    error=str(exc),
                )
                emit(
                    "tool_rejected",
                    {"call_id": call.call_id, "name": call.name, "reason": str(exc)},
                )
            observations.append(observation)

        return finish(
            RunStatus.STEP_BUDGET_EXHAUSTED,
            "maximum number of planner steps reached",
            steps=request.limits.max_steps,
        )


def _fingerprint(call: ToolCall) -> str:
    canonical = json.dumps(
        {"name": call.name, "arguments": call.arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
