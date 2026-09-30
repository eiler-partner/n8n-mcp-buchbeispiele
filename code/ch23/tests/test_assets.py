from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_n8n_workflow_is_valid_and_defaults_to_hardened_mode() -> None:
    workflow = json.loads(
        (ROOT / "n8n" / "deterministic-boundary.json").read_text(encoding="utf-8")
    )
    node_types = {node["type"] for node in workflow["nodes"]}
    assert "n8n-nodes-base.httpRequest" in node_types
    assert "n8n-nodes-base.if" in node_types
    assert '"value": "hardened"' in json.dumps(workflow)
    assert "CANARY-" not in json.dumps(workflow)


def test_compose_is_local_pinned_and_blocks_dangerous_nodes() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "n8nio/n8n:2.40.7" in compose
    assert "127.0.0.1:8023:8023" in compose
    assert "127.0.0.1:8024:8024" in compose
    assert "driver: bridge" in compose
    assert "n8n-nodes-base.executeCommand" in compose
    assert "n8n-nodes-base.readWriteFile" in compose
    # NODES_EXCLUDE ersetzt die n8n-Standardliste; der Local File Trigger
    # muss deshalb ausdrücklich gesperrt bleiben.
    assert "n8n-nodes-base.localFileTrigger" in compose


def test_environment_contains_only_synthetic_canary() -> None:
    environment = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "CANARY-CH23-NOT-A-REAL-SECRET" in environment
    for forbidden in ("sk-", "ghp_", "AKIA"):
        assert forbidden not in environment
