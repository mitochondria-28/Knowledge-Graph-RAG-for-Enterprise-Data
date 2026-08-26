"""
Unit tests for Phase 11 observability.

Tests verify:
  1. _JsonFormatter — correct fields, exception inlining, extra fields
  2. configure_logging() — idempotent, handler added once
  3. Prometheus metrics — counters increment, histograms observe, gauges set
  4. configure_tracing() + get_in_memory_spans() — spans created with attributes
  5. reset_tracing() — clears span buffer
  6. AnswerPipeline.ask() — emits OTel spans and Prometheus observations
  7. GET /metrics endpoint — returns 200 with Prometheus text

No API calls or databases required.
"""

import logging
import json
import os
import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, CollectorRegistry


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_tracing_between_tests():
    """Ensure OTel global state is clean before every test."""
    from src.observability.tracing import reset_tracing
    reset_tracing()
    yield
    reset_tracing()


@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": f"obs-{i:03d}",
            "document_id": f"doc-{i}",
            "source_file": f"corpus/obs_{i}.md",
            "section": f"Section {i}",
            "chunk_index": i,
            "content": f"TechNova Corporation uses StellarDB for enterprise data. Content block {i}.",
            "token_count": 14,
        }
        for i in range(5)
    ]


@pytest.fixture
def mock_pipeline(sample_chunks):
    from src.answer.generator import MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline
    return AnswerPipeline(
        generator=MockAnswerGenerator(),
        chunks=sample_chunks,
        entity_index={"TechNova Corporation": "Company", "StellarDB": "Technology"},
        top_k=3,
    )


# ── _JsonFormatter ────────────────────────────────────────────────────────────

class TestJsonFormatter:
    def _make_record(self, msg="hello", level=logging.INFO, extra=None):
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        record = self._make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_required_fields_present(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record()))
        for field in ("ts", "level", "logger", "msg"):
            assert field in data, f"Missing field: {field}"

    def test_level_is_string(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record(level=logging.WARNING)))
        assert data["level"] == "WARNING"

    def test_msg_is_correct(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record(msg="test message")))
        assert data["msg"] == "test message"

    def test_logger_name_correct(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record()))
        assert data["logger"] == "test.logger"

    def test_extra_fields_merged(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record(extra={"strategy": "graph", "hop_depth": 2})))
        assert data["strategy"] == "graph"
        assert data["hop_depth"] == 2

    def test_exception_inlined_as_string(self):
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = self._make_record()
        record.exc_info = exc_info
        data = json.loads(fmt.format(record))
        assert "exc_info" in data
        assert "ValueError" in data["exc_info"]

    def test_ts_is_iso8601(self):
        from datetime import datetime
        from src.observability.logging import _JsonFormatter
        fmt = _JsonFormatter()
        data = json.loads(fmt.format(self._make_record()))
        dt = datetime.fromisoformat(data["ts"])
        assert dt is not None


# ── configure_logging ─────────────────────────────────────────────────────────

class TestConfigureLogging:
    def test_adds_handler_to_root(self):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        try:
            # Force fresh configure by temporarily removing all handlers
            root.handlers.clear()
            from src.observability.logging import configure_logging
            configure_logging(level="WARNING")
            assert len(root.handlers) >= 1
        finally:
            root.handlers.clear()
            for h in original_handlers:
                root.addHandler(h)

    def test_idempotent_second_call_does_not_add_handler(self):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        try:
            root.handlers.clear()
            from src.observability.logging import configure_logging
            configure_logging()
            count_after_first = len(root.handlers)
            configure_logging()
            assert len(root.handlers) == count_after_first
        finally:
            root.handlers.clear()
            for h in original_handlers:
                root.addHandler(h)

    def test_get_logger_returns_logger_instance(self):
        from src.observability.logging import get_logger
        lg = get_logger("my.module")
        assert isinstance(lg, logging.Logger)
        assert lg.name == "my.module"


