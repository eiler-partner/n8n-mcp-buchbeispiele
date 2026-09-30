from __future__ import annotations

import hashlib
import hmac
import json
import time

from .models import PublicationProposal, PublicationRequest


def proposal_digest(tenant_id: str, proposal: PublicationProposal) -> str:
    payload = {
        "content_hash": proposal.content_hash,
        "destination": proposal.destination,
        "document_id": proposal.document_id,
        "summary": proposal.summary,
        "tenant_id": tenant_id,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def sign_request(
    request: PublicationRequest,
    *,
    reviewer: str,
    signing_key: bytes,
    now: int | None = None,
    ttl_seconds: int = 300,
) -> tuple[int, str]:
    expires_at = (int(time.time()) if now is None else now) + ttl_seconds
    message = f"{request.request_id}:{request.proposal_digest}:{reviewer}:{expires_at}".encode()
    return expires_at, hmac.new(signing_key, message, hashlib.sha256).hexdigest()


def verify_request(
    request: PublicationRequest, *, signing_key: bytes, now: int | None = None
) -> bool:
    if not request.signature or not request.approver or request.expires_at is None:
        return False
    checked_at = int(time.time()) if now is None else now
    message = (
        f"{request.request_id}:{request.proposal_digest}:"
        f"{request.approver}:{request.expires_at}"
    ).encode()
    expected = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    return request.expires_at >= checked_at and hmac.compare_digest(
        request.signature, expected
    )
