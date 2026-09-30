from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from pydantic import Field

from .domain import HashResult, Policy, PolicyRepository, SearchHit, sha256_text

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    policies: PolicyRepository


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    repository = PolicyRepository(
        [
            Policy("POL-101", "Reiserichtlinie", "Belege sind ab 25 Euro erforderlich."),
            Policy("POL-102", "Informationsschutz", "Vertrauliche Daten sind zu verschlüsseln."),
        ]
    )
    logger.info("Policy-Repository initialisiert")
    try:
        yield AppContext(policies=repository)
    finally:
        logger.info("Policy-Repository beendet")


mcp = MCPServer("Policy Lab", lifespan=app_lifespan, log_level="INFO")


@mcp.tool()
def hash_text(
    text: Annotated[str, Field(min_length=1, max_length=20_000, description="Zu hashender UTF-8-Text")],
) -> HashResult:
    """Berechne den SHA-256-Hash eines Textes."""
    return sha256_text(text)


@mcp.tool()
async def search_policies(
    query: Annotated[str, Field(min_length=2, max_length=200)],
    ctx: Context[AppContext],
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> list[SearchHit]:
    """Suche in freigegebenen Unternehmensrichtlinien."""
    hits = await ctx.request_context.lifespan_context.policies.search(query, limit)
    if not hits:
        raise ToolError("Keine passende Richtlinie gefunden. Formuliere die Suche konkreter.")
    return hits


@mcp.resource("policy://{policy_id}", mime_type="text/markdown")
def policy_resource(policy_id: str, ctx: Context) -> str:
    """Lade eine Richtlinie als zitierfähige Ressource."""
    policy = ctx.request_context.lifespan_context.policies.get(policy_id)
    if policy is None:
        raise ResourceNotFoundError(f"Unbekannte Richtlinie: {policy_id}")
    return f"# {policy.title}\n\nID: `{policy.policy_id}`\n\n{policy.text}"


@mcp.prompt(title="Richtlinie prüfen")
def review_policy(policy_id: str, question: str) -> str:
    """Erzeuge einen Prüfauftrag mit Quellen- und Unsicherheitsanforderung."""
    return (
        f"Prüfe die Frage anhand der Ressource policy://{policy_id}: {question}\n"
        "Nenne die Richtlinien-ID, trenne Befund und Interpretation und markiere Unsicherheiten."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
