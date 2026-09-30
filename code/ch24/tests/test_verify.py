from __future__ import annotations

import httpx
import pytest

from document_release_service.verify import wait_for_trace_services


def test_wait_for_trace_services_handles_eventual_indexing() -> None:
    responses = iter(
        [
            ["ch24-api"],
            ["ch24-api", "ch24-mcp", "ch24-n8n"],
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"services": next(responses)}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observed = wait_for_trace_services(
            client,
            "http://jaeger.invalid",
            {"ch24-api", "ch24-mcp", "ch24-n8n"},
            attempts=2,
            delay=0,
        )

    assert observed == {"ch24-api", "ch24-mcp", "ch24-n8n"}


def test_wait_for_trace_services_reports_missing_services() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"services": ["ch24-api"]}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="ch24-mcp, ch24-n8n"):
            wait_for_trace_services(
                client,
                "http://jaeger.invalid",
                {"ch24-api", "ch24-mcp", "ch24-n8n"},
                attempts=2,
                delay=0,
            )
