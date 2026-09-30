from __future__ import annotations

import pytest
from mcp import Client

from document_release_service.mcp_server import create_server
from document_release_service.models import DocumentInput
from document_release_service.repository import MemoryRepository
from document_release_service.service import DocumentReleaseService


@pytest.mark.anyio
async def test_mcp_server_exposes_only_read_tools() -> None:
    repository = MemoryRepository()
    service = DocumentReleaseService(repository, signing_key=b"test")
    service.ingest(
        DocumentInput(
            document_id="DOC-024",
            title="Compliance-Handbuch",
            source="fixture:compliance.txt",
            text="Das Handbuch beschreibt die freigegebenen Kontrollmaßnahmen.",
            trusted=True,
        ),
        tenant_id="tenant-a",
        correlation_id="corr-24",
    )
    server = create_server(repository, tenant_id="tenant-a", require_auth=False)
    async with Client(server) as client:
        listed = await client.list_tools()
        result = await client.call_tool("search_documents", {"query": "Compliance"})
        resource = await client.read_resource("document://DOC-024")
    names = {tool.name for tool in listed.tools}
    assert names == {"search_documents", "read_document"}
    assert result.is_error is False
    assert result.structured_content is not None
    assert resource.contents


@pytest.mark.anyio
async def test_mcp_missing_document_is_a_tool_error() -> None:
    server = create_server(MemoryRepository(), tenant_id="tenant-a", require_auth=False)
    async with Client(server) as client:
        result = await client.call_tool("read_document", {"document_id": "MISSING"})
    assert result.is_error is True
