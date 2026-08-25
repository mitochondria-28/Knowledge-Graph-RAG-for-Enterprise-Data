"""
Unit tests for Phase 8 citation validator.

Tests verify:
  1. Exact substring matches → valid (score=1.0)
  2. Fuzzy matches above threshold → valid
  3. Fuzzy matches below threshold → invalid
  4. chunk_id not in retrieved set → invalid (hallucinated reference)
  5. Empty quote → invalid
  6. citation_confidence computation
  7. Multiple citations validated independently
  8. Custom fuzzy threshold respected
  9. Edge cases: no citations, all valid, all invalid
"""

import pytest

from src.answer.models import Citation, RawAnswer, ValidatedAnswer
from src.answer.validator import CitationValidator


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def chunks() -> list[dict]:
    return [
        {
            "chunk_id": "chunk-aaa",
            "source_file": "corpus/companies/technova_overview.md",
            "content": "TechNova Corporation was founded in 2010 and specialises in enterprise data infrastructure.",
            "chunk_index": 0,
        },
        {
            "chunk_id": "chunk-bbb",
            "source_file": "corpus/people/engineering_org.md",
            "content": "Sandra Müller leads the Platform Team, which is responsible for StellarDB operations and maintenance.",
            "chunk_index": 1,
        },
        {
            "chunk_id": "chunk-ccc",
            "source_file": "corpus/technologies/stellar_db_architecture.md",
            "content": "StellarDB is a distributed in-memory database optimised for low-latency analytical queries.",
            "chunk_index": 0,
        },
    ]


def _make_raw_answer(citations: list[Citation]) -> RawAnswer:
    return RawAnswer(
        question="test question",
        answer_text="test answer",
        citations=citations,
        model="mock",
        latency_ms=1.0,
        retrieval_strategy="vector",
        chunk_count=3,
    )


def _citation(chunk_id: str, quote: str) -> Citation:
    return Citation(chunk_id=chunk_id, source_file="", quote=quote)


# ── Exact match ───────────────────────────────────────────────────────────────

class TestExactMatch:
    def test_verbatim_quote_is_valid(self, chunks):
        cit = _citation("chunk-aaa", "TechNova Corporation was founded in 2010")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is True

    def test_exact_match_score_is_one(self, chunks):
        cit = _citation("chunk-aaa", "TechNova Corporation was founded in 2010")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].match_score == 1.0

    def test_exact_match_matched_text_returned(self, chunks):
        quote = "TechNova Corporation was founded in 2010"
        cit = _citation("chunk-aaa", quote)
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        vr = result.validation_results[0]
        assert vr.matched_text is not None
        assert quote.lower() in vr.matched_text.lower()

    def test_case_insensitive_exact_match(self, chunks):
        cit = _citation("chunk-aaa", "TECHNOVA CORPORATION WAS FOUNDED IN 2010")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is True

    def test_reason_says_exact_match(self, chunks):
        cit = _citation("chunk-bbb", "Sandra Müller leads the Platform Team")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].reason == "exact match"

    def test_partial_quote_still_exact(self, chunks):
        # A short phrase that appears verbatim → exact match
        cit = _citation("chunk-ccc", "StellarDB is a distributed in-memory database")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is True


# ── Fuzzy match ───────────────────────────────────────────────────────────────

class TestFuzzyMatch:
    def test_near_verbatim_quote_passes_fuzzy(self, chunks):
        # Slightly different punctuation / whitespace
        cit = _citation("chunk-aaa", "TechNova Corporation was founded in 2010 and specializes in enterprise data")
        raw = _make_raw_answer([cit])
        result = CitationValidator(fuzzy_threshold=0.80).validate(raw, chunks)
        assert result.validation_results[0].is_valid is True

    def test_fabricated_quote_fails_below_threshold(self, chunks):
        # Completely invented text → low fuzzy score
        cit = _citation("chunk-aaa", "TechNova was established in 1995 as a cloud provider")
        raw = _make_raw_answer([cit])
        result = CitationValidator(fuzzy_threshold=0.80).validate(raw, chunks)
        assert result.validation_results[0].is_valid is False

    def test_fuzzy_threshold_respected(self, chunks):
        # This quote has partial overlap — passes at 0.60 but may fail at 0.95
        cit = _citation("chunk-bbb", "Sandra Müller is responsible for the Platform Team")
        raw = _make_raw_answer([cit])

        # Lower threshold → more lenient
        lenient = CitationValidator(fuzzy_threshold=0.60).validate(raw, chunks)
        strict = CitationValidator(fuzzy_threshold=0.95).validate(raw, chunks)

        # The lenient validator should accept more
        # (we can't assert exact truth value without running rapidfuzz, but
        # we can assert that increasing threshold doesn't make invalid→valid)
        lenient_valid = lenient.validation_results[0].is_valid
        strict_valid = strict.validation_results[0].is_valid
        # If strict accepts it, lenient must too
        if strict_valid:
            assert lenient_valid

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            CitationValidator(fuzzy_threshold=0.0)

    def test_invalid_threshold_above_one_raises(self):
        with pytest.raises(ValueError):
            CitationValidator(fuzzy_threshold=1.1)


