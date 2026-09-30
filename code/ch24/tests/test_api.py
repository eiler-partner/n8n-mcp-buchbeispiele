from __future__ import annotations

from fastapi.testclient import TestClient

from document_release_service.api import create_app
from document_release_service.config import Settings
from document_release_service.repository import MemoryRepository


SETTINGS = Settings(
    database_url="unused",
    mcp_token="mcp",
    approval_key="approval",
    executor_key="executor",
    signing_key=b"signing",
)


def client() -> TestClient:
    return TestClient(create_app(MemoryRepository(), SETTINGS))


def test_health() -> None:
    with client() as http:
        assert http.get("/health").json() == {"status": "ok"}


def test_correlation_header_is_preserved() -> None:
    with client() as http:
        response = http.post(
            "/documents",
            headers={"X-Tenant-ID": "tenant-a", "X-Correlation-ID": "corr-24"},
            json={
                "document_id": "DOC-024",
                "title": "Testdokument",
                "source": "fixture:test.txt",
                "text": "Ein ausreichend langer synthetischer Dokumenttext.",
                "trusted": True,
            },
        )
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "corr-24"
        assert response.json()["correlation_id"] == "corr-24"


def test_approval_channel_rejects_wrong_key() -> None:
    with client() as http:
        response = http.post(
            "/publication-requests/unknown/decision",
            headers={"X-Approval-Key": "wrong"},
            json={"reviewer": "reviewer@example.invalid", "approve": True},
        )
        assert response.status_code == 401
