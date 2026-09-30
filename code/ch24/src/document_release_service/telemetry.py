from __future__ import annotations

import logging
import os


_configured = False


def configure_tracing(service_name: str) -> None:
    global _configured
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if _configured or not endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
    _configured = True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
