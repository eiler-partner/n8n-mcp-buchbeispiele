from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import build_adapter, get_settings
from .domain import ExtractionEnvelope, ExtractionRequest
from .errors import ProviderError
from .service import ExtractionService

app = FastAPI(title="Chapter 12 Model Adapter Lab", version="0.1.0")


def _service() -> ExtractionService:
    return ExtractionService(primary=build_adapter(get_settings()))


@app.exception_handler(ProviderError)
def provider_error(_: Request, exc: ProviderError) -> JSONResponse:
    """Providerfehler als 502 mit Fehlerklasse statt als unklarer 500."""
    return JSONResponse(
        status_code=502,
        content={"error": {"provider": exc.provider, "kind": exc.kind.value,
                           "retryable": exc.retryable}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "provider": settings.model_provider}


@app.post("/extract", response_model=ExtractionEnvelope)
def extract(request: ExtractionRequest) -> ExtractionEnvelope:
    return _service().extract(request)


def main() -> None:
    uvicorn.run("model_adapter_lab.api:app", host="0.0.0.0", port=8020)
