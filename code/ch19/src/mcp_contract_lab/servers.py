from __future__ import annotations

import anyio
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import InputRequiredResult
from pydantic import BaseModel, Field


class PolicyHit(BaseModel):
    policy_id: str
    title: str
    excerpt: str


class RiskAssessment(BaseModel):
    document_id: str
    risk: Literal["low", "medium", "high"]
    reasons: list[str]


POLICIES = (
    PolicyHit(
        policy_id="POL-101",
        title="Reiserichtlinie",
        excerpt="Belege sind ab 25 Euro erforderlich.",
    ),
    PolicyHit(
        policy_id="POL-102",
        title="Informationsschutz",
        excerpt="Vertrauliche Daten sind zu verschlüsseln.",
    ),
)


policy_server = MCPServer(
    "Policy Contract Lab",
    version="1.0.0",
    cache_hints={
        "tools/list": CacheHint(ttl_ms=30_000, scope="public"),
        "resources/list": CacheHint(ttl_ms=30_000, scope="public"),
        "resources/read": CacheHint(ttl_ms=5_000, scope="private"),
    },
)


@policy_server.tool()
def search_policies(
    query: Annotated[str, Field(min_length=2, max_length=200)],
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> list[PolicyHit]:
    """Suche ausschließlich in den freigegebenen Beispielrichtlinien."""
    normalized = query.casefold()
    hits = [
        policy
        for policy in POLICIES
        if normalized in f"{policy.title} {policy.excerpt}".casefold()
    ]
    if not hits:
        raise ToolError("Keine passende Richtlinie gefunden.")
    return hits[:limit]


@policy_server.tool()
async def check_documents(
    document_ids: Annotated[list[str], Field(min_length=1, max_length=10)],
    ctx: Context,
) -> dict[str, int]:
    """Prüfe eine kleine Dokumentliste und melde den Fortschritt."""
    total = len(document_ids)
    for index, document_id in enumerate(document_ids, start=1):
        await anyio.sleep(0)
        await ctx.report_progress(index, total=total, message=document_id)
    return {"checked": total}


@policy_server.resource("policy://catalog", mime_type="application/json")
def policy_catalog() -> str:
    """Liefere die IDs des freigegebenen Richtlinienkatalogs."""
    return '["POL-101", "POL-102"]'


risk_server = MCPServer("Risk Contract Lab", version="1.0.0")


@risk_server.tool()
def classify_risk(
    document_id: Annotated[str, Field(min_length=1, max_length=120)],
    findings: Annotated[list[str], Field(max_length=20)],
) -> RiskAssessment:
    """Klassifiziere ein synthetisches Dokument anhand seiner Befunde."""
    count = len(findings)
    risk: Literal["low", "medium", "high"]
    risk = "high" if count >= 3 else "medium" if count else "low"
    return RiskAssessment(document_id=document_id, risk=risk, reasons=findings)


fault_server = MCPServer("Fault Contract Lab", version="1.0.0")

mrtr_server = MCPServer("MRTR Contract Lab", version="1.0.0")


@mrtr_server.tool()
def confirm_modern_contract(ctx: Context) -> dict[str, bool] | InputRequiredResult:
    """Fordere genau eine MRTR-Runde an und bestätige danach den Vertrag."""
    if ctx.request_state is None:
        return InputRequiredResult(request_state="contract-confirmation-v1")
    return {"confirmed": ctx.request_state == "contract-confirmation-v1"}


@fault_server.tool()
async def delayed_echo(
    text: str,
    delay_seconds: Annotated[float, Field(ge=0, le=2)] = 0,
) -> dict[str, str]:
    """Antworte absichtlich verzögert, um Client-Timeouts zu testen."""
    await anyio.sleep(delay_seconds)
    return {"text": text}


@fault_server.tool()
def controlled_failure(kind: Literal["business", "unexpected"]) -> str:
    """Erzeuge einen erwarteten oder unerwarteten Handlerfehler."""
    if kind == "business":
        raise ToolError("Kontrollierter Fachfehler.")
    raise RuntimeError("Interner Testfehler, der nicht nach außen gelangen darf.")


def stdio_main() -> None:
    policy_server.run()


def http_main() -> None:
    policy_server.run(
        transport="streamable-http",
        host="0.0.0.0",  # nosec B104: absichtlich im Container erreichbar.
        port=8000,
    )


if __name__ == "__main__":
    stdio_main()
