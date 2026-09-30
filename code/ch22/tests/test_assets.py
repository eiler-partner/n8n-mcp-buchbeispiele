from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_workflow_assets_are_valid_and_enforce_expected_node_modes() -> None:
    client = json.loads((ROOT / "n8n" / "client-agent.json").read_text(encoding="utf-8"))
    server = json.loads((ROOT / "n8n" / "server-trigger.json").read_text(encoding="utf-8"))
    implementation = json.loads(
        (ROOT / "n8n" / "catalog-tool-workflow.json").read_text(encoding="utf-8")
    )

    client_nodes = {node["type"]: node for node in client["nodes"]}
    mcp_client = client_nodes["@n8n/n8n-nodes-langchain.mcpClientTool"]
    assert mcp_client["typeVersion"] >= 1.4
    assert mcp_client["parameters"]["serverTransport"] == "httpStreamable"
    assert mcp_client["parameters"]["include"] == "selected"
    assert mcp_client["parameters"]["includeTools"] == ["catalog_lookup"]

    server_nodes = {node["type"]: node for node in server["nodes"]}
    trigger = server_nodes["@n8n/n8n-nodes-langchain.mcpTrigger"]
    tool = server_nodes["@n8n/n8n-nodes-langchain.toolWorkflow"]
    assert trigger["parameters"]["path"] == "ch22-catalog"
    assert tool["parameters"]["name"] == "catalog_lookup"
    assert tool["parameters"]["workflowId"]["value"] == implementation["id"]
    assert tool["parameters"]["workflowInputs"]["schema"][0]["id"] == "query"
    assert "maintenance_reset" not in json.dumps(server)


def test_proxy_profile_preserves_streaming() -> None:
    nginx = (ROOT / "proxy" / "nginx.conf").read_text(encoding="utf-8")
    for directive in (
        "proxy_buffering off",
        "gzip off",
        "chunked_transfer_encoding off",
        "proxy_set_header Connection ''",
    ):
        assert directive in nginx


def test_compose_pins_n8n_and_loopback_ports() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "n8nio/n8n:2.40.7" in compose
    assert "127.0.0.1:5678:5678" in compose
    assert "127.0.0.1:8022:8022" in compose


def test_verification_report_records_wire_version_and_negative_auth() -> None:
    report = json.loads(
        (ROOT / "reports" / "verification-2026-09-29.json").read_text(encoding="utf-8")
    )
    assert report["n8n"]["version"] == "2.40.7"
    assert report["n8n_server_trigger"]["era"] == "legacy"
    assert report["n8n_server_trigger"]["modern_probe"]["http_status"] == 400
    assert report["python_reference_server"]["era"] == "dual"
    assert report["n8n_server_trigger"]["observed_protocol_version"] == "2025-11-25"
    assert report["n8n_server_trigger"]["call_result_id"] == "N8N-022"
    assert report["n8n_server_trigger"]["missing_token_status"] == 403
    assert report["n8n_server_trigger"]["call_succeeded"] is True
    assert report["scope"]["queue_failover_tested"] is False
