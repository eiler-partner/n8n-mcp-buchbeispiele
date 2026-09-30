from __future__ import annotations

import json
import os
import secrets
import time
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from pydantic import AnyHttpUrl, Field
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings
from .models import DocumentHit
from .repository import PostgresRepository, Repository
from .telemetry import configure_logging, configure_tracing


class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected: str, resource: str, tenant_id: str) -> None:
        self.expected = expected
        self.resource = resource
        self.tenant_id = tenant_id

    async def verify_token(self, token: str) -> AccessToken | None:
        if not secrets.compare_digest(token, self.expected):
            return None
        return AccessToken(
            token=token,
            client_id="n8n-ch24-lab",
            scopes=["documents:read"],
            expires_at=int(time.time()) + 3600,
            resource=self.resource,
            subject=f"reader:{self.tenant_id}",
        )


def create_server(
    repository: Repository,
    *,
    tenant_id: str,
    resource: str = "http://127.0.0.1:8025/mcp",
    token: str = "chapter-24-local-mcp-token-change-me",
    require_auth: bool = True,
) -> MCPServer:
    kwargs = {}
    if require_auth:
        kwargs = {
            "token_verifier": StaticTokenVerifier(token, resource, tenant_id),
            "auth": AuthSettings(
                issuer_url=AnyHttpUrl("http://127.0.0.1:8025"),
                resource_server_url=AnyHttpUrl(resource),
                required_scopes=["documents:read"],
                validate_token_resource=True,
            ),
        }
    server = MCPServer(
        "Chapter 24 Document Catalog",
        version="1.0.0",
        instructions="Read-only synthetic document catalog. No publication capability exists.",
        **kwargs,
    )

    @server.tool(
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    )
    def search_documents(
        query: Annotated[str, Field(min_length=2, max_length=120)],
        limit: Annotated[int, Field(ge=1, le=5)] = 5,
    ) -> list[DocumentHit]:
        """Search synthetic documents belonging to the authenticated lab tenant."""
        hits = repository.search_documents(tenant_id, query, limit)
        if not hits:
            raise ToolError("Keine passenden Dokumente.")
        return hits

    @server.tool(
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    )
    def read_document(document_id: str) -> dict[str, str | bool]:
        """Read one normalized synthetic document by identifier."""
        value = repository.get_document(tenant_id, document_id)
        if value is None:
            raise ToolError("Dokument nicht vorhanden.")
        return {
            "document_id": value.document_id,
            "title": value.title,
            "source": value.source,
            "trusted": value.trusted,
            "content_hash": value.content_hash,
            "text": value.text,
        }

    @server.resource("document://{document_id}", mime_type="application/json")
    def document_resource(document_id: str) -> str:
        """Return a normalized document as a resource."""
        value = repository.get_document(tenant_id, document_id)
        if value is None:
            raise ResourceNotFoundError(f"document://{document_id}")
        return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)

    return server


def main() -> None:
    configure_logging()
    configure_tracing("ch24-mcp")
    settings = Settings.from_env()
    repository = PostgresRepository(settings.database_url)
    repository.initialize()
    resource = os.getenv("CH24_MCP_RESOURCE", "http://127.0.0.1:8025/mcp")
    server = create_server(
        repository,
        tenant_id=settings.tenant_id,
        resource=resource,
        token=settings.mcp_token,
    )
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        host="0.0.0.0",
    )

    async def record_protocol_version(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/mcp":
            try:
                payload = json.loads((await request.body()).decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and payload.get("method") == "initialize":
                print(
                    json.dumps(
                        {
                            "event": "mcp.initialize",
                            "protocol_version": payload.get("params", {}).get(
                                "protocolVersion"
                            ),
                            "client": payload.get("params", {}).get("clientInfo"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )

        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=record_protocol_version)

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104: published only on loopback by Compose.
        port=int(os.getenv("CH24_MCP_PORT", "8025")),
    )


if __name__ == "__main__":
    main()