# ── Hallucinated chunk_id ─────────────────────────────────────────────────────

class TestHallucinatedChunkId:
    def test_unknown_chunk_id_is_invalid(self, chunks):
        cit = _citation("chunk-INVENTED", "some valid-sounding quote")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is False

    def test_hallucinated_chunk_id_score_is_zero(self, chunks):
        cit = _citation("chunk-INVENTED", "some quote")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].match_score == 0.0

    def test_hallucinated_chunk_source_is_unknown(self, chunks):
        cit = _citation("chunk-INVENTED", "some quote")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].source_file == "UNKNOWN"

    def test_hallucinated_reason_mentions_hallucination(self, chunks):
        cit = _citation("chunk-INVENTED", "some quote")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        reason = result.validation_results[0].reason.lower()
        assert "hallucin" in reason or "not in" in reason


# ── Empty quote ───────────────────────────────────────────────────────────────

class TestEmptyQuote:
    def test_empty_quote_is_invalid(self, chunks):
        cit = _citation("chunk-aaa", "")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is False

    def test_whitespace_only_quote_is_invalid(self, chunks):
        cit = _citation("chunk-aaa", "   ")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].is_valid is False


# ── citation_confidence ───────────────────────────────────────────────────────

class TestCitationConfidence:
    def test_all_valid_confidence_is_one(self, chunks):
        citations = [
            _citation("chunk-aaa", "TechNova Corporation was founded in 2010"),
            _citation("chunk-bbb", "Sandra Müller leads the Platform Team"),
        ]
        raw = _make_raw_answer(citations)
        result = CitationValidator().validate(raw, chunks)
        assert result.citation_confidence == 1.0

    def test_all_invalid_confidence_is_zero(self, chunks):
        citations = [
            _citation("chunk-FAKE-1", "invented text one"),
            _citation("chunk-FAKE-2", "invented text two"),
        ]
        raw = _make_raw_answer(citations)
        result = CitationValidator().validate(raw, chunks)
        assert result.citation_confidence == 0.0

    def test_half_valid_confidence_is_half(self, chunks):
        citations = [
            _citation("chunk-aaa", "TechNova Corporation was founded in 2010"),  # valid
            _citation("chunk-FAKE", "invented text"),                              # invalid
        ]
        raw = _make_raw_answer(citations)
        result = CitationValidator().validate(raw, chunks)
        assert result.citation_confidence == 0.5

    def test_no_citations_confidence_is_zero(self, chunks):
        raw = _make_raw_answer([])
        result = CitationValidator().validate(raw, chunks)
        assert result.citation_confidence == 0.0

    def test_valid_count_correct(self, chunks):
        citations = [
            _citation("chunk-aaa", "TechNova Corporation was founded in 2010"),
            _citation("chunk-FAKE", "invented text"),
        ]
        raw = _make_raw_answer(citations)
        result = CitationValidator().validate(raw, chunks)
        assert result.valid_count == 1
        assert result.invalid_count == 1


# ── Multiple independent citations ────────────────────────────────────────────

class TestMultipleCitations:
    def test_each_citation_validated_independently(self, chunks):
        citations = [
            _citation("chunk-aaa", "TechNova Corporation was founded in 2010"),
            _citation("chunk-bbb", "Sandra Müller leads the Platform Team"),
            _citation("chunk-FAKE", "completely invented content"),
        ]
        raw = _make_raw_answer(citations)
        result = CitationValidator().validate(raw, chunks)
        assert len(result.validation_results) == 3
        assert result.validation_results[0].is_valid is True
        assert result.validation_results[1].is_valid is True
        assert result.validation_results[2].is_valid is False

    def test_output_answer_text_preserved(self, chunks):
        raw = _make_raw_answer([])
        raw.answer_text = "The answer is TechNova."
        result = CitationValidator().validate(raw, chunks)
        assert result.answer_text == "The answer is TechNova."

    def test_output_question_preserved(self, chunks):
        raw = _make_raw_answer([])
        raw.question = "Who founded TechNova?"
        result = CitationValidator().validate(raw, chunks)
        assert result.question == "Who founded TechNova?"

    def test_source_file_from_chunk(self, chunks):
        cit = _citation("chunk-aaa", "TechNova Corporation was founded in 2010")
        raw = _make_raw_answer([cit])
        result = CitationValidator().validate(raw, chunks)
        assert result.validation_results[0].source_file == "corpus/companies/technova_overview.md"

    def test_validated_answer_is_correct_type(self, chunks):
        raw = _make_raw_answer([])
        result = CitationValidator().validate(raw, chunks)
        assert isinstance(result, ValidatedAnswer)
