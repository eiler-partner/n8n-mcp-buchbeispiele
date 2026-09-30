from __future__ import annotations

from fastapi import FastAPI

from .config import Settings
from .domain import RunRequest
from .factory import build_controller


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    app = FastAPI(title="Controlled Research Agent", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "provider": resolved.model_provider}

    @app.post("/research")
    def research(request: RunRequest) -> dict[str, object]:
        controller = build_controller(resolved)
        effective = request.model_copy(
            update={"limits": request.limits if "limits" in request.model_fields_set else resolved.limits()}
        )
        return controller.run(effective).model_dump(mode="json")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("controlled_research_agent.api:app", host="0.0.0.0", port=8030)
