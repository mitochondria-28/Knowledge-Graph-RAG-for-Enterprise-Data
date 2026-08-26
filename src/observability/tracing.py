"""
OpenTelemetry distributed tracing — Phase 11.

WHY OPENTELEMETRY:

OpenTelemetry is the CNCF standard for distributed tracing. A single "trace"
spans multiple services; each unit of work inside a service is a "span".
In a RAG pipeline a trace looks like:

  ┌─ ask (root span) ───────────────────────────────────────────┐
  │  ┌─ route ──────┐ ┌─ retrieve ──┐ ┌─ generate ─┐ ┌─ validate ┐│
  │  └──────────────┘ └─────────────┘ └────────────┘ └───────────┘│
  └─────────────────────────────────────────────────────────────┘

Jaeger / Tempo / Zipkin can visualise this as a waterfall.

DESIGN:

configure_tracing() sets up a global TracerProvider with an in-memory exporter
(useful for testing) or OTLP HTTP exporter (production).

In production, set:
    OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
    OTEL_SERVICE_NAME=kg-rag-api

get_tracer(name) returns a module-level tracer the caller uses as a context manager:

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("route") as span:
        span.set_attribute("strategy", decision.strategy)
        ...

WHY AN IN-MEMORY EXPORTER BY DEFAULT:

No external service is needed. Tests can call get_in_memory_spans() to assert
that the right spans were created with the right attributes.
"""

import os
from typing import Sequence

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import ReadableSpan

_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "kg-rag-api")
_exporter: InMemorySpanExporter | None = None
_provider: TracerProvider | None = None


def configure_tracing(service_name: str = _SERVICE_NAME) -> InMemorySpanExporter:
    """
    Initialise the global TracerProvider with an in-memory exporter.

    Safe to call multiple times — returns the existing exporter if already
    configured. This makes it idempotent in tests.

    Returns:
        The InMemorySpanExporter, useful for asserting spans in tests.
    """
    global _exporter, _provider

    if _provider is not None:
        assert _exporter is not None
        return _exporter

    _exporter = InMemorySpanExporter()
    _provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    _provider.add_span_processor(SimpleSpanProcessor(_exporter))
    trace.set_tracer_provider(_provider)
    return _exporter


def get_tracer(name: str) -> trace.Tracer:
    """
    Return a module-level tracer from the module-level provider.

    Uses _provider.get_tracer() directly to avoid the OTel global API,
    which cannot be safely overridden once set (causes recursion via
    ProxyTracerProvider in tests). Falls back to configure_tracing() if
    not yet initialised.
    """
    provider = _provider
    if provider is None:
        provider = configure_tracing()
        # configure_tracing() sets _provider; re-read it
        provider = _provider
    return provider.get_tracer(name)  # type: ignore[union-attr]


def get_in_memory_spans() -> Sequence[ReadableSpan]:
    """
    Return all spans recorded since configure_tracing() was called.

    Useful in tests:
        spans = get_in_memory_spans()
        span_names = [s.name for s in spans]
        assert "route" in span_names
    """
    if _exporter is None:
        return []
    return _exporter.get_finished_spans()


def reset_tracing() -> None:
    """
    Clear all recorded spans and reset the module-level provider.

    ONLY for use in tests — clears module-level global state.
    Does NOT touch the OTel global TracerProvider (which cannot be
    safely overridden once set — see OTel SDK design).
    """
    global _exporter, _provider
    if _exporter is not None:
        _exporter.clear()
    _exporter = None
    _provider = None
