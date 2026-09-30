from __future__ import annotations

from anthropic import Anthropic
from ollama import Client as OllamaClient
from openai import OpenAI

from .audit import JsonlAuditSink
from .config import Settings
from .controller import AgentController
from .providers import AnthropicPlanner, OllamaPlanner, OpenAIPlanner
from .tools import ToolRegistry


def build_controller(settings: Settings) -> AgentController:
    registry = ToolRegistry.from_path(settings.agent_catalog_path)
    if settings.model_provider == "openai":
        if not settings.openai_api_key or not settings.openai_model:
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
        planner = OpenAIPlanner(
            client=OpenAI(api_key=settings.openai_api_key),
            model=settings.openai_model,
        )
    elif settings.model_provider == "anthropic":
        if not settings.anthropic_api_key or not settings.anthropic_model:
            raise ValueError("ANTHROPIC_API_KEY and ANTHROPIC_MODEL are required")
        planner = AnthropicPlanner(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=settings.anthropic_model,
        )
    else:
        planner = OllamaPlanner(
            client=OllamaClient(host=settings.ollama_host),
            model=settings.ollama_model,
        )
    return AgentController(
        planner=planner,
        registry=registry,
        audit_sink=JsonlAuditSink(settings.agent_audit_path),
    )
