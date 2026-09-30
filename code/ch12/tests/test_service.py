from __future__ import annotations

from dataclasses import dataclass

import pytest

from model_adapter_lab.domain import ExtractedInvoice, ExtractionEnvelope, ExtractionRequest
from model_adapter_lab.errors import FailureKind, ProviderError
from model_adapter_lab.service import ExtractionService

from fakes import VALID_DATA


REQUEST = ExtractionRequest(document_id="invoice-1", text="invoice")


@dataclass
class StubAdapter:
    provider: str
    model: str
    failure: FailureKind | None = None

    def extract(self, request: ExtractionRequest) -> ExtractionEnvelope:
        if self.failure:
            raise ProviderError(self.provider, self.failure, "controlled failure")
        return ExtractionEnvelope(
            document_id=request.document_id,
            provider=self.provider,
            model=self.model,
            latency_ms=1,
            data=ExtractedInvoice.model_validate(VALID_DATA),
        )


@pytest.mark.parametrize("kind", [FailureKind.TRANSPORT, FailureKind.RATE_LIMIT, FailureKind.SERVER])
def test_fallback_only_for_retryable_failures(kind: FailureKind) -> None:
    service = ExtractionService(
        primary=StubAdapter("cloud-a", "a", failure=kind),
        fallback=StubAdapter("local", "b"),
    )

    assert service.extract(REQUEST).provider == "local"


@pytest.mark.parametrize(
    "kind",
    [FailureKind.AUTHENTICATION, FailureKind.INVALID_OUTPUT, FailureKind.REFUSAL, FailureKind.POLICY],
)
def test_no_silent_fallback_for_semantic_or_policy_failures(kind: FailureKind) -> None:
    service = ExtractionService(
        primary=StubAdapter("cloud-a", "a", failure=kind),
        fallback=StubAdapter("local", "b"),
    )

    with pytest.raises(ProviderError) as caught:
        service.extract(REQUEST)

    assert caught.value.kind is kind


def test_provider_switch_does_not_change_business_contract() -> None:
    results = [
        ExtractionService(primary=StubAdapter("openai", "configured-a")).extract(REQUEST),
        ExtractionService(primary=StubAdapter("anthropic", "configured-b")).extract(REQUEST),
        ExtractionService(primary=StubAdapter("ollama", "configured-c")).extract(REQUEST),
    ]

    assert {item.data.model_dump_json() for item in results} == {
        ExtractedInvoice.model_validate(VALID_DATA).model_dump_json()
    }
    assert {item.provider for item in results} == {"openai", "anthropic", "ollama"}
