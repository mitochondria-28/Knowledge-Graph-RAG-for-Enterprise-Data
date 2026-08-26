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

By default, MockAnswerGenerator is used (no API key needed). To use Claude:

    import anthropic
    from src.answer.generator import AnswerGenerator

    pipeline = AnswerPipeline(
        generator=AnswerGenerator(anthropic.Anthropic()),
    )
"""

import json
import logging
from pathlib import Path
from typing import Callable

from src.config import settings
from src.answer.generator import MockAnswerGenerator
from src.answer.models import ValidatedAnswer
from src.answer.validator import CitationValidator
from src.router.pipeline import QuestionRouter, load_entity_index

logger = logging.getLogger(__name__)

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
      - Pass AnswerGenerator(anthropic.Anthropic()) for real Claude answers
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

        # 1. Route
        decision = self._router.route(question)
        logger.info(
            "Routed '%s...' → strategy=%s hop_depth=%d confidence=%.2f",
            question[:60], decision.strategy, decision.hop_depth, decision.confidence,
        )

        # 2. Retrieve
        retrieved = self._retriever_fn(question, self._chunks, k)
        logger.info("Retrieved %d chunks", len(retrieved))

        # 3. Generate (with routing decision as strategy label)
        raw_answer = self._generator.generate(
            question=question,
            chunks=retrieved,
            strategy=decision.strategy,
        )

        # 4. Validate citations
        validated = self._validator.validate(raw_answer, retrieved)
        logger.info(
            "Citation confidence: %.0f%% (%d/%d valid)",
            100 * validated.citation_confidence,
            validated.valid_count,
            len(validated.validation_results),
        )

        return validated
