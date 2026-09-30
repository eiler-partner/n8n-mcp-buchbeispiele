from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .jobs import DemoReviewEngine, ReviewJob, ReviewJobManager, ReviewResult


@dataclass
class AppContext:
    jobs: ReviewJobManager
    engine: DemoReviewEngine


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    engine = DemoReviewEngine()
    jobs = ReviewJobManager(engine)
    try:
        yield AppContext(jobs=jobs, engine=engine)
    finally:
        await jobs.close()


mcp = MCPServer("Advanced Policy Lab", lifespan=app_lifespan)


def _jobs(ctx: Context[AppContext]) -> ReviewJobManager:
    return ctx.request_context.lifespan_context.jobs


@mcp.tool()
async def start_review(
    document_id: Annotated[str, Field(min_length=1, max_length=120)],
    checks: Annotated[list[str], Field(min_length=1, max_length=20)],
    ctx: Context[AppContext],
) -> ReviewJob:
    """Starte eine asynchrone Dokumentenprüfung und liefere einen Job-Handle."""
    return await _jobs(ctx).submit(document_id, checks)


@mcp.tool()
async def get_review(
    review_id: Annotated[str, Field(min_length=1, max_length=64)],
    ctx: Context[AppContext],
) -> ReviewJob:
    """Liefere Zustand und Ergebnis einer gestarteten Dokumentenprüfung."""
    try:
        return await _jobs(ctx).get(review_id)
    except KeyError as exc:
        raise ToolError("Unbekannte review_id.") from exc


@mcp.tool()
async def cancel_review(
    review_id: Annotated[str, Field(min_length=1, max_length=64)],
    ctx: Context[AppContext],
) -> ReviewJob:
    """Fordere den Abbruch einer laufenden Dokumentenprüfung an."""
    try:
        return await _jobs(ctx).cancel(review_id)
    except KeyError as exc:
        raise ToolError("Unbekannte review_id.") from exc


@mcp.tool()
async def review_now(
    document_id: Annotated[str, Field(min_length=1, max_length=120)],
    checks: Annotated[list[str], Field(min_length=1, max_length=20)],
    ctx: Context[AppContext],
) -> ReviewResult:
    """Prüfe ein kurzes Dokument im Aufruf und melde Fortschritt."""

    async def report(done: int, total: int, message: str) -> None:
        await ctx.report_progress(done, total=total, message=message)

    engine = ctx.request_context.lifespan_context.engine
    return await engine.review(document_id, checks, report)


def main() -> None:
    mcp.run()


def http_main() -> None:
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",  # nosec B104: Container-Port ist bewusst extern erreichbar.
        port=8000,
    )


if __name__ == "__main__":
    main()
