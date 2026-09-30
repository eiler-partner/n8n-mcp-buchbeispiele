from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx


DOCUMENT = {
    "document_id": "SUP-2026-001",
    "title": "Lieferantenprüfung Alpenstahl",
    "source": "fixture:supplier-alpenstahl.txt",
    "text": "Die Compliance-Lieferantenerklärung wurde geprüft. ISO 27001 ist bis Dezember 2027 gültig.",
    "trusted": True,
}


def wait_for_trace_services(
    client: httpx.Client,
    jaeger_url: str,
    required: set[str],
    *,
    attempts: int = 20,
    delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> set[str]:
    """Wait for Jaeger's eventually consistent service index."""
    observed: set[str] = set()
    for attempt in range(attempts):
        response = client.get(f"{jaeger_url}/api/v3/services")
        response.raise_for_status()
        observed = set(response.json()["services"])
        if required <= observed:
            return observed
        if attempt + 1 < attempts:
            sleep(delay)
    missing = ", ".join(sorted(required - observed))
    raise RuntimeError(f"Erwartete OpenTelemetry-Dienste fehlen in Jaeger: {missing}")


def verify(
    base_url: str,
    *,
    n8n_url: str,
    jaeger_url: str,
    output: Path | None = None,
) -> dict[str, object]:
    correlation_id = "ch24-e2e-001"
    headers = {"X-Tenant-ID": "tenant-alpen", "X-Correlation-ID": correlation_id}
    with httpx.Client(timeout=30) as client:
        ingestion = client.post(
            f"{n8n_url}/webhook/ch24-document-intake",
            headers={"X-Correlation-ID": correlation_id},
            json=DOCUMENT,
        )
        ingestion.raise_for_status()
        ingested = ingestion.json()
        agent = client.post(
            f"{n8n_url}/webhook/ch24-agent-query",
            json={"question": "Welche Compliance-Dokumente sind vorhanden?"},
        )
        agent.raise_for_status()
        agent_result = agent.json()
        if DOCUMENT["document_id"] not in str(agent_result.get("output", "")):
            raise RuntimeError("n8n-Agent erhielt kein passendes MCP-Dokument")
        proposal = {
            "document_id": DOCUMENT["document_id"],
            "content_hash": ingested["content_hash"],
            "summary": "Die geprüfte Lieferantenerklärung bestätigt eine gültige ISO-27001-Zertifizierung.",
            "destination": "local://published-reviews",
        }
        requested = client.post(
            f"{base_url}/publication-requests", headers=headers, json=proposal
        )
        requested.raise_for_status()
        request_id = requested.json()["request_id"]
        before = client.post(
            f"{base_url}/publication-requests/{request_id}/execute",
            headers={"X-Executor-Key": "chapter-24-local-executor-key-change-me"},
        )
        if before.status_code != 409:
            raise RuntimeError("Executor lief ohne menschliche Freigabe")
        approved = client.post(
            f"{base_url}/publication-requests/{request_id}/decision",
            headers={"X-Approval-Key": "chapter-24-local-approval-key-change-me"},
            json={"reviewer": "reviewer@example.invalid", "approve": True},
        )
        approved.raise_for_status()
        executed = client.post(
            f"{base_url}/publication-requests/{request_id}/execute",
            headers={"X-Executor-Key": "chapter-24-local-executor-key-change-me"},
        )
        executed.raise_for_status()
        outbox = client.get(f"{base_url}/outbox/{request_id}")
        outbox.raise_for_status()
        required_trace_services = {"ch24-api", "ch24-mcp", "ch24-n8n"}
        wait_for_trace_services(client, jaeger_url, required_trace_services)

    report: dict[str, object] = {
        "correlation_id": correlation_id,
        "document_id": DOCUMENT["document_id"],
        "created": ingested["created"],
        "n8n_ingestion": True,
        "n8n_mcp_agent": DOCUMENT["document_id"] in agent_result["output"],
        "blocked_before_approval": True,
        "approved_by": approved.json()["approver"],
        "published": outbox.json()["request_id"] == request_id,
        "destination": outbox.json()["destination"],
        "trace_services": sorted(required_trace_services),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prüft den vollständigen Kapitel-24-Schreibpfad.")
    parser.add_argument("--url", default="http://127.0.0.1:8024")
    parser.add_argument("--n8n-url", default="http://127.0.0.1:5678")
    parser.add_argument("--jaeger-url", default="http://127.0.0.1:16686")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.url,
                n8n_url=args.n8n_url,
                jaeger_url=args.jaeger_url,
                output=args.output,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
