from __future__ import annotations

import os

import pytest

from model_adapter_lab.config import Settings, build_adapter
from model_adapter_lab.domain import ExtractionRequest


pytestmark = pytest.mark.live


def _enabled() -> bool:
    return os.getenv("RUN_LIVE_MODEL_TESTS") == "1"


@pytest.mark.parametrize("provider", ["ollama", "openai", "anthropic"])
def test_live_provider_contract(provider: str, monkeypatch) -> None:
    if not _enabled():
        pytest.skip("Set RUN_LIVE_MODEL_TESTS=1 to enable cost-bearing live tests")
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not configured")
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is not configured")

    monkeypatch.setenv("MODEL_PROVIDER", provider)
    settings = Settings()
    result = build_adapter(settings).extract(
        ExtractionRequest(
            document_id="live-invoice",
            text=(
                "Rechnung RE-2026-1042 der Alpenlicht GmbH vom 12.09.2026. "
                "Gesamtbetrag EUR 1.488,00. Zahlbar bis 12.10.2026."
            ),
        )
    )

    assert result.data.invoice_number == "RE-2026-1042"
    assert result.data.currency == "EUR"
    assert result.data.gross_amount is not None
