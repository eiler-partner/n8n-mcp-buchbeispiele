from __future__ import annotations

import os

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from .contracts import manifest_digest
from .models import Document, RiskClass, ToolContract
from .pipeline import scripted_planner
from .policy import BoundaryPolicy


CANARY = os.getenv("CH23_CANARY_SECRET", "CANARY-CH23-NOT-A-REAL-SECRET")
SIGNING_KEY = os.getenv("CH23_APPROVAL_KEY", "chapter-23-local-signing-key").encode()
CONTRACTS = (
    ToolContract(name="search_catalog", description="Read-only search", risk=RiskClass.READ),
    ToolContract(
        name="export_report",
        description="Send an approved report to the local capture fixture",
        risk=RiskClass.EXTERNAL,
        allowed_destinations=("http://capture-sink:8024/capture",),
        max_payload_chars=500,
    ),
)
POLICY = BoundaryPolicy(
    CONTRACTS,
    expected_manifest_digest=manifest_digest(CONTRACTS),
    signing_key=SIGNING_KEY,
)


class EvaluationRequest(BaseModel):
    mode: str = "hardened"
    document: Document


app = FastAPI(title="Chapter 23 Prompt Boundary", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate")
async def evaluate(request: EvaluationRequest) -> dict[str, object]:
    proposal = scripted_planner(request.document, canary=CANARY)
    if request.mode == "vulnerable":
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.post(
                str(proposal.arguments["destination"]),
                json={"payload": proposal.arguments["payload"]},
            )
        return {"mode": request.mode, "executed": True, "sink_status": response.status_code}
    decision = POLICY.evaluate(proposal, request.document)
    return {"mode": request.mode, "executed": decision.allowed, "decision": decision.model_dump()}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8023)
