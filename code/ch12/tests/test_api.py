from __future__ import annotations

from fastapi.testclient import TestClient

from model_adapter_lab.api import app


def test_health_does_not_expose_model_or_credentials(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    from model_adapter_lab.config import get_settings

    get_settings.cache_clear()
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "ollama"}


def test_provider_error_becomes_classified_502(monkeypatch) -> None:
    from model_adapter_lab import api
    from model_adapter_lab.errors import FailureKind, ProviderError

    class Unreachable:
        def extract(self, request):
            raise ProviderError("ollama", FailureKind.TRANSPORT, "ollama request failed (transport)")

    monkeypatch.setattr(api, "build_adapter", lambda settings: Unreachable())
    response = TestClient(app).post("/extract", json={"document_id": "demo", "text": "Rechnung R-1, EUR 12,00"})

    assert response.status_code == 502
    assert response.json() == {"error": {"provider": "ollama", "kind": "transport", "retryable": True}}
