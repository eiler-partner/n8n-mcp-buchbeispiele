from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,39}$")
    title: str = Field(min_length=3, max_length=160)
    source: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=10, max_length=20_000)
    trusted: bool = False


class NormalizedDocument(BaseModel):
    tenant_id: str
    document_id: str
    title: str
    source: str
    text: str
    trusted: bool
    content_hash: str
    correlation_id: str


class IngestionResult(BaseModel):
    document_id: str
    content_hash: str
    correlation_id: str
    created: bool


class DocumentHit(BaseModel):
    document_id: str
    title: str
    source: str
    trusted: bool
    content_hash: str


class PublicationProposal(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,39}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=20, max_length=1_200)
    destination: str = Field(min_length=3, max_length=120)


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PUBLISHED = "published"
    DENIED = "denied"


class PublicationRequest(BaseModel):
    request_id: str
    tenant_id: str
    document_id: str
    content_hash: str
    summary: str
    destination: str
    proposal_digest: str
    correlation_id: str
    status: RequestStatus = RequestStatus.PENDING
    approver: str | None = None
    expires_at: int | None = None
    signature: str | None = None


class ApprovalDecision(BaseModel):
    reviewer: str = Field(min_length=3, max_length=120)
    approve: bool = True


class PublishResult(BaseModel):
    request_id: str
    document_id: str
    destination: str
    correlation_id: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
