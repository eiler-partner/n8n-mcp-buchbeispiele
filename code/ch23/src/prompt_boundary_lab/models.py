from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskClass(StrEnum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


class Document(BaseModel):
    document_id: str
    tenant_id: str
    source: str
    trusted: bool = False
    text: str = Field(max_length=20_000)


class ToolContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    risk: RiskClass
    allowed_destinations: tuple[str, ...] = ()
    max_payload_chars: int = 2_000


class ToolProposal(BaseModel):
    tool: str
    tenant_id: str
    arguments: dict[str, Any]
    document_id: str


class Approval(BaseModel):
    proposal_digest: str
    approver: str
    expires_at: int
    signature: str


class PolicyDecision(BaseModel):
    allowed: bool
    reason_codes: list[str]
    proposal_digest: str
    requires_approval: bool
    audit_event: dict[str, Any]
