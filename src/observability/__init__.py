"""
Observability package — Phase 11.

Exports the three pillars in one place so callers import from a single module:

    from src.observability import get_logger, metrics, tracer

Pillars:
  logging  — structured JSON logs via stdlib logging + structlog-style formatting
  metrics  — Prometheus counters / histograms (prometheus_client)
  tracing  — OpenTelemetry spans (opentelemetry-sdk)
"""

from src.observability.logging import configure_logging, get_logger
from src.observability.metrics import METRICS
from src.observability.tracing import get_tracer

__all__ = ["configure_logging", "get_logger", "METRICS", "get_tracer"]
