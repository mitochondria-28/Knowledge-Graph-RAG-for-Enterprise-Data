"""
Data models for Phase 10 benchmarking.

DESIGN RATIONALE:

QuestionBenchmark — one record per question.
  Stores both the raw timings and derived quality metrics so the report
  can be regenerated from the JSON file without re-running the pipeline.

LatencyStats — aggregated latency for one pipeline stage.
  p50/p95/p99 catch long-tail behaviour that mean/max hide.
  With 20 questions the p99 = max, but the structure is right for
  larger runs.

BenchmarkReport — the full run output.
  Serialisable to JSON (via dataclasses.asdict) so reports can be
  diffed across git commits or pipeline configurations.
"""

from dataclasses import dataclass, field


@dataclass
class QuestionBenchmark:
    """Per-question benchmark result."""
    qid: str
    question: str
    question_type: str

    # Routing
    routed_strategy: str
    expected_strategy: str
    correct_routing: bool
    routing_confidence: float

    # Latency (ms) per stage
    routing_ms: float
    retrieval_ms: float
    generation_ms: float
    validation_ms: float
    total_ms: float

    # Retrieval
    chunk_count: int

    # Citation quality
    citation_count: int
    citation_confidence: float
    valid_citations: int
    invalid_citations: int


@dataclass
class LatencyStats:
    """Percentile summary for one pipeline stage across all questions."""
    stage: str
    mean_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass
class BenchmarkReport:
    """Full benchmark run result — serialisable to JSON."""
    run_at: str                                      # ISO-8601 timestamp
    generator: str                                   # class name
    question_count: int
    routing_accuracy: float                          # correct / total
    mean_citation_confidence: float
    latency: dict[str, LatencyStats] = field(default_factory=dict)
    citation_by_type: dict[str, float] = field(default_factory=dict)
    routing_by_type: dict[str, float] = field(default_factory=dict)
    per_question: list[QuestionBenchmark] = field(default_factory=list)
