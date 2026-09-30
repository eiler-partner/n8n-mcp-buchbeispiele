from __future__ import annotations

import hashlib
import hmac
import time

from .contracts import proposal_digest
from .models import Approval, ToolProposal


def issue_approval(
    proposal: ToolProposal,
    *,
    approver: str,
    signing_key: bytes,
    now: int | None = None,
    ttl_seconds: int = 300,
) -> Approval:
    issued_at = int(time.time()) if now is None else now
    digest = proposal_digest(proposal.tool, proposal.tenant_id, proposal.arguments)
    expires_at = issued_at + ttl_seconds
    message = f"{digest}:{approver}:{expires_at}".encode()
    signature = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    return Approval(
        proposal_digest=digest,
        approver=approver,
        expires_at=expires_at,
        signature=signature,
    )


def verify_approval(
    approval: Approval,
    proposal: ToolProposal,
    *,
    signing_key: bytes,
    now: int | None = None,
) -> bool:
    checked_at = int(time.time()) if now is None else now
    digest = proposal_digest(proposal.tool, proposal.tenant_id, proposal.arguments)
    message = f"{digest}:{approval.approver}:{approval.expires_at}".encode()
    expected = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    return (
        approval.expires_at >= checked_at
        and approval.proposal_digest == digest
        and hmac.compare_digest(approval.signature, expected)
    )
