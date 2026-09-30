from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_pins_n8n_and_jaeger() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "n8nio/n8n:2.40.7" in compose
    assert "jaeger:2.21.0" in compose
    assert "127.0.0.1:" in compose


def test_workflows_have_stable_ids() -> None:
    workflows = sorted((ROOT / "n8n" / "workflows").glob("*.json"))
    assert workflows
    for path in workflows:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["id"].startswith("ch24")
        assert value["settings"]["executionOrder"] == "v1"


def test_no_real_secrets_in_environment_example() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "change-me" in text
    assert "sk-" not in text
