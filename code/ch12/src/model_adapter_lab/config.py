from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .adapters import AnthropicMessagesAdapter, InvoiceExtractor, OllamaAdapter, OpenAIResponsesAdapter


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_provider: Literal["openai", "anthropic", "ollama"] = "ollama"
    openai_api_key: str | None = None
    openai_model: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = Field(default="qwen3:14b", min_length=1)

    @model_validator(mode="after")
    def selected_provider_is_configured(self) -> Settings:
        if self.model_provider == "openai" and not (self.openai_api_key and self.openai_model):
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
        if self.model_provider == "anthropic" and not (
            self.anthropic_api_key and self.anthropic_model
        ):
            raise ValueError("ANTHROPIC_API_KEY and ANTHROPIC_MODEL are required")
        return self


def build_adapter(settings: Settings) -> InvoiceExtractor:
    if settings.model_provider == "openai":
        from openai import OpenAI

        return OpenAIResponsesAdapter(
            client=OpenAI(api_key=settings.openai_api_key),
            model=settings.openai_model or "",
        )
    if settings.model_provider == "anthropic":
        from anthropic import Anthropic

        return AnthropicMessagesAdapter(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=settings.anthropic_model or "",
        )

    from ollama import Client

    return OllamaAdapter(client=Client(host=settings.ollama_host), model=settings.ollama_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
