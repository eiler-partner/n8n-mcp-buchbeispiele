from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


class ContractViolation(ValueError):
    """Ein entdeckter Serverkatalog verletzt die lokale Freigabe."""


@dataclass(frozen=True)
class ToolPolicy:
    """Clientseitige Allowlist; Servermetadaten erweitern sie nie automatisch."""

    allowed: frozenset[str]

    def select(self, discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_name = {str(tool.get("name")): tool for tool in discovered}
        missing = self.allowed - by_name.keys()
        if missing:
            raise ContractViolation(
                "Freigegebene Tools fehlen am Server: " + ", ".join(sorted(missing))
            )
        return [by_name[name] for name in sorted(self.allowed)]

    def require_call(self, name: str) -> None:
        if name not in self.allowed:
            raise ContractViolation(f"Tool ist nicht freigegeben: {name}")


@dataclass(frozen=True)
class ProtocolObservation:
    endpoint: str
    transport: str
    protocol_version: str
    server_name: str
    tools: tuple[str, ...]
    modern_probe: dict[str, Any] | None = None
    call: dict[str, Any] | None = None

    @property
    def era(self) -> str:
        """legacy, modern oder dual - gemessen, nicht aus dem Image-Tag abgeleitet."""
        modern = bool(self.modern_probe and self.modern_probe.get("era") == "modern")
        legacy = bool(self.protocol_version) and not self.protocol_version.startswith("2026")
        if modern and legacy:
            return "dual"
        return "modern" if modern else "legacy"

    def with_modern_probe(self, probe: dict[str, Any]) -> "ProtocolObservation":
        return replace(self, modern_probe=dict(probe))

    def with_call(self, call: dict[str, Any]) -> "ProtocolObservation":
        return replace(self, call=dict(call))

    @classmethod
    def from_initialize_and_tools(
        cls,
        *,
        endpoint: str,
        transport: str,
        initialize: dict[str, Any],
        tools_result: dict[str, Any],
    ) -> "ProtocolObservation":
        result = initialize.get("result")
        if not isinstance(result, dict):
            raise ContractViolation("Initialize-Antwort enthält kein result-Objekt")
        protocol = result.get("protocolVersion")
        server_info = result.get("serverInfo")
        if not isinstance(protocol, str) or not protocol:
            raise ContractViolation("Initialize-Antwort enthält keine Protokollversion")
        if not isinstance(server_info, dict) or not isinstance(server_info.get("name"), str):
            raise ContractViolation("Initialize-Antwort enthält keine Serveridentität")

        tools_payload = tools_result.get("result")
        if not isinstance(tools_payload, dict) or not isinstance(tools_payload.get("tools"), list):
            raise ContractViolation("tools/list-Antwort enthält keinen Toolkatalog")
        names = tuple(sorted(str(tool["name"]) for tool in tools_payload["tools"]))
        return cls(endpoint, transport, protocol, server_info["name"], names)
