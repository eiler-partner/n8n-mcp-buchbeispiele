from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from .policy import ProtocolObservation, ToolPolicy


def decode_mcp_response(response: httpx.Response) -> dict[str, Any]:
    """Decode JSON or the first JSON-RPC object from an SSE response."""
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("MCP-Antwort ist kein JSON-Objekt")
        return value
    for line in response.text.splitlines():
        if line.startswith("data:"):
            value = json.loads(line.removeprefix("data:").strip())
            if isinstance(value, dict):
                return value
    raise ValueError("Keine JSON-RPC-Antwort in HTTP/SSE-Nutzlast")


def _post(
    client: httpx.Client,
    endpoint: str,
    payload: dict[str, Any],
    *,
    protocol_version: str | None = None,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = client.post(endpoint, headers=headers, json=payload)
    response.raise_for_status()
    return decode_mcp_response(response), response.headers.get("Mcp-Session-Id", session_id)


MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
# Fehler, die laut MCP 2026-07-28 einen modernen Server erkennen lassen.
MODERN_ERROR_CODES = {-32020, -32021, -32022}


def probe_modern_era(client: httpx.Client, endpoint: str) -> dict[str, Any]:
    """Prüft mit server/discover, ob der Endpunkt die zustandslose Revision spricht.

    Nach der Spezifikation erkennt ein Client einen modernen Server an einem
    DiscoverResult oder an einem modernen JSON-RPC-Fehler. Jede andere
    Antwort (etwa 400 ohne modernen Fehlerkörper) weist auf einen Legacy-Server.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": "discover-1",
        "method": "server/discover",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "chapter-22-probe", "version": "1.1.0"},
            }
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MODERN_VERSION,
        "Mcp-Method": "server/discover",
    }
    response = client.post(endpoint, headers=headers, json=payload)
    observation: dict[str, Any] = {"http_status": response.status_code, "era": "legacy"}
    try:
        body = decode_mcp_response(response)
    except (ValueError, json.JSONDecodeError):
        return observation
    result = body.get("result")
    error = body.get("error")
    if isinstance(result, dict):
        observation["era"] = "modern"
        observation["supported_versions"] = list(result.get("supportedVersions", []))
    elif isinstance(error, dict) and error.get("code") in MODERN_ERROR_CODES:
        observation["era"] = "modern"
        observation["error_code"] = error.get("code")
        data = error.get("data")
        if isinstance(data, dict) and isinstance(data.get("supported"), list):
            observation["supported_versions"] = list(data["supported"])
    elif isinstance(error, dict):
        observation["error_code"] = error.get("code")
    return observation


def summarize_call(query: str, result: dict[str, Any]) -> dict[str, Any]:
    """Verdichtet ein tools/call-Ergebnis auf pruefbare Felder, ohne Rohtext zu speichern."""
    payload = result.get("result", {})
    text = json.dumps(payload.get("structuredContent", payload.get("content", [])), ensure_ascii=False)
    return {
        "tool": "catalog_lookup",
        "query": query,
        "is_error": bool(payload.get("isError", "error" in result)),
        "item_ids": sorted(set(re.findall(r"\b[A-Z0-9]{2,5}-\d{3}\b", text))),
    }


def probe_streamable_http(
    endpoint: str, token: str, allow: frozenset[str], call_query: str | None = None
) -> ProtocolObservation:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(headers=headers, timeout=20) as client:
        modern = probe_modern_era(client, endpoint)
        initialize, session_id = _post(
            client,
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LEGACY_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "chapter-22-probe", "version": "1.0.0"},
                },
            },
        )
        version = initialize["result"]["protocolVersion"]
        tools, _ = _post(
            client,
            endpoint,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            protocol_version=version,
            session_id=session_id,
        )

        call_result = None
        if call_query is not None and "catalog_lookup" in allow:
            call_result, _ = _post(
                client,
                endpoint,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "catalog_lookup", "arguments": {"query": call_query}}},
                protocol_version=version,
                session_id=session_id,
            )

    discovered = tools["result"]["tools"]
    selected = ToolPolicy(allow).select(discovered)
    filtered_tools = {**tools, "result": {**tools["result"], "tools": selected}}
    observation = ProtocolObservation.from_initialize_and_tools(
        endpoint=endpoint,
        transport="streamable-http",
        initialize=initialize,
        tools_result=filtered_tools,
    )
    observation = observation.with_modern_probe(modern)
    if call_result is not None:
        observation = observation.with_call(summarize_call(call_query, call_result))
    return observation


async def probe_sse(endpoint: str, token: str, allow: frozenset[str]) -> ProtocolObservation:
    headers = {"Authorization": f"Bearer {token}"}
    async with sse_client(endpoint, headers=headers) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
    discovered = [tool.model_dump(by_alias=True, mode="json") for tool in listed.tools]
    selected = ToolPolicy(allow).select(discovered)
    return ProtocolObservation(
        endpoint=endpoint,
        transport="sse",
        protocol_version=initialized.protocol_version,
        server_name=initialized.server_info.name,
        tools=tuple(sorted(str(tool["name"]) for tool in selected)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Messe n8n/MCP-Vertrag und Tool-Allowlist.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--transport", choices=("streamable-http", "sse"), default="streamable-http")
    parser.add_argument("--allow", action="append", default=["catalog_lookup"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--call-query", help="optional: catalog_lookup mit dieser Suche aufrufen")
    args = parser.parse_args()
    if args.transport == "sse":
        observation = anyio.run(probe_sse, args.url, args.token, frozenset(args.allow))
    else:
        observation = probe_streamable_http(
            args.url, args.token, frozenset(args.allow), call_query=args.call_query
        )
    payload = {
        "endpoint": observation.endpoint,
        "transport": observation.transport,
        # Rückgabe der initialize-Antwort auf das Legacy-Angebot 2025-11-25:
        "protocol_version": observation.protocol_version,
        "server_name": observation.server_name,
        "tools": list(observation.tools),
    }
    if observation.modern_probe is not None:
        payload["modern_probe"] = observation.modern_probe
        payload["era"] = observation.era
    if observation.call is not None:
        payload["call"] = observation.call
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
