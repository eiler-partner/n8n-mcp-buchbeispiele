from __future__ import annotations

from collections.abc import Iterable

from .approval import verify_approval
from .audit import redact
from .contracts import manifest_digest, proposal_digest
from .models import Approval, Document, PolicyDecision, RiskClass, ToolContract, ToolProposal


class ContractViolation(ValueError):
    pass


class BoundaryPolicy:
    def __init__(
        self,
        contracts: Iterable[ToolContract],
        *,
        expected_manifest_digest: str,
        signing_key: bytes,
    ) -> None:
        contract_list = tuple(contracts)
        self.contracts = {contract.name: contract for contract in contract_list}
        self.expected_manifest_digest = expected_manifest_digest
        self.current_manifest_digest = manifest_digest(contract_list)
        self.signing_key = signing_key
        # Verbrauchte Freigaben: Eine Signatur erlaubt genau eine Ausführung.
        # In Produktion liegt dieser Zustand in einer Datenbank mit Unique-Constraint.
        self._consumed_approvals: set[str] = set()

    def evaluate(
        self,
        proposal: ToolProposal,
        document: Document,
        *,
        approval: Approval | None = None,
        now: int | None = None,
    ) -> PolicyDecision:
        reasons: list[str] = []
        contract = self.contracts.get(proposal.tool)
        digest = proposal_digest(proposal.tool, proposal.tenant_id, proposal.arguments)

        if self.current_manifest_digest != self.expected_manifest_digest:
            reasons.append("MANIFEST_CHANGED")
        if contract is None:
            reasons.append("TOOL_NOT_ALLOWLISTED")
        if proposal.tenant_id != document.tenant_id:
            reasons.append("TENANT_MISMATCH")

        requires_approval = bool(contract and contract.risk is not RiskClass.READ)
        if contract is not None:
            payload = str(proposal.arguments.get("payload", ""))
            destination = str(proposal.arguments.get("destination", ""))
            if len(payload) > contract.max_payload_chars:
                reasons.append("PAYLOAD_TOO_LARGE")
            if contract.risk is RiskClass.EXTERNAL:
                if destination not in contract.allowed_destinations:
                    reasons.append("DESTINATION_NOT_ALLOWED")
                if not document.trusted:
                    reasons.append("UNTRUSTED_SOURCE_TO_EXTERNAL_SINK")
            if requires_approval and (
                approval is None
                or not verify_approval(
                    approval,
                    proposal,
                    signing_key=self.signing_key,
                    now=now,
                )
            ):
                reasons.append("APPROVAL_MISSING_OR_STALE")
            elif requires_approval and approval is not None and approval.signature in self._consumed_approvals:
                reasons.append("APPROVAL_ALREADY_USED")

        if not reasons and requires_approval and approval is not None:
            self._consumed_approvals.add(approval.signature)

        event = redact(
            {
                "document_id": document.document_id,
                "document_source": document.source,
                "document_trusted": document.trusted,
                "tenant_id": proposal.tenant_id,
                "tool": proposal.tool,
                "arguments": proposal.arguments,
                "manifest_digest": self.current_manifest_digest,
                "proposal_digest": digest,
                "decision": "allow" if not reasons else "block",
                "reason_codes": reasons,
                "approver": approval.approver if approval else None,
            }
        )
        return PolicyDecision(
            allowed=not reasons,
            reason_codes=reasons,
            proposal_digest=digest,
            requires_approval=requires_approval,
            audit_event=event,
        )
