"""Lokale Wire-Simulation des URL-Modus; keine URL wird aufgerufen."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse


DEMO_URL = "https://consent.example.invalid/continue/POL-101"


def input_required_url(request_id: str = "call-1") -> dict[str, Any]:
    """Bilde eine moderne MRTR-Antwort für einen externen, fiktiven Schritt."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "resultType": "input_required",
            "inputRequests": {
                "external_step": {
                    "method": "elicitation/create",
                    "params": {
                        "mode": "url",
                        "message": "Optionalen externen Prüfschritt öffnen?",
                        "url": DEMO_URL,
                    },
                }
            },
            "requestState": "demo-state-v1",
        },
    }


def resume_url(
    first: dict[str, Any], action: Literal["accept", "decline", "cancel"], request_id: str = "call-2"
) -> dict[str, Any]:
    """Erzeuge den Retry, ohne URL oder Ergebnis des externen Schritts vorzutäuschen."""
    result = first["result"]
    request = result["inputRequests"]["external_step"]
    url = request["params"]["url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "consent.example.invalid":
        raise ValueError("Nicht freigegebene Demo-Domain")
    if request["params"]["mode"] != "url":
        raise ValueError("URL-Modus erwartet")
    if request_id == first["id"]:
        raise ValueError("Der Retry benötigt eine neue JSON-RPC-ID")
    if action not in ("accept", "decline", "cancel"):
        raise ValueError("Ungültige Benutzeraktion")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "external_check",
            "arguments": {"policy_id": "POL-101"},
            "inputResponses": {"external_step": {"action": action}},
            "requestState": result["requestState"],
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {
                    "elicitation": {"url": {}}
                },
            },
        },
    }
