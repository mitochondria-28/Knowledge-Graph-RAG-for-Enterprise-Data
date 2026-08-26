"""
Property-based tests — Phase 12.

WHY PROPERTY-BASED TESTING:

Unit tests check specific examples. Property-based tests (Hypothesis) generate
hundreds of random inputs and verify invariants that must hold for ALL inputs:

  "The router never crashes, regardless of input string"
  "Citation confidence is always in [0, 1]"
  "The keyword retriever never returns more than top_k chunks"

These catch bugs that specific examples miss — edge cases in Unicode handling,
empty strings, very long inputs, strings that look like regex metacharacters, etc.

HYPOTHESIS SETTINGS:

@settings(max_examples=200) runs 200 examples per test.
@settings(suppress_health_check=[HealthCheck.too_slow]) lets slow tests pass in CI.

In local dev, set HYPOTHESIS_DATABASE_DIRECTORY=.hypothesis to persist the
example database and replay past failures.
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


# ── Shared corpus for property tests (module-level, built once) ───────────────

def _make_chunk(i: int, content: str = "") -> dict:
    return {
        "chunk_id": f"prop-{i:04d}",
        "document_id": f"doc-{i}",
        "source_file": f"corpus/prop_{i}.md",
        "section": "Section",
        "chunk_index": i,
        "content": content or f"TechNova Corporation. StellarDB. Block {i}.",
        "token_count": 10,
    }


_CHUNKS = [_make_chunk(i) for i in range(20)]
_ENTITY_INDEX = {
    "TechNova Corporation": "Company",
    "TechNova": "Company",
    "StellarDB": "Technology",
    "Platform Team": "Team",
}


# ── Router: never crashes ─────────────────────────────────────────────────────

class TestRouterProperties:
    @pytest.fixture(scope="class")
    def router(self):
        from src.router.pipeline import QuestionRouter
        return QuestionRouter(_ENTITY_INDEX)

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_router_never_crashes(self, router, question):
        """Router must return a RoutingDecision for any non-empty string."""
        decision = router.route(question)
        assert decision is not None

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_strategy_always_valid(self, router, question):
        """Strategy is always one of the three known values."""
        decision = router.route(question)
        assert decision.strategy in ("vector", "graph", "hybrid")

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_confidence_in_range(self, router, question):
        """Confidence is always in [0, 1]."""
        decision = router.route(question)
        assert 0.0 <= decision.confidence <= 1.0

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_hop_depth_non_negative(self, router, question):
        """hop_depth is always ≥ 0."""
        decision = router.route(question)
        assert decision.hop_depth >= 0

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_router_is_deterministic(self, router, question):
        """Same question → same strategy every time."""
        d1 = router.route(question)
        d2 = router.route(question)
        assert d1.strategy == d2.strategy

    @given(question=st.from_regex(r"[A-Za-z ]{1,100}", fullmatch=True))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alphabetic_questions_route(self, router, question):
        """ASCII-only questions always get a valid routing decision."""
        decision = router.route(question)
        assert decision.strategy in ("vector", "graph", "hybrid")


# ── Keyword retriever: invariants ─────────────────────────────────────────────

class TestRetrieverProperties:
    @given(
        question=st.text(min_size=1, max_size=300),
        top_k=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_never_exceeds_top_k(self, question, top_k):
        """Retriever must never return more than top_k chunks."""
        from src.answer.pipeline import _keyword_retrieve
        result = _keyword_retrieve(question, _CHUNKS, top_k)
        assert len(result) <= top_k

    @given(question=st.text(min_size=1, max_size=300))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_returns_list(self, question):
        """Return type is always list."""
        from src.answer.pipeline import _keyword_retrieve
        result = _keyword_retrieve(question, _CHUNKS, 5)
        assert isinstance(result, list)

    @given(question=st.text(min_size=1, max_size=300))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_empty_corpus_returns_empty(self, question):
        """Empty corpus → empty result, no crash."""
        from src.answer.pipeline import _keyword_retrieve
        result = _keyword_retrieve(question, [], 5)
        assert result == []

    @given(question=st.text(min_size=1, max_size=300))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_never_crashes(self, question):
        """Retriever never raises an exception for any string input."""
        from src.answer.pipeline import _keyword_retrieve
        result = _keyword_retrieve(question, _CHUNKS, 5)
        assert result is not None

    @given(question=st.text(min_size=1, max_size=300))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_all_returned_chunks_are_from_input(self, question):
        """Every returned chunk must be from the original input list."""
        from src.answer.pipeline import _keyword_retrieve
        result = _keyword_retrieve(question, _CHUNKS, 5)
        chunk_ids = {c["chunk_id"] for c in _CHUNKS}
        for chunk in result:
            assert chunk["chunk_id"] in chunk_ids


# ── CitationValidator: invariants ─────────────────────────────────────────────

def _make_citation(chunk_id: str, quote: str):
    from src.answer.models import Citation
    return Citation(chunk_id=chunk_id, source_file="corpus/test.md", quote=quote)


class TestValidatorProperties:
    @pytest.fixture(scope="class")
    def validator(self):
        from src.answer.validator import CitationValidator
        return CitationValidator(fuzzy_threshold=0.80)

    @given(
        quote=st.text(min_size=0, max_size=200),
        content=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_validate_one_never_crashes(self, validator, quote, content):
        """_validate_one must not raise for any (quote, content) pair."""
        chunk = _make_chunk(0, content)
        citation = _make_citation(chunk["chunk_id"], quote)
        result = validator._validate_one(citation, {chunk["chunk_id"]: chunk})
        assert result is not None

    @given(
        quote=st.text(min_size=0, max_size=200),
        content=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_match_score_in_range(self, validator, quote, content):
        """match_score is always in [0, 1]."""
        chunk = _make_chunk(0, content)
        citation = _make_citation(chunk["chunk_id"], quote)
        result = validator._validate_one(citation, {chunk["chunk_id"]: chunk})
        assert 0.0 <= result.match_score <= 1.0

    @given(content=st.text(min_size=10, max_size=200))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_exact_substring_always_valid(self, validator, content):
        """A non-empty substring quote of the chunk content must pass."""
        quote = content[:30].strip()
        if not quote:
            return  # skip whitespace-only slices
        chunk = _make_chunk(0, content)
        citation = _make_citation(chunk["chunk_id"], quote)
        result = validator._validate_one(citation, {chunk["chunk_id"]: chunk})
        assert result.is_valid, (
            f"Exact substring failed: quote={quote!r}, score={result.match_score}"
        )

    @given(
        quote=st.text(min_size=1, max_size=200),
        content=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_is_valid_is_bool(self, validator, quote, content):
        """is_valid is always a proper bool."""
        chunk = _make_chunk(0, content)
        citation = _make_citation(chunk["chunk_id"], quote)
        result = validator._validate_one(citation, {chunk["chunk_id"]: chunk})
        assert isinstance(result.is_valid, bool)

    @given(quote=st.text(min_size=1, max_size=200))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_unknown_chunk_id_always_invalid(self, validator, quote):
        """Citation pointing to chunk_id not in chunk_map → always invalid."""
        citation = _make_citation("NONEXISTENT-CHUNK-99999", quote)
        result = validator._validate_one(citation, {})
        assert not result.is_valid


# ── Full pipeline: never crashes ──────────────────────────────────────────────

class TestPipelineProperties:
    @pytest.fixture(scope="class")
    def pipeline(self):
        from src.answer.generator import MockAnswerGenerator
        from src.answer.pipeline import AnswerPipeline
        return AnswerPipeline(
            generator=MockAnswerGenerator(),
            chunks=_CHUNKS,
            entity_index=_ENTITY_INDEX,
            top_k=5,
        )

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_pipeline_never_crashes(self, pipeline, question):
        """ask() must not raise for any non-empty question string."""
        from src.answer.models import ValidatedAnswer
        result = pipeline.ask(question)
        assert isinstance(result, ValidatedAnswer)

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_citation_confidence_always_in_range(self, pipeline, question):
        """citation_confidence ∈ [0, 1] for any input."""
        result = pipeline.ask(question)
        assert 0.0 <= result.citation_confidence <= 1.0

    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_strategy_always_valid(self, pipeline, question):
        """retrieval_strategy is always one of three known values."""
        result = pipeline.ask(question)
        assert result.retrieval_strategy in ("vector", "graph", "hybrid")
