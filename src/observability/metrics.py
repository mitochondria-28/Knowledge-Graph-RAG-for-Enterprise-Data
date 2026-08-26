"""
Prometheus metrics — Phase 11.

WHY PROMETHEUS:

prometheus_client is the de-facto Python instrumentation library.
It exposes an HTTP scrape endpoint (/metrics) that Prometheus server polls
every 15–60 seconds. Grafana reads from Prometheus to render dashboards.

METRIC TYPES USED:

  Counter   — monotonically increasing totals (requests, errors)
              Query: rate(kg_rag_requests_total[5m])

  Histogram — samples with configurable bucket boundaries
              Query: histogram_quantile(0.95, kg_rag_pipeline_duration_seconds_bucket)

  Gauge     — current value, can go up or down (chunk count at startup)
              Query: kg_rag_corpus_chunks

DESIGN:

All metrics live in one METRICS dict so they're importable in one place:

    from src.observability.metrics import METRICS
    METRICS["requests_total"].labels(status="200", strategy="graph").inc()

The namespace "kg_rag" prevents collisions with other apps on the same host.

BUCKETS:

Pipeline duration buckets cover the expected latency range:
  Mock mode: <0.01s per stage
  Real Claude: 0.5s–2.0s for generation
Upper bound 5.0s catches slow LLM responses; +Inf is always added automatically.
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Request counters ──────────────────────────────────────────────────────────

REQUEST_TOTAL = Counter(
    name="kg_rag_requests_total",
    documentation="Total HTTP requests to /ask by HTTP status code and routing strategy",
    labelnames=["status_code", "strategy"],
)

REQUEST_ERRORS = Counter(
    name="kg_rag_request_errors_total",
    documentation="Total /ask errors by error type",
    labelnames=["error_type"],
)

# ── Pipeline stage histograms ─────────────────────────────────────────────────

_BUCKETS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)

PIPELINE_STAGE_DURATION = Histogram(
    name="kg_rag_pipeline_stage_duration_seconds",
    documentation="Per-stage pipeline latency in seconds",
    labelnames=["stage"],
    buckets=_BUCKETS,
)

PIPELINE_TOTAL_DURATION = Histogram(
    name="kg_rag_pipeline_total_duration_seconds",
    documentation="End-to-end pipeline latency in seconds (route+retrieve+generate+validate)",
    buckets=_BUCKETS,
)

# ── Citation quality gauge ────────────────────────────────────────────────────

CITATION_CONFIDENCE = Histogram(
    name="kg_rag_citation_confidence",
    documentation="Fraction of citations that pass validation per request (0.0–1.0)",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# ── Corpus gauges (set once at startup) ──────────────────────────────────────

CORPUS_CHUNKS = Gauge(
    name="kg_rag_corpus_chunks",
    documentation="Number of chunks loaded at startup",
)

CORPUS_ENTITIES = Gauge(
    name="kg_rag_corpus_entities",
    documentation="Number of entity names/aliases in the entity index",
)

# ── Convenience dict for callers ──────────────────────────────────────────────

METRICS: dict[str, object] = {
    "requests_total":          REQUEST_TOTAL,
    "request_errors":          REQUEST_ERRORS,
    "pipeline_stage_duration": PIPELINE_STAGE_DURATION,
    "pipeline_total_duration": PIPELINE_TOTAL_DURATION,
    "citation_confidence":     CITATION_CONFIDENCE,
    "corpus_chunks":           CORPUS_CHUNKS,
    "corpus_entities":         CORPUS_ENTITIES,
}
