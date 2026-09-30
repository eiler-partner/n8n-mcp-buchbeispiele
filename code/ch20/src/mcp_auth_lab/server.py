from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl
import uvicorn

from .auth import AuthConfig, JsonlAuditSink, JwtTokenVerifier, Principal, principal_from_claims
from .policy import DocumentPolicy


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    issuer: str
    resource: str
    algorithm: str
    fixture_secret: str | None
    jwks_url: str | None
    audit_path: Path

    @classmethod
    def from_environment(cls) -> "ServerConfig":
        host = os.getenv("MCP_AUTH_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_AUTH_PORT", "8019"))
        resource = os.getenv("MCP_AUTH_RESOURCE", f"http://127.0.0.1:{port}/mcp")
        algorithm = os.getenv("MCP_JWT_ALGORITHM", "HS256")
        return cls(
            host=host,
            port=port,
            issuer=os.getenv("MCP_AUTH_ISSUER", "http://127.0.0.1:9019"),
            resource=resource,
            algorithm=algorithm,
            fixture_secret=os.getenv(
                "MCP_JWT_FIXTURE_SECRET",
                "chapter-20-local-fixture-only-32-bytes-minimum",
            ),
            jwks_url=os.getenv("MCP_JWKS_URL"),
            audit_path=Path(os.getenv("MCP_AUDIT_PATH", "/tmp/mcp-auth-audit.jsonl")),
        )


def create_server(config: ServerConfig) -> MCPServer:
    audit = JsonlAuditSink(config.audit_path)
    verifier = JwtTokenVerifier(
        AuthConfig(
            issuer=config.issuer,
            resource=config.resource,
            algorithm=config.algorithm,
            fixture_secret=config.fixture_secret,
            jwks_url=config.jwks_url,
        ),
        audit,
    )
    policy = DocumentPolicy(audit)
    server = MCPServer(
        "Tenant Document Reader",
        instructions=(
            "Read-only document access. Identity and tenant always come from the validated token; "
            "tool arguments never select a tenant."
        ),
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(config.issuer),
            resource_server_url=AnyHttpUrl(config.resource),
            required_scopes=["documents:read"],
            validate_token_resource=True,
        ),
    )

    @server.tool(
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    )
    def list_documents() -> dict[str, object]:
        """List the documents visible to the authenticated tenant."""
        return policy.list_documents(_current_principal())

    @server.tool(
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
    )
    def read_document(document_id: str) -> dict[str, object]:
        """Read metadata for one document without revealing cross-tenant existence."""
        return policy.read_document(_current_principal(), document_id)

    return server


def _current_principal() -> Principal:
    token = get_access_token()
    if token is None or token.claims is None:
        raise ToolError("Zugriff verweigert: Es fehlt eine geprüfte Identität.")
    return principal_from_claims(token.claims)


class ScopeChallengeMiddleware:
    """Add the normative scope parameter to SDK-generated 403 challenges."""

    def __init__(self, app: Any, required_scope: str) -> None:
        self.app = app
        self.required_scope = required_scope

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        async def send_with_scope(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and message["status"] == 403:
                headers = list(message.get("headers", []))
                for index, (name, value) in enumerate(headers):
                    if name.lower() != b"www-authenticate":
                        continue
                    text = value.decode("latin-1")
                    if 'error="insufficient_scope"' in text and " scope=" not in text:
                        marker = ", resource_metadata="
                        scope_parameter = f', scope="{self.required_scope}"'
                        text = text.replace(marker, scope_parameter + marker, 1)
                        headers[index] = (name, text.encode("latin-1"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_scope)


def main() -> None:
    config = ServerConfig.from_environment()
    app = create_server(config).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host=config.host,
    )
    uvicorn.run(ScopeChallengeMiddleware(app, "documents:read"), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
