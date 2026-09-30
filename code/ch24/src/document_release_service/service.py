from __future__ import annotations

import re
import uuid

from .approval import proposal_digest, sign_request, verify_request
from .audit import audit
from .models import (
    ApprovalDecision,
    DocumentInput,
    IngestionResult,
    PublicationProposal,
    PublicationRequest,
    PublishResult,
    RequestStatus,
)
from .normalization import normalize_document
from .repository import ConflictError, Repository


URL = re.compile(r"https?://", re.I)
ATTACK_MARKERS = ("ignore previous", "exfiltrate", "send secret", "export secret")


class PolicyError(ValueError):
    pass


class StateError(ValueError):
    pass


class DocumentReleaseService:
    def __init__(
        self,
        repository: Repository,
        *,
        signing_key: bytes,
        destination: str = "local://published-reviews",
    ) -> None:
        self.repository = repository
        self.signing_key = signing_key
        self.destination = destination

    def ingest(
        self, value: DocumentInput, *, tenant_id: str, correlation_id: str
    ) -> IngestionResult:
        document = normalize_document(
            value, tenant_id=tenant_id, correlation_id=correlation_id
        )
        created = self.repository.put_document(document)
        audit(
            "document.ingested",
            tenant_id=tenant_id,
            document_id=document.document_id,
            correlation_id=correlation_id,
            content_hash=document.content_hash,
            created=created,
        )
        return IngestionResult(
            document_id=document.document_id,
            content_hash=document.content_hash,
            correlation_id=correlation_id,
            created=created,
        )

    def request_publication(
        self,
        proposal: PublicationProposal,
        *,
        tenant_id: str,
        correlation_id: str,
    ) -> PublicationRequest:
        document = self.repository.get_document(tenant_id, proposal.document_id)
        if document is None:
            raise PolicyError("Dokument im Tenant nicht vorhanden")
        reasons: list[str] = []
        if document.content_hash != proposal.content_hash:
            reasons.append("CONTENT_HASH_MISMATCH")
        if proposal.destination != self.destination:
            reasons.append("DESTINATION_NOT_ALLOWED")
        if not document.trusted:
            reasons.append("UNTRUSTED_DOCUMENT")
        folded = f"{document.text}\n{proposal.summary}".casefold()
        if URL.search(proposal.summary):
            reasons.append("URL_IN_SUMMARY")
        if any(marker in folded for marker in ATTACK_MARKERS):
            reasons.append("PROMPT_INJECTION_MARKER")
        if reasons:
            audit(
                "publication.blocked",
                tenant_id=tenant_id,
                document_id=proposal.document_id,
                correlation_id=correlation_id,
                reasons=reasons,
            )
            raise PolicyError(",".join(reasons))

        request = PublicationRequest(
            request_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            document_id=proposal.document_id,
            content_hash=proposal.content_hash,
            summary=proposal.summary,
            destination=proposal.destination,
            proposal_digest=proposal_digest(tenant_id, proposal),
            correlation_id=correlation_id,
        )
        self.repository.put_request(request)
        audit(
            "publication.pending",
            request_id=request.request_id,
            tenant_id=tenant_id,
            document_id=proposal.document_id,
            proposal_digest=request.proposal_digest,
            correlation_id=correlation_id,
        )
        return request

    def decide(
        self,
        request_id: str,
        decision: ApprovalDecision,
        *,
        now: int | None = None,
    ) -> PublicationRequest:
        request = self.repository.get_request(request_id)
        if request is None:
            raise StateError("Freigabeanforderung nicht vorhanden")
        if request.status is not RequestStatus.PENDING:
            raise StateError("Freigabeanforderung ist nicht mehr offen")
        if not decision.approve:
            request.status = RequestStatus.DENIED
            request.approver = decision.reviewer
        else:
            expires_at, signature = sign_request(
                request,
                reviewer=decision.reviewer,
                signing_key=self.signing_key,
                now=now,
            )
            request.status = RequestStatus.APPROVED
            request.approver = decision.reviewer
            request.expires_at = expires_at
            request.signature = signature
        self.repository.save_request(request)
        audit(
            "publication.decision",
            request_id=request_id,
            status=request.status,
            reviewer=decision.reviewer,
            signature=request.signature,
            correlation_id=request.correlation_id,
        )
        return request

    def execute(self, request_id: str, *, now: int | None = None) -> PublishResult:
        request = self.repository.get_request(request_id)
        if request is None:
            raise StateError("Freigabeanforderung nicht vorhanden")
        if request.status is not RequestStatus.APPROVED:
            raise StateError("Freigabeanforderung ist nicht genehmigt")
        document = self.repository.get_document(request.tenant_id, request.document_id)
        if document is None or document.content_hash != request.content_hash:
            raise StateError("Dokumentvertrag hat sich geändert")
        proposal = PublicationProposal(
            document_id=request.document_id,
            content_hash=request.content_hash,
            summary=request.summary,
            destination=request.destination,
        )
        if proposal_digest(request.tenant_id, proposal) != request.proposal_digest:
            raise StateError("Publikationsvorschlag wurde verändert")
        if not verify_request(request, signing_key=self.signing_key, now=now):
            raise StateError("Freigabe ist ungültig oder abgelaufen")
        result = PublishResult(
            request_id=request.request_id,
            document_id=request.document_id,
            destination=request.destination,
            correlation_id=request.correlation_id,
        )
        if not self.repository.put_outbox(result):
            raise ConflictError("Publikation wurde bereits ausgeführt")
        request.status = RequestStatus.PUBLISHED
        self.repository.save_request(request)
        audit(
            "publication.executed",
            request_id=request_id,
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            correlation_id=request.correlation_id,
        )
        return result
