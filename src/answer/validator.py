"""
Citation validator — Phase 8.

WHY VALIDATE CITATIONS:

LLMs hallucinate. Even with tool-use forcing structured output, Claude might:
  1. Invent a chunk_id that wasn't in the retrieved set
  2. Quote a phrase that never appeared in the cited chunk
  3. Paraphrase instead of quoting verbatim (quote won't match)

Citation validation catches all three cases by checking each (chunk_id, quote)
pair against the actual retrieved chunk content.

VALIDATION ALGORITHM:

For each citation:
  1. chunk_id lookup — is the chunk_id in the set we actually retrieved?
     If not → INVALID ("hallucinated reference")

  2. Exact substring match (case-insensitive)
     If the quote is a verbatim substring of the chunk content → VALID (score=1.0)

  3. Fuzzy partial match via rapidfuzz.fuzz.partial_ratio
     partial_ratio finds the best-matching substring window.
     If score ≥ fuzzy_threshold (default 0.80) → VALID

     This handles minor punctuation / whitespace differences while still
     rejecting paraphrased or fabricated quotes.

  4. None of the above → INVALID with match_score and reason

WHY partial_ratio INSTEAD OF ratio:

ratio() compares the full strings — a short quote vs. a 500-token chunk
will always score low even if the quote appears verbatim.

partial_ratio() slides a window of the shorter string over the longer one
and takes the best match, which is exactly what we want: "does this phrase
appear anywhere in the chunk?"

THRESHOLD CHOICE (0.80):

Allows for minor OCR / encoding differences and sentence boundary variation
while firmly rejecting fabricated content. Empirically validated against
the TechNova corpus.
"""

import logging

from rapidfuzz import fuzz

from src.answer.models import Citation, RawAnswer, ValidatedAnswer, ValidationResult

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.80


class CitationValidator:
    """
    Validates each citation in a RawAnswer against the retrieved chunks.

    Args:
        fuzzy_threshold: Minimum partial_ratio score (0.0–1.0) to accept
                         a fuzzy match. Default: 0.80.
    """

    def __init__(self, fuzzy_threshold: float = _DEFAULT_THRESHOLD) -> None:
        if not 0.0 < fuzzy_threshold <= 1.0:
            raise ValueError(f"fuzzy_threshold must be in (0, 1], got {fuzzy_threshold}")
        self._threshold = fuzzy_threshold

    def validate(
        self,
        raw_answer: RawAnswer,
        chunks: list[dict],
    ) -> ValidatedAnswer:
        """
        Check every citation in raw_answer against chunk content.

        Args:
            raw_answer: Output from AnswerGenerator (unvalidated citations).
            chunks:     The chunks that were retrieved and passed to the generator.
                        Only chunk_ids present here are considered valid references.

        Returns:
            ValidatedAnswer with per-citation ValidationResult objects.
        """
        chunk_map: dict[str, dict] = {c["chunk_id"]: c for c in chunks}

        results: list[ValidationResult] = [
            self._validate_one(citation, chunk_map)
            for citation in raw_answer.citations
        ]

        if results:
            n_valid = sum(1 for r in results if r.is_valid)
            logger.debug(
                "Citation validation: %d/%d valid (%.0f%%)",
                n_valid, len(results), 100 * n_valid / len(results),
            )

        return ValidatedAnswer(
            question=raw_answer.question,
            answer_text=raw_answer.answer_text,
            citations=raw_answer.citations,
            validation_results=results,
            retrieval_strategy=raw_answer.retrieval_strategy,
            model=raw_answer.model,
            latency_ms=raw_answer.latency_ms,
            llm_confidence=raw_answer.llm_confidence,
            chunk_count=raw_answer.chunk_count,
        )

    def _validate_one(
        self,
        citation: Citation,
        chunk_map: dict[str, dict],
    ) -> ValidationResult:
        # ── Step 1: chunk_id must be in the retrieved set ────────────────────
        if citation.chunk_id not in chunk_map:
            return ValidationResult(
                chunk_id=citation.chunk_id,
                quote=citation.quote,
                source_file="UNKNOWN",
                is_valid=False,
                match_score=0.0,
                matched_text=None,
                reason=(
                    f"chunk_id '{citation.chunk_id}' was not in the retrieved set — "
                    "possible hallucinated reference"
                ),
            )

        chunk = chunk_map[citation.chunk_id]
        content: str = chunk["content"]
        source_file: str = chunk.get("source_file", "unknown")

        quote = citation.quote.strip()
        if not quote:
            return ValidationResult(
                chunk_id=citation.chunk_id,
                quote=citation.quote,
                source_file=source_file,
                is_valid=False,
                match_score=0.0,
                matched_text=None,
                reason="empty quote — nothing to verify",
            )

        quote_lower = quote.lower()
        content_lower = content.lower()

        # ── Step 2: exact substring match ────────────────────────────────────
        if quote_lower in content_lower:
            idx = content_lower.index(quote_lower)
            matched = content[idx: idx + len(quote)]
            return ValidationResult(
                chunk_id=citation.chunk_id,
                quote=citation.quote,
                source_file=source_file,
                is_valid=True,
                match_score=1.0,
                matched_text=matched,
                reason="exact match",
            )

        # ── Step 3: fuzzy partial match ───────────────────────────────────────
        score = fuzz.partial_ratio(quote_lower, content_lower) / 100.0
        if score >= self._threshold:
            return ValidationResult(
                chunk_id=citation.chunk_id,
                quote=citation.quote,
                source_file=source_file,
                is_valid=True,
                match_score=round(score, 3),
                matched_text=None,
                reason=f"fuzzy match ({score:.0%})",
            )

        # ── Step 4: not found ─────────────────────────────────────────────────
        return ValidationResult(
            chunk_id=citation.chunk_id,
            quote=citation.quote,
            source_file=source_file,
            is_valid=False,
            match_score=round(score, 3),
            matched_text=None,
            reason=(
                f"quote not verifiable in chunk "
                f"(best fuzzy match: {score:.0%}, threshold: {self._threshold:.0%})"
            ),
        )
