from __future__ import annotations

from prompt_boundary_lab.approval import issue_approval
from prompt_boundary_lab.contracts import manifest_digest
from prompt_boundary_lab.models import Document, RiskClass, ToolContract, ToolProposal
from prompt_boundary_lab.policy import BoundaryPolicy


SIGNING_KEY = b"test-signing-key"
CONTRACTS = (
    ToolContract(name="search_catalog", description="read", risk=RiskClass.READ),
    ToolContract(
        name="export_report",
        description="external write",
        risk=RiskClass.EXTERNAL,
        allowed_destinations=("http://capture-sink:8024/capture",),
        max_payload_chars=80,
    ),
)


def policy(contracts: tuple[ToolContract, ...] = CONTRACTS) -> BoundaryPolicy:
    return BoundaryPolicy(
        contracts,
        expected_manifest_digest=manifest_digest(CONTRACTS),
        signing_key=SIGNING_KEY,
    )


def document(*, trusted: bool = False, tenant: str = "tenant-a") -> Document:
    return Document(
        document_id="doc-23",
        tenant_id=tenant,
        source="upload:supplier.txt",
        trusted=trusted,
        text="Quarterly report",
    )


def proposal(**arguments: object) -> ToolProposal:
    return ToolProposal(
        tool="export_report",
        tenant_id="tenant-a",
        document_id="doc-23",
        arguments={
            "destination": "http://capture-sink:8024/capture",
            "payload": "approved summary",
            **arguments,
        },
    )


def test_read_only_allowlisted_tool_needs_no_approval() -> None:
    request = ToolProposal(
        tool="search_catalog",
        tenant_id="tenant-a",
        document_id="doc-23",
        arguments={"query": "n8n"},
    )
    decision = policy().evaluate(request, document())
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_untrusted_source_cannot_reach_external_sink() -> None:
    decision = policy().evaluate(proposal(), document())
    assert decision.allowed is False
    assert "UNTRUSTED_SOURCE_TO_EXTERNAL_SINK" in decision.reason_codes
    assert "APPROVAL_MISSING_OR_STALE" in decision.reason_codes


def test_exact_approval_allows_trusted_external_action() -> None:
    request = proposal()
    approval = issue_approval(
        request,
        approver="alice",
        signing_key=SIGNING_KEY,
        now=1_000,
    )
    decision = policy().evaluate(request, document(trusted=True), approval=approval, now=1_100)
    assert decision.allowed is True


def test_approval_is_single_use() -> None:
    request = proposal()
    boundary = policy()
    approval = issue_approval(request, approver="alice", signing_key=SIGNING_KEY, now=1_000)
    first = boundary.evaluate(request, document(trusted=True), approval=approval, now=1_100)
    second = boundary.evaluate(request, document(trusted=True), approval=approval, now=1_101)
    assert first.allowed is True
    assert second.allowed is False
    assert "APPROVAL_ALREADY_USED" in second.reason_codes


def test_changed_arguments_invalidate_approval() -> None:
    approved = proposal()
    approval = issue_approval(approved, approver="alice", signing_key=SIGNING_KEY, now=1_000)
    changed = proposal(payload="different summary")
    decision = policy().evaluate(changed, document(trusted=True), approval=approval, now=1_100)
    assert decision.allowed is False
    assert "APPROVAL_MISSING_OR_STALE" in decision.reason_codes


def test_expired_approval_is_rejected() -> None:
    request = proposal()
    approval = issue_approval(request, approver="alice", signing_key=SIGNING_KEY, now=1_000)
    decision = policy().evaluate(request, document(trusted=True), approval=approval, now=1_301)
    assert "APPROVAL_MISSING_OR_STALE" in decision.reason_codes


def test_destination_allowlist_is_exact() -> None:
    request = proposal(destination="http://capture-sink.evil.invalid/capture")
    decision = policy().evaluate(request, document(trusted=True))
    assert "DESTINATION_NOT_ALLOWED" in decision.reason_codes


def test_tenant_mismatch_is_blocked() -> None:
    decision = policy().evaluate(proposal(), document(trusted=True, tenant="tenant-b"))
    assert "TENANT_MISMATCH" in decision.reason_codes


def test_unknown_tool_is_blocked() -> None:
    request = ToolProposal(
        tool="shell_exec",
        tenant_id="tenant-a",
        document_id="doc-23",
        arguments={"command": "whoami"},
    )
    decision = policy().evaluate(request, document(trusted=True))
    assert "TOOL_NOT_ALLOWLISTED" in decision.reason_codes


def test_manifest_change_detects_rug_pull() -> None:
    changed = CONTRACTS + (
        ToolContract(name="shell_exec", description="new write tool", risk=RiskClass.WRITE),
    )
    request = ToolProposal(
        tool="search_catalog",
        tenant_id="tenant-a",
        document_id="doc-23",
        arguments={"query": "n8n"},
    )
    decision = policy(changed).evaluate(request, document())
    assert "MANIFEST_CHANGED" in decision.reason_codes


def test_payload_limit_is_enforced() -> None:
    decision = policy().evaluate(proposal(payload="x" * 81), document(trusted=True))
    assert "PAYLOAD_TOO_LARGE" in decision.reason_codes


def test_audit_event_redacts_canary() -> None:
    decision = policy().evaluate(
        proposal(payload="CANARY-CH23-NOT-A-REAL-SECRET"),
        document(trusted=True),
    )
    assert "CANARY-" not in str(decision.audit_event)
    assert "[REDACTED]" in str(decision.audit_event)
