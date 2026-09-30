from __future__ import annotations

from types import SimpleNamespace

from controlled_research_agent.domain import FinalAnswer, ToolCall
from controlled_research_agent.providers import AnthropicPlanner, OllamaPlanner, OpenAIPlanner
from controlled_research_agent.tools import ToolRegistry


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self.response


def test_openai_planner_disables_parallel_calls(registry: ToolRegistry) -> None:
    api = FakeResponses(
        SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call-1",
                    name="search_catalog",
                    arguments='{"query":"MCP","max_hits":2}',
                )
            ],
            output_text="",
        )
    )
    planner = OpenAIPlanner(SimpleNamespace(responses=api), "configured-model")

    decision = planner.decide("Suche", (), registry.contracts)

    assert isinstance(decision, ToolCall)
    assert api.kwargs["parallel_tool_calls"] is False
    assert api.kwargs["store"] is False
    assert len(api.kwargs["tools"]) == 2  # type: ignore[arg-type]


def test_anthropic_planner_uses_strict_tool_schema(registry: ToolRegistry) -> None:
    class Messages:
        kwargs: dict[str, object]

        def create(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="toolu-1",
                        name="read_document",
                        input={"document_id": "mcp-tools-2026"},
                    )
                ]
            )

    messages = Messages()
    planner = AnthropicPlanner(SimpleNamespace(messages=messages), "configured-model")

    decision = planner.decide("Lies", (), registry.contracts)

    assert isinstance(decision, ToolCall)
    assert messages.kwargs["disable_parallel_tool_use"] is True
    assert all(tool["strict"] is True for tool in messages.kwargs["tools"])  # type: ignore[index,union-attr]


def test_ollama_planner_can_return_final_answer(registry: ToolRegistry) -> None:
    class Client:
        def chat(self, **kwargs: object) -> object:
            return SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[],
                    content='{"answer":"Belegt","document_ids":["mcp-tools-2026"]}',
                )
            )

    decision = OllamaPlanner(Client(), "configured-model").decide(
        "Antworte", (), registry.contracts
    )

    assert isinstance(decision, FinalAnswer)
    assert decision.document_ids == ["mcp-tools-2026"]
