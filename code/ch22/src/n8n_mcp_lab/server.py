from __future__ import annotations

import os
import secrets
import time
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl, BaseModel, Field


class CatalogHit(BaseModel):
    item_id: str
    title: str
    status: str


CATALOG = (
    CatalogHit(item_id="MCP-001", title="MCP-Betriebshandbuch", status="approved"),
    CatalogHit(item_id="N8N-022", title="n8n-MCP-Integrationsmuster", status="approved"),
    CatalogHit(item_id="SEC-023", title="Prompt-Injection-Prüfplan", status="draft"),
)


class StaticTokenVerifier(TokenVerifier):
    """Kleiner Labor-Verifier; Produktion verwendet OAuth/OIDC und kurze Tokens."""

    def __init__(self, expected: str, resource: str) -> None:
        self.expected = expected
        self.resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        if not secrets.compare_digest(token, self.expected):
            return None
        return AccessToken(
            token=token,
            client_id="n8n-ch22-lab",
            scopes=["catalog:read"],
            expires_at=int(time.time()) + 3600,
            resource=self.resource,
            subject="n8n-client",
        )


def create_server(resource: str, token: str) -> MCPServer:
    server = MCPServer(
        "Chapter 22 Catalog",
        version="1.0.0",
        instructions="Read-only synthetic catalog. Never infer write capabilities.",
        token_verifier=StaticTokenVerifier(token, resource),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl("http://127.0.0.1:8022"),
            resource_server_url=AnyHttpUrl(resource),
            required_scopes=["catalog:read"],
            validate_token_resource=True,
        ),
    )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
    def catalog_lookup(
        query: Annotated[str, Field(min_length=2, max_length=120)],
        limit: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> list[CatalogHit]:
        """Search the approved synthetic catalog by title or identifier."""
        needle = query.casefold()
        hits = [item for item in CATALOG if needle in f"{item.item_id} {item.title}".casefold()]
        if not hits:
            raise ToolError("Keine passenden Katalogeinträge.")
        return hits[:limit]

    @server.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def maintenance_reset(confirm: bool = False) -> dict[str, bool]:
        """Negative test fixture. n8n must exclude this maintenance tool."""
        raise ToolError("Dieses Testwerkzeug ist absichtlich nicht ausführbar.")

    return server


def _token() -> str:
    return os.getenv("CH22_MCP_TOKEN", "chapter-22-local-token-change-me")


def http_main() -> None:
    resource = os.getenv("CH22_MCP_HTTP_RESOURCE", "http://127.0.0.1:8022/mcp")
    create_server(resource, _token()).run(
        transport="streamable-http",
        host="0.0.0.0",  # nosec B104: Container-Port wird nur an Loopback veröffentlicht.
        port=int(os.getenv("CH22_MCP_HTTP_PORT", "8022")),
        streamable_http_path="/mcp",
    )


def sse_main() -> None:
    resource = os.getenv("CH22_MCP_SSE_RESOURCE", "http://127.0.0.1:8023/sse")
    create_server(resource, _token()).run(
        transport="sse",
        host="0.0.0.0",  # nosec B104: Container-Port wird nur an Loopback veröffentlicht.
        port=int(os.getenv("CH22_MCP_SSE_PORT", "8023")),
        sse_path="/sse",
        message_path="/messages/",
    )


if __name__ == "__main__":
    http_main()