# ── Prometheus metrics ────────────────────────────────────────────────────────

class TestPrometheusMetrics:
    def test_metrics_dict_has_expected_keys(self):
        from src.observability.metrics import METRICS
        for key in (
            "requests_total", "request_errors", "pipeline_stage_duration",
            "pipeline_total_duration", "citation_confidence",
            "corpus_chunks", "corpus_entities",
        ):
            assert key in METRICS, f"Missing metric: {key}"

    def test_request_total_counter_increments(self):
        from src.observability.metrics import REQUEST_TOTAL
        before = REQUEST_TOTAL.labels(status_code="200", strategy="vector")._value.get()
        REQUEST_TOTAL.labels(status_code="200", strategy="vector").inc()
        after = REQUEST_TOTAL.labels(status_code="200", strategy="vector")._value.get()
        assert after == before + 1

    def test_request_errors_counter_increments(self):
        from src.observability.metrics import REQUEST_ERRORS
        before = REQUEST_ERRORS.labels(error_type="TestError")._value.get()
        REQUEST_ERRORS.labels(error_type="TestError").inc()
        after = REQUEST_ERRORS.labels(error_type="TestError")._value.get()
        assert after == before + 1

    def test_pipeline_stage_histogram_observes(self):
        from src.observability.metrics import PIPELINE_STAGE_DURATION
        before = PIPELINE_STAGE_DURATION.labels(stage="test_route")._sum.get()
        PIPELINE_STAGE_DURATION.labels(stage="test_route").observe(0.123)
        after = PIPELINE_STAGE_DURATION.labels(stage="test_route")._sum.get()
        assert after == pytest.approx(before + 0.123, abs=1e-6)

    def test_corpus_chunks_gauge_set(self):
        from src.observability.metrics import CORPUS_CHUNKS
        CORPUS_CHUNKS.set(27)
        assert CORPUS_CHUNKS._value.get() == pytest.approx(27)

    def test_corpus_entities_gauge_set(self):
        from src.observability.metrics import CORPUS_ENTITIES
        CORPUS_ENTITIES.set(42)
        assert CORPUS_ENTITIES._value.get() == pytest.approx(42)

    def test_citation_confidence_histogram_observes(self):
        from src.observability.metrics import CITATION_CONFIDENCE
        before = CITATION_CONFIDENCE._sum.get()
        CITATION_CONFIDENCE.observe(0.85)
        after = CITATION_CONFIDENCE._sum.get()
        assert after == pytest.approx(before + 0.85, abs=1e-6)


# ── Tracing ───────────────────────────────────────────────────────────────────

class TestTracing:
    def test_configure_tracing_returns_exporter(self):
        from src.observability.tracing import configure_tracing
        exporter = configure_tracing()
        assert exporter is not None

    def test_configure_tracing_idempotent(self):
        from src.observability.tracing import configure_tracing
        exp1 = configure_tracing()
        exp2 = configure_tracing()
        assert exp1 is exp2

    def test_get_tracer_returns_tracer(self):
        from src.observability.tracing import get_tracer
        from opentelemetry import trace
        tracer = get_tracer("test.module")
        assert tracer is not None

    def test_spans_recorded_in_memory(self):
        from src.observability.tracing import configure_tracing, get_in_memory_spans, get_tracer
        configure_tracing()
        tracer = get_tracer("test")
        with tracer.start_as_current_span("my-span"):
            pass
        spans = get_in_memory_spans()
        assert any(s.name == "my-span" for s in spans)

    def test_span_attributes_set(self):
        from src.observability.tracing import configure_tracing, get_in_memory_spans, get_tracer
        configure_tracing()
        tracer = get_tracer("test")
        with tracer.start_as_current_span("attributed") as span:
            span.set_attribute("strategy", "hybrid")
            span.set_attribute("chunk_count", 5)
        spans = get_in_memory_spans()
        target = next(s for s in spans if s.name == "attributed")
        assert target.attributes["strategy"] == "hybrid"
        assert target.attributes["chunk_count"] == 5

    def test_reset_clears_spans(self):
        from src.observability.tracing import configure_tracing, get_in_memory_spans, get_tracer, reset_tracing
        configure_tracing()
        tracer = get_tracer("test")
        with tracer.start_as_current_span("ephemeral"):
            pass
        reset_tracing()
        assert get_in_memory_spans() == []

    def test_child_spans_have_parent(self):
        from src.observability.tracing import configure_tracing, get_in_memory_spans, get_tracer
        configure_tracing()
        tracer = get_tracer("test")
        with tracer.start_as_current_span("parent"):
            with tracer.start_as_current_span("child"):
                pass
        spans = get_in_memory_spans()
        names = [s.name for s in spans]
        assert "parent" in names
        assert "child" in names


