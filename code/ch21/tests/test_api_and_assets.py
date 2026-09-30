from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from controlled_research_agent.api import create_app
from controlled_research_agent.config import Settings


def test_health_does_not_contact_provider(tmp_path: Path, tiny_catalog_path: Path) -> None:
    settings = Settings(
        model_provider="ollama",
        agent_catalog_path=tiny_catalog_path,
        agent_audit_path=tmp_path / "audit.jsonl",
    )

    response = TestClient(create_app(settings)).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "ollama"}


def test_n8n_workflow_is_importable_json() -> None:
    path = Path(__file__).parents[1] / "n8n" / "controlled-research.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))

    assert workflow["active"] is False
    assert len(workflow["nodes"]) == 5
    assert {node["name"] for node in workflow["nodes"]} >= {
        "Kontrollierter Agent",
        "Nur validiertes Ergebnis",
        "Freigabekandidat",
    }
