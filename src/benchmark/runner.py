"""
Benchmark runner — Phase 10.

WHY THE RUNNER CALLS PIPELINE STAGES DIRECTLY (NOT pipeline.ask()):

pipeline.ask() times the entire call and returns a single latency figure.
To get per-stage breakdowns we need to call each stage separately with our
own clock around each one. This is the only correct way — measuring wall
time inside pipeline.ask() via monkey-patching would be fragile and would
couple the benchmark to implementation details.

The downside is that the runner knows about pipeline internals (_router,
_retriever_fn, _generator, _validator, _chunks). This is acceptable for a
benchmark — it's not production code, it's a measurement tool.

EXPECTED STRATEGY MAP:

Taken from Phase 6 evaluation. These are the "ground truth" routing
decisions. Routing accuracy = fraction of questions where the router's
decision matches the expected strategy.

PERCENTILE CALCULATION:

With 20 questions, p99 ≈ max. We use linear interpolation (the same
method as numpy.percentile with interpolation='linear') so the harness
is correct for larger question sets too.
"""

import logging
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone

from src.benchmark.models import BenchmarkReport, LatencyStats, QuestionBenchmark
from src.evaluation.models import EvalQuestion

logger = logging.getLogger(__name__)

# Expected routing strategy per Phase 6 question type
_EXPECTED: dict[str, str] = {
    "simple_entity": "vector",
    "factual":        "vector",
    "one_hop":        "graph",
    "two_hop":        "graph",
    "three_hop":      "graph",
    "multi_entity":   "hybrid",
}


# ── Percentile helper ─────────────────────────────────────────────────────────

def _percentile(data: list[float], p: float) -> float:
    """
    p-th percentile (0–100) via linear interpolation.
    Matches numpy.percentile(data, p, interpolation='linear').
    """
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    if n == 1:
        return s[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


def compute_latency_stats(stage: str, values: list[float]) -> LatencyStats:
    """Aggregate a list of per-question timings into LatencyStats."""
    if not values:
        return LatencyStats(stage=stage, mean_ms=0, min_ms=0, max_ms=0,
                            p50_ms=0, p95_ms=0, p99_ms=0)
    return LatencyStats(
        stage=stage,
        mean_ms=round(statistics.mean(values), 2),
        min_ms=round(min(values), 2),
        max_ms=round(max(values), 2),
        p50_ms=round(_percentile(values, 50), 2),
        p95_ms=round(_percentile(values, 95), 2),
        p99_ms=round(_percentile(values, 99), 2),
    )


# ── BenchmarkRunner ───────────────────────────────────────────────────────────

class BenchmarkRunner:
    """
    Runs the full pipeline stage-by-stage against a list of questions
    and aggregates results into a BenchmarkReport.

    Usage:
        from src.answer.pipeline import AnswerPipeline
        from tests.evaluation.questions import QUESTIONS

        pipeline = AnswerPipeline(...)
        report = BenchmarkRunner(pipeline).run(QUESTIONS)
    """

    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline

    def run(self, questions: list[EvalQuestion]) -> BenchmarkReport:
        """
        Run all questions through the pipeline and return a BenchmarkReport.
        """
        logger.info("Benchmarking %d questions …", len(questions))
        results: list[QuestionBenchmark] = []

        for q in questions:
            result = self._run_one(q)
            results.append(result)
            logger.debug(
                "%s → %s (%.1fms total, conf=%.0f%%)",
                q.qid, result.routed_strategy,
                result.total_ms, 100 * result.citation_confidence,
            )

        return self._aggregate(results)

    def _run_one(self, q: EvalQuestion) -> QuestionBenchmark:
        pipeline = self._pipeline

        # ── Stage 1: Routing ─────────────────────────────────────────────────
        t0 = time.perf_counter()
        decision = pipeline._router.route(q.question)
        routing_ms = (time.perf_counter() - t0) * 1000

        # ── Stage 2: Retrieval ───────────────────────────────────────────────
        t0 = time.perf_counter()
        retrieved = pipeline._retriever_fn(q.question, pipeline._chunks, pipeline._top_k)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        # ── Stage 3: Generation ───────────────────────────────────────────────
        t0 = time.perf_counter()
        raw = pipeline._generator.generate(
            question=q.question,
            chunks=retrieved,
            strategy=decision.strategy,
        )
        generation_ms = (time.perf_counter() - t0) * 1000

        # ── Stage 4: Validation ───────────────────────────────────────────────
        t0 = time.perf_counter()
        validated = pipeline._validator.validate(raw, retrieved)
        validation_ms = (time.perf_counter() - t0) * 1000

        total_ms = routing_ms + retrieval_ms + generation_ms + validation_ms
        expected = _EXPECTED.get(q.question_type, "hybrid")

        return QuestionBenchmark(
            qid=q.qid,
            question=q.question,
            question_type=q.question_type,
            routed_strategy=decision.strategy,
            expected_strategy=expected,
            correct_routing=decision.strategy == expected,
            routing_confidence=decision.confidence,
            routing_ms=round(routing_ms, 3),
            retrieval_ms=round(retrieval_ms, 3),
            generation_ms=round(generation_ms, 3),
            validation_ms=round(validation_ms, 3),
            total_ms=round(total_ms, 3),
            chunk_count=len(retrieved),
            citation_count=len(validated.citations),
            citation_confidence=round(validated.citation_confidence, 4),
            valid_citations=validated.valid_count,
            invalid_citations=validated.invalid_count,
        )

    def _aggregate(self, results: list[QuestionBenchmark]) -> BenchmarkReport:
        pipeline = self._pipeline
        generator_name = type(pipeline._generator).__name__

        # ── Routing accuracy ─────────────────────────────────────────────────
        routing_accuracy = sum(r.correct_routing for r in results) / len(results)

        # ── Citation confidence ──────────────────────────────────────────────
        mean_conf = statistics.mean(r.citation_confidence for r in results)

        # ── Latency stats per stage ──────────────────────────────────────────
        stages = ("routing", "retrieval", "generation", "validation", "total")
        latency: dict[str, LatencyStats] = {}
        for stage in stages:
            field = f"{stage}_ms"
            values = [getattr(r, field) for r in results]
            latency[stage] = compute_latency_stats(stage, values)

        # ── Citation confidence by question type ─────────────────────────────
        by_type: dict[str, list[float]] = defaultdict(list)
        for r in results:
            by_type[r.question_type].append(r.citation_confidence)
        citation_by_type = {t: round(statistics.mean(v), 4) for t, v in by_type.items()}

        # ── Routing accuracy by type ─────────────────────────────────────────
        correct_by_type: dict[str, list[bool]] = defaultdict(list)
        for r in results:
            correct_by_type[r.question_type].append(r.correct_routing)
        routing_by_type = {
            t: round(sum(v) / len(v), 4) for t, v in correct_by_type.items()
        }

        return BenchmarkReport(
            run_at=datetime.now(timezone.utc).isoformat(),
            generator=generator_name,
            question_count=len(results),
            routing_accuracy=round(routing_accuracy, 4),
            mean_citation_confidence=round(mean_conf, 4),
            latency=latency,
            citation_by_type=citation_by_type,
            routing_by_type=routing_by_type,
            per_question=results,
        )