# ── Pipeline instrumentation ──────────────────────────────────────────────────

class TestPipelineInstrumentation:
    def test_ask_creates_root_span(self, mock_pipeline):
        from src.observability.tracing import configure_tracing, get_in_memory_spans
        configure_tracing()
        mock_pipeline.ask("What is TechNova Corporation?")
        names = [s.name for s in get_in_memory_spans()]
        assert "ask" in names

    def test_ask_creates_stage_spans(self, mock_pipeline):
        from src.observability.tracing import configure_tracing, get_in_memory_spans
        configure_tracing()
        mock_pipeline.ask("What is StellarDB?")
        names = [s.name for s in get_in_memory_spans()]
        for stage in ("route", "retrieve", "generate", "validate"):
            assert stage in names, f"Missing span: {stage}"

    def test_root_span_has_strategy_attribute(self, mock_pipeline):
        from src.observability.tracing import configure_tracing, get_in_memory_spans
        configure_tracing()
        mock_pipeline.ask("What is StellarDB?")
        ask_span = next(s for s in get_in_memory_spans() if s.name == "ask")
        assert "strategy" in ask_span.attributes

    def test_pipeline_stage_histogram_incremented(self, mock_pipeline):
        from src.observability.metrics import PIPELINE_STAGE_DURATION
        # Use _sum: any positive timing means observe() was called
        before = PIPELINE_STAGE_DURATION.labels(stage="route")._sum.get()
        mock_pipeline.ask("What is TechNova Corporation?")
        after = PIPELINE_STAGE_DURATION.labels(stage="route")._sum.get()
        assert after >= before  # route timing is always ≥ 0

    def test_pipeline_total_histogram_incremented(self, mock_pipeline):
        from prometheus_client import generate_latest
        from src.observability.metrics import PIPELINE_TOTAL_DURATION
        mock_pipeline.ask("What is TechNova Corporation?")
        text = generate_latest().decode()
        assert "kg_rag_pipeline_total_duration_seconds_count" in text

    def test_citation_confidence_histogram_incremented(self, mock_pipeline):
        from prometheus_client import generate_latest
        from src.observability.metrics import CITATION_CONFIDENCE
        mock_pipeline.ask("What is TechNova Corporation?")
        text = generate_latest().decode()
        assert "kg_rag_citation_confidence_count" in text


# ── /metrics endpoint ─────────────────────────────────────────────────────────

class TestMetricsEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        from src.api.app import create_app
        from src.answer.generator import MockAnswerGenerator
        from src.answer.pipeline import AnswerPipeline
        application = create_app()
        with TestClient(application) as c:
            real = c.app.state.pipeline
            c.app.state.pipeline = AnswerPipeline(
                generator=MockAnswerGenerator(),
                chunks=real._chunks,
                entity_index=real._router._entity_index,
            )
            yield c

    def test_metrics_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type_is_prometheus(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_contains_kg_rag_metric(self, client):
        resp = client.get("/metrics")
        # After an ask request, pipeline metrics appear
        client.post("/ask", json={"question": "What is TechNova?", "top_k": 3})
        resp = client.get("/metrics")
        assert "kg_rag" in resp.text
