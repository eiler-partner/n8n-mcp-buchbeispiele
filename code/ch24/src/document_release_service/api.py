from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .config import Settings
from .models import ApprovalDecision, DocumentInput, PublicationProposal
from .repository import ConflictError, PostgresRepository, Repository
from .service import DocumentReleaseService, PolicyError, StateError
from .telemetry import configure_logging, configure_tracing


def create_app(
    repository: Repository | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    repository = repository or PostgresRepository(settings.database_url)
    service = DocumentReleaseService(
        repository, signing_key=settings.signing_key, destination=settings.publish_destination
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(title="Chapter 24 Document Release Service", lifespan=lifespan)
    app.state.service = service
    app.state.repository = repository
    app.state.settings = settings

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/documents")
    def ingest(
        body: DocumentInput,
        request: Request,
        x_tenant_id: str = Header(alias="X-Tenant-ID"),
    ):
        try:
            return service.ingest(
                body,
                tenant_id=x_tenant_id,
                correlation_id=request.state.correlation_id,
            )
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/publication-requests")
    def publication_request(
        body: PublicationProposal,
        request: Request,
        x_tenant_id: str = Header(alias="X-Tenant-ID"),
    ):
        try:
            return service.request_publication(
                body,
                tenant_id=x_tenant_id,
                correlation_id=request.state.correlation_id,
            )
        except PolicyError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/publication-requests/{request_id}/decision")
    def decide(
        request_id: str,
        body: ApprovalDecision,
        x_approval_key: str = Header(alias="X-Approval-Key"),
    ):
        if not secrets.compare_digest(x_approval_key, settings.approval_key):
            raise HTTPException(status_code=401, detail="Ungültiger Freigabekanal")
        try:
            return service.decide(request_id, body)
        except StateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/publication-requests/{request_id}/execute")
    def execute(
        request_id: str,
        x_executor_key: str = Header(alias="X-Executor-Key"),
    ):
        if not secrets.compare_digest(x_executor_key, settings.executor_key):
            raise HTTPException(status_code=401, detail="Ungültiger Executor")
        try:
            return service.execute(request_id)
        except (StateError, ConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/outbox/{request_id}")
    def outbox(request_id: str):
        value = repository.get_outbox(request_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Nicht publiziert")
        return value

    return app


def main() -> None:
    configure_logging()
    configure_tracing("ch24-api")
    app = create_app()
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        FastAPIInstrumentor.instrument_app(app)
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("CH24_API_PORT", "8024")))  # nosec B104


if __name__ == "__main__":
    main()
