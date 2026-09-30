from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.server import MCPServer


class ContractMismatch(AssertionError):
    """Der sichtbare MCP-Vertrag weicht vom freigegebenen Snapshot ab."""


def _normalized(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True, mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {key: _normalized(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_normalized(item) for item in value]
        if all(isinstance(item, dict) and "name" in item for item in normalized):
            return sorted(normalized, key=lambda item: item["name"])
        if all(isinstance(item, dict) and "uri" in item for item in normalized):
            return sorted(normalized, key=lambda item: item["uri"])
        return normalized
    return value


async def snapshot_server(server: MCPServer) -> dict[str, Any]:
    """Erzeuge den vom Client tatsächlich sichtbaren Vertrag eines Servers."""
    async with Client(server, raise_exceptions=True) as client:
        tools = await client.list_tools(cache_mode="refresh")
        resources = await client.list_resources(cache_mode="refresh")
        templates = await client.list_resource_templates(cache_mode="refresh")
        return _normalized(
            {
                "protocolVersion": client.protocol_version,
                "serverInfo": client.server_info,
                "capabilities": client.server_capabilities,
                "tools": tools.tools,
                "resources": resources.resources,
                "resourceTemplates": templates.resource_templates,
            }
        )


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def compare_snapshot(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if actual != expected:
        actual_text = json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True)
        expected_text = json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True)
        raise ContractMismatch(
            "MCP-Vertrag hat sich geändert. Snapshot nur nach fachlichem Review aktualisieren.\n"
            f"--- erwartet ---\n{expected_text}\n--- tatsächlich ---\n{actual_text}"
        )
