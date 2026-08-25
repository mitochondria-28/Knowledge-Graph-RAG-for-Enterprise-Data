"""
Data models for the retrieval evaluation framework.

GROUND-TRUTH DESIGN:

Questions define relevance by source file, not chunk ID. Chunk IDs are
UUID5(doc_hash:chunk_index) — they change when content changes, so hardcoding
them in a test suite creates brittle tests. Source files are stable.

The harness resolves source_file → chunk_ids at runtime from all_chunks.json,
making the evaluation portable across re-ingestion runs.

QUESTION TYPES:

  simple_entity   — "What is StellarDB?" — answer lives in one document
  factual         — "When did TechNova acquire Stellar Systems?" — exact fact retrieval
  one_hop         — requires traversing one relationship in the graph
  two_hop         — requires traversing two relationships
  three_hop       — requires traversing three relationships
  multi_entity    — answer spans multiple entities / documents

This taxonomy predicts retriever advantage:
  vector wins     → simple_entity, factual
  graph wins      → one_hop, two_hop, three_hop
  both needed     → multi_entity
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalQuestion:
    qid: str                          # "q01" … "q20"
    question: str                     # natural language question
    question_type: str                # see taxonomy above
    relevant_sources: list[str]       # source_file values containing the answer
    expected_entities: list[str]      # canonical entity names for graph retrieval
    notes: str = ""                   # why this question is interesting / hard


@dataclass
class RetrievalResult:
    qid: str
    retriever: str                    # "keyword", "vector", "graph"
    retrieved_chunk_ids: list[str]    # ranked, position 0 = top result
    latency_ms: float = 0.0


@dataclass
class QuestionScore:
    qid: str
    question: str
    question_type: str
    retriever: str
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    mrr: float                        # mean reciprocal rank (0–1)
    retrieved_count: int
    relevant_count: int
    k: int


@dataclass
class EvalReport:
    retriever: str
    k: int
    scores: list[QuestionScore]
    # Macro-averaged (unweighted mean across questions)
    macro_precision: float
    macro_recall: float
    macro_f1: float
    macro_mrr: float
    # Per-type breakdown: question_type → {metric: value}
    by_type: dict[str, dict[str, float]] = field(default_factory=dict)

    def summary_row(self) -> dict[str, str]:
        return {
            "retriever":  self.retriever,
            "P@k":        f"{self.macro_precision:.3f}",
            "R@k":        f"{self.macro_recall:.3f}",
            "F1@k":       f"{self.macro_f1:.3f}",
            "MRR":        f"{self.macro_mrr:.3f}",
        }
