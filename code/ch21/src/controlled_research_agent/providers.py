from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from pydantic import ValidationError

from .domain import (
    SYSTEM_INSTRUCTIONS,
    FinalAnswer,
    PlannerDecision,
    ToolCall,
    ToolContract,
    ToolObservation,
)


def _transcript(question: str, observations: Sequence[ToolObservation]) -> str:
    rows = [f"Auftrag: {question}"]
    for item in observations:
        rows.append(
            json.dumps(
                {
                    "tool": item.name,
                    "arguments": item.arguments,
                    "ok": item.ok,
                    "result": item.result,
                    "error": item.error,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    rows.append("Waehle den naechsten Tool Call oder liefere das finale JSON-Objekt.")
    return "\n".join(rows)


def _final_from_text(text: str) -> FinalAnswer:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(candidate)
    return FinalAnswer.model_validate(value)


def _openai_tools(tools: Sequence[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
            "strict": True,
        }
        for tool in tools
    ]


def _anthropic_tools(tools: Sequence[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "strict": True,
        }
        for tool in tools
    ]


def _ollama_tools(tools: Sequence[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


@dataclass(slots=True)
class OpenAIPlanner:
    client: Any
    model: str

    def decide(
        self,
        question: str,
        observations: Sequence[ToolObservation],
        tools: Sequence[ToolContract],
    ) -> PlannerDecision:
        response = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=_transcript(question, observations),
            tools=_openai_tools(tools),
            tool_choice="auto",
            parallel_tool_calls=False,
            store=False,
        )
        for item in response.output:
            if getattr(item, "type", None) == "function_call":
                return ToolCall(
                    call_id=item.call_id,
                    name=item.name,
                    arguments=json.loads(item.arguments),
                )
        return _final_from_text(response.output_text)


@dataclass(slots=True)
class AnthropicPlanner:
    client: Any
    model: str

    def decide(
        self,
        question: str,
        observations: Sequence[ToolObservation],
        tools: Sequence[ToolContract],
    ) -> PlannerDecision:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            system=SYSTEM_INSTRUCTIONS,
            messages=[{"role": "user", "content": _transcript(question, observations)}],
            tools=_anthropic_tools(tools),
            tool_choice={"type": "auto"},
            disable_parallel_tool_use=True,
        )
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return ToolCall(
                    call_id=block.id,
                    name=block.name,
                    arguments=block.input,
                )
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return _final_from_text("".join(text_parts))


@dataclass(slots=True)
class OllamaPlanner:
    client: Any
    model: str

    def decide(
        self,
        question: str,
        observations: Sequence[ToolObservation],
        tools: Sequence[ToolContract],
    ) -> PlannerDecision:
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": _transcript(question, observations)},
            ],
            tools=_ollama_tools(tools),
            think=False,
            stream=False,
            options={"temperature": 0, "num_predict": 1200},
        )
        calls = response.message.tool_calls or []
        if calls:
            call = calls[0]
            return ToolCall(
                call_id=f"ollama-{len(observations) + 1}",
                name=call.function.name,
                arguments=call.function.arguments,
            )
        return _final_from_text(response.message.content)


class ProviderOutputError(ValueError):
    """Stable public error for malformed provider output."""


def safe_decide(planner: Any, *args: Any) -> PlannerDecision:
    try:
        return planner.decide(*args)
    except (ValidationError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise ProviderOutputError("provider returned no valid planner decision") from exc
