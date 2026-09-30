from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from pydantic import ValidationError

from .domain import (
    SYSTEM_INSTRUCTIONS,
    ExtractedInvoice,
    ExtractionEnvelope,
    ExtractionRequest,
)
from .errors import FailureKind, ProviderError


class InvoiceExtractor(Protocol):
    provider: str
    model: str

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope: ...


def _envelope(
    request: ExtractionRequest,
    provider: str,
    model: str,
    started: float,
    data: ExtractedInvoice,
) -> ExtractionEnvelope:
    return ExtractionEnvelope(
        document_id=request.document_id,
        provider=provider,
        model=model,
        latency_ms=max(0, round((perf_counter() - started) * 1000)),
        data=data,
    )


def _validated(provider: str, value: Any) -> ExtractedInvoice:
    try:
        if isinstance(value, ExtractedInvoice):
            return value
        return ExtractedInvoice.model_validate(value)
    except ValidationError as exc:
        raise ProviderError(provider, FailureKind.INVALID_OUTPUT, "Schema validation failed") from exc


@dataclass(slots=True)
class OpenAIResponsesAdapter:
    client: Any
    model: str
    provider: str = "openai"

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope:
        started = perf_counter()
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": request.text},
                ],
                text_format=ExtractedInvoice,
            )
        except Exception as exc:  # SDK exception types are mapped in one boundary.
            raise _map_sdk_error(self.provider, exc) from exc
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderError(self.provider, FailureKind.REFUSAL, "No parsed output returned")
        return _envelope(request, self.provider, self.model, started, _validated(self.provider, parsed))


@dataclass(slots=True)
class AnthropicMessagesAdapter:
    client: Any
    model: str
    provider: str = "anthropic"

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope:
        started = perf_counter()
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": request.text}],
                output_format=ExtractedInvoice,
            )
        except Exception as exc:
            raise _map_sdk_error(self.provider, exc) from exc
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ProviderError(self.provider, FailureKind.REFUSAL, "No parsed output returned")
        return _envelope(request, self.provider, self.model, started, _validated(self.provider, parsed))


@dataclass(slots=True)
class OllamaAdapter:
    client: Any
    model: str
    provider: str = "ollama"

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope:
        started = perf_counter()
        schema = ExtractedInvoice.model_json_schema()
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": request.text + "\n\nJSON-Schema:\n" + json.dumps(schema),
                    },
                ],
                format=schema,
                think=False,
                options={"temperature": 0, "num_predict": 1024},
            )
            content = response.message.content
            parsed = ExtractedInvoice.model_validate_json(content)
        except ValidationError as exc:
            raise ProviderError(self.provider, FailureKind.INVALID_OUTPUT, "Schema validation failed") from exc
        except Exception as exc:
            raise _map_sdk_error(self.provider, exc) from exc
        return _envelope(request, self.provider, self.model, started, parsed)


def _map_sdk_error(provider: str, exc: Exception) -> ProviderError:
    """Normalize SDK-specific failures without leaking prompts or credentials."""

    name = type(exc).__name__.lower()
    status = getattr(exc, "status_code", None)
    if status in {401, 403} or "authentication" in name or "permission" in name:
        kind = FailureKind.AUTHENTICATION
    elif status == 429 or "ratelimit" in name:
        kind = FailureKind.RATE_LIMIT
    elif isinstance(status, int) and status >= 500:
        kind = FailureKind.SERVER
    elif "connection" in name or "timeout" in name:
        kind = FailureKind.TRANSPORT
    else:
        kind = FailureKind.POLICY
    return ProviderError(provider, kind, f"{provider} request failed ({kind.value})")
