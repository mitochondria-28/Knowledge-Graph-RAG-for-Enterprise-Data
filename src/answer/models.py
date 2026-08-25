"""
Data models for Phase 8 — Answer Generation + Citation Validation.

DESIGN NOTES:

RawAnswer  — what comes directly from the LLM (tool-use output, unvalidated)
ValidatedAnswer — RawAnswer after CitationValidator has checked every citation

Keeping them separate makes the validation step explicit and testable.
Citations can be in one of three states after validation:
  VALID     — quote found in chunk (exact or fuzzy ≥ threshold)
  INVALID   — quote not found, or chunk_id wasn't retrieved (hallucinated ref)
  UNCHECKED — not yet validated (only appears on RawAnswer)

citation_confidence on ValidatedAnswer is valid_count / total_citations,
not the LLM's self-reported confidence (which is informational only).
"""

from dataclasses import dataclass, field


@dataclass
class Citation:
    """A single citation produced by the LLM."""
    chunk_id: str
    source_file: str
    quote: str   # short verbatim phrase from the chunk


@dataclass
class RawAnswer:
    """Structured answer returned by AnswerGenerator — citations not yet verified."""
    question: str
    answer_text: str
    citations: list[Citation]
    model: str
    latency_ms: float
    retrieval_strategy: str
    chunk_count: int              # number of chunks provided as context
    llm_confidence: float = 0.0   # LLM's self-reported confidence (informational)


@dataclass
class ValidationResult:
    """Result of validating one Citation against its source chunk."""
    chunk_id: str
    quote: str
    source_file: str
    is_valid: bool
    match_score: float          # 0.0–1.0 (1.0 = exact, <1.0 = fuzzy)
    matched_text: str | None    # actual text found in chunk (None for fuzzy / invalid)
    reason: str                 # human-readable explanation


@dataclass
class ValidatedAnswer:
    """
    Final answer with all citations checked against chunk content.

    Use citation_confidence (not llm_confidence) to decide whether
    the answer is trustworthy enough to show the user.
    """
    question: str
    answer_text: str
    citations: list[Citation]
    validation_results: list[ValidationResult]
    retrieval_strategy: str
    model: str
    latency_ms: float
    llm_confidence: float = 0.0
    chunk_count: int = 0

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.validation_results if r.is_valid)

    @property
    def invalid_count(self) -> int:
        return sum(1 for r in self.validation_results if not r.is_valid)

    @property
    def citation_confidence(self) -> float:
        """Fraction of citations that could be verified in source chunks."""
        if not self.validation_results:
            return 0.0
        return self.valid_count / len(self.validation_results)
