from __future__ import annotations

from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import Client
from mcp.client import CacheConfig
from mcp.server import MCPServer
from mcp.types import CallToolResult, Resource, Tool


class ClientConfigurationError(ValueError):
    """Eine Server- oder Toolkonfiguration ist nicht eindeutig oder nicht sicher."""


@dataclass(frozen=True)
class ServerBinding:
    alias: str
    target: MCPServer | str | Any
    allowed_tools: frozenset[str]
    cache_partition: str = "book-lab"

    def __post_init__(self) -> None:
        if not self.alias or "/" in self.alias:
            raise ClientConfigurationError("Server-Aliase müssen kurz sein und dürfen kein '/' enthalten.")
        if not self.allowed_tools:
            raise ClientConfigurationError("Jeder Server benötigt eine explizite Tool-Allowlist.")


@dataclass
class ClientPool:
    """Verwaltet mehrere MCP-Clients mit qualifizierten Toolnamen."""

    bindings: tuple[ServerBinding, ...]
    _stack: AsyncExitStack = field(init=False, default_factory=AsyncExitStack)
    _clients: dict[str, Client] = field(init=False, default_factory=dict)
    _tools: dict[str, Tool] = field(init=False, default_factory=dict)

    async def __aenter__(self) -> ClientPool:
        aliases = [binding.alias for binding in self.bindings]
        if len(aliases) != len(set(aliases)):
            raise ClientConfigurationError("Server-Aliase müssen eindeutig sein.")

        try:
            for binding in self.bindings:
                client = Client(
                    binding.target,
                    cache=CacheConfig(partition=binding.cache_partition),
                )
                self._clients[binding.alias] = await self._stack.enter_async_context(client)
            await self.refresh_catalog()
            return self
        except BaseException:
            await self._stack.aclose()
            raise

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    @property
    def tools(self) -> Mapping[str, Tool]:
        return dict(self._tools)

    async def refresh_catalog(self) -> None:
        discovered: dict[str, Tool] = {}
        for binding in self.bindings:
            client = self._clients[binding.alias]
            result = await client.list_tools(cache_mode="refresh")
            available = {tool.name: tool for tool in result.tools}
            missing = binding.allowed_tools - available.keys()
            if missing:
                names = ", ".join(sorted(missing))
                raise ClientConfigurationError(
                    f"Allowlist für {binding.alias} verweist auf unbekannte Tools: {names}"
                )
            for name in sorted(binding.allowed_tools):
                discovered[f"{binding.alias}/{name}"] = available[name]
        self._tools = discovered

    async def list_resources(self, alias: str) -> list[Resource]:
        client = self._client(alias)
        resources: list[Resource] = []
        cursor: str | None = None
        while True:
            result = await client.list_resources(cursor=cursor)
            resources.extend(result.resources)
            cursor = result.next_cursor
            if cursor is None:
                return resources

    async def call_tool(
        self,
        qualified_name: str,
        arguments: dict[str, Any],
        *,
        progress_callback: Any | None = None,
    ) -> CallToolResult:
        if qualified_name not in self._tools:
            raise ClientConfigurationError(
                f"Tool ist nicht freigegeben oder unbekannt: {qualified_name}"
            )
        alias, tool_name = qualified_name.split("/", maxsplit=1)
        return await self._client(alias).call_tool(
            tool_name,
            arguments,
            progress_callback=progress_callback,
        )

    def _client(self, alias: str) -> Client:
        try:
            return self._clients[alias]
        except KeyError as exc:
            raise ClientConfigurationError(f"Unbekannter Server-Alias: {alias}") from exc
