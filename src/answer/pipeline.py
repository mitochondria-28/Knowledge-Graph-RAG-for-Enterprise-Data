"""
Answer pipeline — Phase 8.

ORCHESTRATION:

  1. Route     — QuestionRouter classifies question → strategy + hop_depth
  2. Retrieve  — fetch relevant chunks (keyword by default, swappable)
  3. Generate  — AnswerGenerator calls Claude with chunk context
  4. Validate  — CitationValidator checks every citation against chunk content

RETRIEVAL WITHOUT LIVE DATABASES:

This pipeline ships with a built-in keyword retriever so it works without
Neo4j or PostgreSQL. To use real vector or graph retrieval, pass a custom
retriever_fn:

    from src.vector.store import search_similar
    pipeline = AnswerPipeline(
        retriever_fn=lambda q, chunks, k: my_vector_retrieve(q, k),
        ...
    )

RETRIEVER INTERFACE:

    retriever_fn(question: str, chunks: list[dict], top_k: int) -> list[dict]

Returns a ranked list of chunk dicts (may be a subset of all_chunks).

SWAPPING THE GENERATOR:

By default, MockAnswerGenerator is used (no API key needed). To use Gemini:

    from src.answer.generator import make_generator

    pipeline = AnswerPipeline(
        generator=make_generator(api_key="YOUR_GEMINI_API_KEY"),
    )

OBSERVABILITY (Phase 11):

Every ask() call emits:
  - OpenTelemetry spans: ask / route / retrieve / generate / validate
  - Prometheus histograms: kg_rag_pipeline_stage_duration_seconds (per stage)
                           kg_rag_pipeline_total_duration_seconds  (end-to-end)
  - Prometheus histogram:  kg_rag_citation_confidence
  - Structured log lines at INFO level for each stage
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable

from src.config import settings
from src.answer.generator import MockAnswerGenerator
from src.answer.models import ValidatedAnswer
from src.answer.validator import CitationValidator
from src.observability.metrics import (
    CITATION_CONFIDENCE,
    PIPELINE_STAGE_DURATION,
    PIPELINE_TOTAL_DURATION,
)
from src.observability.tracing import get_tracer
from src.router.pipeline import QuestionRouter, load_entity_index

logger = logging.getLogger(__name__)

def _get_tracer():
    return get_tracer(__name__)

# ── Type alias ────────────────────────────────────────────────────────────────
RetrieverFn = Callable[[str, list[dict], int], list[dict]]

# ── Stopwords for the built-in keyword retriever ──────────────────────────────
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "and", "or", "but", "if",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "what", "which", "who", "whom", "this", "that",
    "these", "those", "how", "when", "where", "why", "than", "then",
    "not", "only", "its", "their", "his", "her", "it", "he", "she",
    "they", "we", "you", "i", "me", "my", "your", "our",
})


def _keyword_retrieve(question: str, chunks: list[dict], top_k: int) -> list[dict]:
    """
    Lightweight keyword retriever — no database, no model, no API key.

    Scores by token overlap (question tokens ∩ chunk tokens, stopwords removed).
    Falls back to first top_k chunks if no tokens match anything.
    """
    q_tokens = {t for t in question.lower().split() if t not in _STOPWORDS}
    if not q_tokens:
        return chunks[:top_k]

    scored: list[tuple[int, int, dict]] = []
    for chunk in chunks:
        c_tokens = {t for t in chunk["content"].lower().split() if t not in _STOPWORDS}
        overlap = len(q_tokens & c_tokens)
        scored.append((overlap, -chunk.get("chunk_index", 0), chunk))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    matched = [c for score, _, c in scored[:top_k] if score > 0]
    return matched if matched else chunks[:top_k]


def load_chunks(chunks_file: Path | None = None) -> list[dict]:
    """Load all chunks from all_chunks.json (Phase 1 output)."""
    path = chunks_file or (settings.output_dir / "all_chunks.json")
    if not path.exists():
        logger.warning("Chunk file not found at %s — retrieval will be empty", path)
        return []
    chunks = json.loads(path.read_text(encoding="utf-8"))
    logger.debug("Loaded %d chunks from %s", len(chunks), path)
    return chunks


class AnswerPipeline:
    """
    End-to-end Q&A pipeline: route → retrieve → generate → validate.

    Works out-of-the-box without any running databases:
      - Keyword retrieval (no DB)
      - MockAnswerGenerator (no API key)

    Production upgrade:
      - Pass make_generator(api_key=...) for real Gemini answers
      - Pass a custom retriever_fn for vector or graph retrieval
    """

    def __init__(
        self,
        *,
        generator=None,
        validator: CitationValidator | None = None,
        retriever_fn: RetrieverFn | None = None,
        chunks: list[dict] | None = None,
        entity_index: dict[str, str] | None = None,
        top_k: int = 5,
    ) -> None:
        self._generator = generator or MockAnswerGenerator()
        self._validator = validator or CitationValidator()
        self._retriever_fn = retriever_fn or _keyword_retrieve
        self._chunks = chunks if chunks is not None else load_chunks()
        self._router = QuestionRouter(entity_index or load_entity_index())
        self._top_k = top_k

    def ask(self, question: str, top_k: int | None = None) -> ValidatedAnswer:
        """
        Full pipeline for a single question.

        Args:
            question: Natural-language question string.
            top_k:    Number of chunks to retrieve; overrides the instance default.

        Returns:
            ValidatedAnswer with answer, citations, and validation status.
        """
        k = top_k if top_k is not None else self._top_k
        pipeline_start = time.perf_counter()

        with _get_tracer().start_as_current_span("ask") as root_span:
            root_span.set_attribute("question.length", len(question))
            root_span.set_attribute("top_k", k)

            # 1. Route
            _tracer = _get_tracer()
            with _tracer.start_as_current_span("route") as span:
                t0 = time.perf_counter()
                decision = self._router.route(question)
                route_s = time.perf_counter() - t0
                span.set_attribute("strategy", decision.strategy)
                span.set_attribute("hop_depth", decision.hop_depth)
                span.set_attribute("confidence", decision.confidence)

            PIPELINE_STAGE_DURATION.labels(stage="route").observe(route_s)
            logger.info(
                "Routed question",
                extra={
                    "stage": "route",
                    "strategy": decision.strategy,
                    "hop_depth": decision.hop_depth,
                    "confidence": round(decision.confidence, 3),
                    "duration_ms": round(route_s * 1000, 2),
                },
            )

            # 2. Retrieve
            with _tracer.start_as_current_span("retrieve") as span:
                t0 = time.perf_counter()
                retrieved = self._retriever_fn(question, self._chunks, k)
                retrieve_s = time.perf_counter() - t0
                span.set_attribute("chunk_count", len(retrieved))

            PIPELINE_STAGE_DURATION.labels(stage="retrieve").observe(retrieve_s)
            logger.info(
                "Retrieved chunks",
                extra={
                    "stage": "retrieve",
                    "chunk_count": len(retrieved),
                    "duration_ms": round(retrieve_s * 1000, 2),
                },
            )

            # 3. Generate
            with _tracer.start_as_current_span("generate") as span:
                t0 = time.perf_counter()
                raw_answer = self._generator.generate(
                    question=question,
                    chunks=retrieved,
                    strategy=decision.strategy,
                )
                generate_s = time.perf_counter() - t0
                span.set_attribute("model", raw_answer.model)
                span.set_attribute("citation_count", len(raw_answer.citations))

            PIPELINE_STAGE_DURATION.labels(stage="generate").observe(generate_s)
            logger.info(
                "Generated answer",
                extra={
                    "stage": "generate",
                    "model": raw_answer.model,
                    "citation_count": len(raw_answer.citations),
                    "duration_ms": round(generate_s * 1000, 2),
                },
            )

            # 4. Validate citations
            with _tracer.start_as_current_span("validate") as span:
                t0 = time.perf_counter()
                validated = self._validator.validate(raw_answer, retrieved)
                validate_s = time.perf_counter() - t0
                span.set_attribute("valid_citations", validated.valid_count)
                span.set_attribute("invalid_citations", validated.invalid_count)
                span.set_attribute("citation_confidence", validated.citation_confidence)

            PIPELINE_STAGE_DURATION.labels(stage="validate").observe(validate_s)
            logger.info(
                "Validated citations",
                extra={
                    "stage": "validate",
                    "valid": validated.valid_count,
                    "invalid": validated.invalid_count,
                    "citation_confidence": round(validated.citation_confidence, 3),
                    "duration_ms": round(validate_s * 1000, 2),
                },
            )

            # End-to-end metrics
            total_s = time.perf_counter() - pipeline_start
            PIPELINE_TOTAL_DURATION.observe(total_s)
            CITATION_CONFIDENCE.observe(validated.citation_confidence)
            root_span.set_attribute("citation_confidence", validated.citation_confidence)
            root_span.set_attribute("strategy", decision.strategy)

        return validated
