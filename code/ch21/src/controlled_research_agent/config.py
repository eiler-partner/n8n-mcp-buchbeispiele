from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .domain import RunLimits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_provider: Literal["openai", "anthropic", "ollama"] = "ollama"
    openai_api_key: str = ""
    openai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    agent_catalog_path: Path = Path("examples/catalog.json")
    agent_audit_path: Path = Path("var/audit.jsonl")
    agent_max_steps: int = Field(default=4, ge=1, le=12)
    agent_max_seconds: float = Field(default=45, gt=0, le=300)
    agent_max_result_chars: int = Field(default=8_000, ge=500, le=50_000)

    def limits(self) -> RunLimits:
        return RunLimits(
            max_steps=self.agent_max_steps,
            max_elapsed_seconds=self.agent_max_seconds,
            max_result_chars=self.agent_max_result_chars,
        )
