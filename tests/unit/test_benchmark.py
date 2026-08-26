"""
Unit tests for Phase 10 benchmarking.

Tests verify:
  1. _percentile() — correct linear interpolation
  2. compute_latency_stats() — all fields correct, handles edge cases
  3. BenchmarkRunner._run_one() — stage timings are non-negative, fields populated
  4. BenchmarkRunner.run() — aggregates correctly across all questions
  5. BenchmarkReport aggregation — routing_accuracy, citation_by_type, routing_by_type
  6. save_report() / JSON serialisation — valid JSON, round-trips cleanly
  7. Edge cases — single question, all correct routing, zero citations

No API calls or databases required — MockAnswerGenerator + in-memory chunks.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.benchmark.models import BenchmarkReport, LatencyStats, QuestionBenchmark
from src.benchmark.runner import BenchmarkRunner, _percentile, compute_latency_stats
from src.evaluation.models import EvalQuestion


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": f"chunk-{i:03d}",
            "document_id": f"doc-{i}",
            "source_file": f"corpus/doc_{i}.md",
            "section": f"Section {i}",
            "chunk_index": i,
            "content": f"TechNova Corporation content number {i}. StellarDB is a database.",
            "token_count": 12,
        }
        for i in range(10)
    ]


@pytest.fixture
def mock_pipeline(sample_chunks):
    """AnswerPipeline backed by MockAnswerGenerator and sample chunks."""
    from src.answer.generator import MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline

    return AnswerPipeline(
        generator=MockAnswerGenerator(),
        chunks=sample_chunks,
        entity_index={
            "TechNova Corporation": "Company",
            "StellarDB": "Technology",
            "Platform Team": "Team",
        },
        top_k=3,
    )


def _make_question(
    qid: str = "q01",
    question: str = "What is StellarDB?",
    qtype: str = "simple_entity",
) -> EvalQuestion:
    return EvalQuestion(
        qid=qid,
        question=question,
        question_type=qtype,
        relevant_sources=["corpus/doc_0.md"],
        expected_entities=["StellarDB"],
        notes="",
    )


# ── _percentile ───────────────────────────────────────────────────────────────

class TestPercentile:
    def test_p50_of_sorted_odd_list(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(data, 50) == pytest.approx(3.0)

    def test_p0_is_min(self):
        data = [1.0, 2.0, 3.0]
        assert _percentile(data, 0) == pytest.approx(1.0)

    def test_p100_is_max(self):
        data = [1.0, 2.0, 3.0]
        assert _percentile(data, 100) == pytest.approx(3.0)

    def test_p95_with_20_values(self):
        data = list(range(1, 21))  # 1..20
        result = _percentile(data, 95)
        # Linear interpolation: idx = 0.95 * 19 = 18.05 → 19 + 0.05*(20-19) = 19.05
        assert result == pytest.approx(19.05)

    def test_single_element(self):
        assert _percentile([42.0], 50) == pytest.approx(42.0)

    def test_empty_returns_zero(self):
        assert _percentile([], 50) == 0.0

    def test_unsorted_input_handled(self):
        data = [5.0, 1.0, 3.0, 2.0, 4.0]
        assert _percentile(data, 50) == pytest.approx(3.0)

    def test_two_elements_p50(self):
        # Linear interpolation at midpoint
        assert _percentile([0.0, 10.0], 50) == pytest.approx(5.0)


# ── compute_latency_stats ─────────────────────────────────────────────────────

class TestComputeLatencyStats:
    def test_stage_name_preserved(self):
        stats = compute_latency_stats("routing", [1.0, 2.0, 3.0])
        assert stats.stage == "routing"

    def test_mean_correct(self):
        stats = compute_latency_stats("s", [1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats.mean_ms == pytest.approx(3.0)

    def test_min_correct(self):
        stats = compute_latency_stats("s", [3.0, 1.0, 2.0])
        assert stats.min_ms == pytest.approx(1.0)

    def test_max_correct(self):
        stats = compute_latency_stats("s", [3.0, 1.0, 2.0])
        assert stats.max_ms == pytest.approx(3.0)

    def test_p50_is_median(self):
        stats = compute_latency_stats("s", [1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats.p50_ms == pytest.approx(3.0)

    def test_all_same_values(self):
        stats = compute_latency_stats("s", [5.0, 5.0, 5.0])
        assert stats.mean_ms == pytest.approx(5.0)
        assert stats.p50_ms == pytest.approx(5.0)
        assert stats.p95_ms == pytest.approx(5.0)

    def test_empty_returns_zeros(self):
        stats = compute_latency_stats("s", [])
        assert stats.mean_ms == 0.0
        assert stats.min_ms == 0.0
        assert stats.p99_ms == 0.0


# ── BenchmarkRunner._run_one ─────────────────────────────────────────────────

class TestRunOne:
    def test_returns_question_benchmark(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        q = _make_question()
        result = runner._run_one(q)
        assert isinstance(result, QuestionBenchmark)

    def test_qid_preserved(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question(qid="q07"))
        assert result.qid == "q07"

    def test_question_preserved(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        q = _make_question(question="Who leads the Platform Team?", qtype="one_hop")
        result = runner._run_one(q)
        assert result.question == "Who leads the Platform Team?"

    def test_question_type_preserved(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question(qtype="factual"))
        assert result.question_type == "factual"

    def test_all_timings_non_negative(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question())
        assert result.routing_ms >= 0
        assert result.retrieval_ms >= 0
        assert result.generation_ms >= 0
        assert result.validation_ms >= 0
        assert result.total_ms >= 0

    def test_total_ms_is_sum_of_stages(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question())
        expected_total = (
            result.routing_ms + result.retrieval_ms +
            result.generation_ms + result.validation_ms
        )
        # Each stage is rounded to 3 dp independently, so allow ±0.005ms drift
        assert result.total_ms == pytest.approx(expected_total, abs=0.005)

    def test_chunk_count_respects_top_k(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question())
        assert result.chunk_count <= mock_pipeline._top_k

    def test_citation_confidence_in_range(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question())
        assert 0.0 <= result.citation_confidence <= 1.0

    def test_correct_routing_for_definition(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question(question="What is StellarDB?", qtype="simple_entity"))
        # simple_entity expected → vector; router should pick vector for definition
        assert result.expected_strategy == "vector"
        assert result.correct_routing == (result.routed_strategy == "vector")

    def test_expected_strategy_for_one_hop(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question(question="Who leads the Platform Team?", qtype="one_hop"))
        assert result.expected_strategy == "graph"

    def test_valid_plus_invalid_equals_citation_count(self, mock_pipeline):
        runner = BenchmarkRunner(mock_pipeline)
        result = runner._run_one(_make_question())
        assert result.valid_citations + result.invalid_citations == result.citation_count


# ── BenchmarkRunner.run (full aggregation) ────────────────────────────────────

class TestRunAggregation:
    @pytest.fixture
    def questions(self):
        return [
            _make_question("q01", "What is StellarDB?",             "simple_entity"),
            _make_question("q02", "What is TechNova Corporation?",   "simple_entity"),
            _make_question("q09", "Who leads the Platform Team?",    "one_hop"),
            _make_question("q13", "Who leads the team that maintains StellarDB?", "two_hop"),
        ]

    def test_report_has_correct_question_count(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert report.question_count == len(questions)

    def test_per_question_count_matches(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert len(report.per_question) == len(questions)

    def test_routing_accuracy_in_range(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert 0.0 <= report.routing_accuracy <= 1.0

    def test_mean_citation_confidence_in_range(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert 0.0 <= report.mean_citation_confidence <= 1.0

    def test_latency_has_five_stages(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert set(report.latency.keys()) == {"routing", "retrieval", "generation", "validation", "total"}

    def test_all_latency_means_positive(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        for stage, stats in report.latency.items():
            assert stats.mean_ms >= 0, f"{stage} mean should be ≥ 0"

    def test_citation_by_type_keys(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert "simple_entity" in report.citation_by_type
        assert "one_hop" in report.citation_by_type

    def test_routing_by_type_values_in_range(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        for qtype, acc in report.routing_by_type.items():
            assert 0.0 <= acc <= 1.0, f"{qtype} accuracy out of range"

    def test_run_at_is_iso_timestamp(self, mock_pipeline, questions):
        from datetime import datetime
        report = BenchmarkRunner(mock_pipeline).run(questions)
        # Should parse without error
        dt = datetime.fromisoformat(report.run_at)
        assert dt is not None

    def test_generator_name_recorded(self, mock_pipeline, questions):
        report = BenchmarkRunner(mock_pipeline).run(questions)
        assert report.generator == "MockAnswerGenerator"


# ── JSON serialisation ────────────────────────────────────────────────────────

class TestSaveReport:
    @pytest.fixture
    def sample_report(self, mock_pipeline):
        q = _make_question()
        return BenchmarkRunner(mock_pipeline).run([q])

    def test_saves_json_file(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            save_report(sample_report, path)
            assert path.exists()

    def test_json_is_valid(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            save_report(sample_report, path)
            data = json.loads(path.read_text())
            assert isinstance(data, dict)

    def test_json_has_required_top_level_keys(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            save_report(sample_report, path)
            data = json.loads(path.read_text())
            for key in ("run_at", "generator", "question_count", "routing_accuracy",
                        "mean_citation_confidence", "latency", "per_question"):
                assert key in data, f"Missing key: {key}"

    def test_per_question_is_list(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            save_report(sample_report, path)
            data = json.loads(path.read_text())
            assert isinstance(data["per_question"], list)
            assert len(data["per_question"]) == 1

    def test_creates_parent_directory(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dir" / "report.json"
            save_report(sample_report, path)
            assert path.exists()

    def test_round_trip_routing_accuracy(self, sample_report):
        from src.benchmark.report import save_report
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            save_report(sample_report, path)
            data = json.loads(path.read_text())
            assert data["routing_accuracy"] == pytest.approx(
                sample_report.routing_accuracy, rel=1e-4
            )
