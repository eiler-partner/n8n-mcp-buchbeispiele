from __future__ import annotations

import pytest

from model_adapter_lab.adapters import AnthropicMessagesAdapter, OllamaAdapter, OpenAIResponsesAdapter
from model_adapter_lab.domain import ExtractedInvoice, ExtractionRequest
from model_adapter_lab.errors import FailureKind, ProviderError

from fakes import FakeAnthropic, FakeOllama, FakeOpenAI, Recorder


REQUEST = ExtractionRequest(document_id="invoice-1", text="Rechnung RE-2026-1042 ...")


def test_openai_uses_responses_and_pydantic_contract() -> None:
    recorder = Recorder()
    result = OpenAIResponsesAdapter(FakeOpenAI(recorder), "configured-openai-model").extract(REQUEST)

    assert recorder.kwargs["text_format"] is ExtractedInvoice
    assert recorder.kwargs["model"] == "configured-openai-model"
    assert result.provider == "openai"
    assert result.data.invoice_number == "RE-2026-1042"


def test_anthropic_uses_messages_parse_and_same_contract() -> None:
    recorder = Recorder()
    result = AnthropicMessagesAdapter(FakeAnthropic(recorder), "configured-anthropic-model").extract(
        REQUEST
    )

    assert recorder.kwargs["output_format"] is ExtractedInvoice
    assert recorder.kwargs["model"] == "configured-anthropic-model"
    assert result.provider == "anthropic"
    assert result.data.invoice_number == "RE-2026-1042"


def test_ollama_sends_schema_and_validates_json() -> None:
    recorder = Recorder()
    result = OllamaAdapter(FakeOllama(recorder), "configured-local-model").extract(REQUEST)

    assert recorder.kwargs["format"]["additionalProperties"] is False
    assert recorder.kwargs["think"] is False
    assert recorder.kwargs["options"]["temperature"] == 0
    assert result.provider == "ollama"
    assert result.data.invoice_number == "RE-2026-1042"


def test_ollama_rejects_invalid_output() -> None:
    adapter = OllamaAdapter(FakeOllama(Recorder(), '{"status":"complete"}'), "local")

    with pytest.raises(ProviderError) as caught:
        adapter.extract(REQUEST)

    assert caught.value.kind is FailureKind.INVALID_OUTPUT
    assert not caught.value.retryable
