from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from .auth import JsonlAuditSink, Principal


@dataclass(frozen=True)
class Document:
    id: str
    tenant_id: str
    title: str
    classification: str


DOCUMENTS = (
    Document("A-001", "tenant-a", "Informationsschutz", "intern"),
    Document("A-002", "tenant-a", "Lieferantenprüfung", "vertraulich"),
    Document("B-001", "tenant-b", "Standortstrategie", "vertraulich"),
)


def digest_arguments(arguments: dict[str, Any]) -> str:
    payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class DocumentPolicy:
    def __init__(self, audit: JsonlAuditSink) -> None:
        self.audit = audit

    def list_documents(self, principal: Principal) -> dict[str, Any]:
        self._require_consent(principal, "list_documents", {})
        visible = [document for document in DOCUMENTS if document.tenant_id == principal.tenant_id]
        self.audit.record(
            "tool_call",
            principal=principal,
            tool="list_documents",
            decision="allow",
            reason="tenant_filter_applied",
            argument_digest=digest_arguments({}),
        )
        return {
            "documents": [
                {
                    "id": document.id,
                    "title": document.title,
                    "classification": document.classification,
                }
                for document in visible
            ]
        }

    def read_document(self, principal: Principal, document_id: str) -> dict[str, Any]:
        args = {"document_id": document_id}
        self._require_consent(principal, "read_document", args)
        document = next((entry for entry in DOCUMENTS if entry.id == document_id), None)
        if document is None or document.tenant_id != principal.tenant_id:
            reason = "not_found" if document is None else "tenant_boundary"
            self.audit.record(
                "tool_call",
                principal=principal,
                tool="read_document",
                decision="deny",
                reason=reason,
                argument_digest=digest_arguments(args),
            )
            return {"found": False}

        self.audit.record(
            "tool_call",
            principal=principal,
            tool="read_document",
            decision="allow",
            reason="tenant_match",
            argument_digest=digest_arguments(args),
        )
        return {
            "found": True,
            "document": {
                "id": document.id,
                "title": document.title,
                "classification": document.classification,
            },
        }

    def _require_consent(
        self,
        principal: Principal,
        tool: str,
        arguments: dict[str, Any],
    ) -> None:
        if principal.consent_status == "granted":
            return
        self.audit.record(
            "tool_call",
            principal=principal,
            tool=tool,
            decision="deny",
            reason="consent_not_granted",
            argument_digest=digest_arguments(arguments),
        )
        raise ToolError("Zugriff verweigert: Für diesen Aufruf liegt kein aktiver Consent vor.")
