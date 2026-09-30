from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_auth_lab.auth import JsonlAuditSink, Principal
from mcp_auth_lab.policy import DocumentPolicy


def principal(*, tenant: str = "tenant-a", consent: str = "granted") -> Principal:
    return Principal(
        issuer="https://issuer.example",
        subject="alice",
        client_id="test-client",
        tenant_id=tenant,
        scopes=frozenset({"documents:read"}),
        consent_id="consent-123",
        consent_status=consent,
    )


def test_tenant_filter_is_derived_from_signed_principal(tmp_path) -> None:
    policy = DocumentPolicy(JsonlAuditSink(tmp_path / "audit.jsonl"))
    result = policy.list_documents(principal())
    assert [entry["id"] for entry in result["documents"]] == ["A-001", "A-002"]


def test_cross_tenant_document_is_indistinguishable_from_missing(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    policy = DocumentPolicy(JsonlAuditSink(audit_path))
    assert policy.read_document(principal(), "B-001") == {"found": False}
    assert policy.read_document(principal(), "does-not-exist") == {"found": False}
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert {row["reason"] for row in rows} == {"tenant_boundary", "not_found"}


def test_consent_denial_prevents_tool_result(tmp_path) -> None:
    policy = DocumentPolicy(JsonlAuditSink(tmp_path / "audit.jsonl"))
    with pytest.raises(ToolError, match="kein aktiver Consent"):
        policy.list_documents(principal(consent="denied"))
