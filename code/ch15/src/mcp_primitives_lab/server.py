"""Kleiner MCP-Dienst: fachliche Trennung der vier Primitives."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    Elicit,
    ElicitationResult,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
    ToolAnnotations,
)
from pydantic import BaseModel, Field


POLICIES = {
    "POL-101": {
        "title": "Reiserichtlinie (synthetisch)",
        "text": "Reisebelege ab 25 Euro sind aufzubewahren.",
        "control": "CTRL-TRAVEL-01",
    },
    "POL-102": {
        "title": "Informationsschutz (synthetisch)",
        "text": "Vertrauliche Dokumente sind verschlüsselt abzulegen.",
        "control": "CTRL-INFO-02",
    },
}


class ReviewPeriod(BaseModel):
    period: Literal["2026-Q3", "2026-Q4"] = Field(description="Prüfzeitraum")


class Assessment(BaseModel):
    policy_id: str
    control_id: str
    period: str | None
    status: Literal["checked", "declined", "cancelled"]
    evidence_uri: str | None


async def ask_period(policy_id: str) -> Elicit[ReviewPeriod]:
    if policy_id not in POLICIES:
        raise ToolError("Unbekannte synthetische Richtlinien-ID")
    return Elicit("Für welchen Zeitraum soll die Richtlinie geprüft werden?", ReviewPeriod)


server = MCPServer("Compliance Primitives Lab", version="1.0.0")


@server.resource("policy://{policy_id}", mime_type="text/markdown")
def read_policy(policy_id: str) -> str:
    """Lies eine freigegebene synthetische Richtlinie anhand ihrer ID."""
    policy = POLICIES.get(policy_id)
    if policy is None:
        raise ResourceNotFoundError(f"Unbekannte Richtlinie: {policy_id}")
    return f"# {policy['title']}\n\n{policy['text']}\n"


@server.tool(
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
)
async def check_policy(
    policy_id: Annotated[str, Field(description="Freigegebene Richtlinien-ID")],
    period: Annotated[ElicitationResult[ReviewPeriod], Resolve(ask_period)],
) -> Assessment:
    """Prüfe eine synthetische Richtlinie lesend gegen ihren Kontrollpunkt."""
    policy = POLICIES[policy_id]
    match period:
        case AcceptedElicitation(data=ReviewPeriod(period=value)):
            return Assessment(
                policy_id=policy_id,
                control_id=policy["control"],
                period=value,
                status="checked",
                evidence_uri=f"policy://{policy_id}",
            )
        case DeclinedElicitation():
            status = "declined"
        case CancelledElicitation():
            status = "cancelled"
        case _:
            raise ToolError("Unbekanntes Ergebnis der Rückfrage")
    return Assessment(
        policy_id=policy_id,
        control_id=policy["control"],
        period=None,
        status=status,
        evidence_uri=None,
    )


@server.prompt(title="Synthetische Richtlinie prüfen")
def review_policy(policy_id: str) -> str:
    """Starte eine menschlich gewählte Prüfung mit explizitem Quellenbezug."""
    if policy_id not in POLICIES:
        raise ValueError("Unbekannte Richtlinien-ID")
    return (
        f"Prüfe policy://{policy_id}. Nenne Kontroll-ID und Belegstelle. "
        "Trenne Befund von Interpretation; triff keine automatische Rechtsentscheidung."
    )


@server.completion()
async def complete_policy_id(
    ref: PromptReference | ResourceTemplateReference,
    argument: CompletionArgument,
    context: CompletionContext | None,
) -> Completion | None:
    """Schlage nur freigegebene IDs für Prompt oder Resource-Template vor."""
    del context
    if argument.name != "policy_id":
        return None
    if isinstance(ref, PromptReference) and ref.name != "review_policy":
        return None
    if isinstance(ref, ResourceTemplateReference) and ref.uri != "policy://{policy_id}":
        return None
    return Completion(values=[key for key in POLICIES if key.startswith(argument.value)])


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
