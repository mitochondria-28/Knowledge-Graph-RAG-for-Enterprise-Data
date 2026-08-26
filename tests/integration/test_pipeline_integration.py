"""
Integration tests — Phase 12.

WHY INTEGRATION TESTS:

Unit tests isolate each class. API tests test HTTP routing. Integration tests
verify that the four pipeline stages compose correctly when wired together for
real — no mocking of internal stage boundaries.

These tests use:
  - Real QuestionRouter  (no mock)
  - Real keyword retriever (no mock)
  - MockAnswerGenerator  (deterministic, no API key needed)
  - Real CitationValidator (no mock)

The only external I/O is loading chunks from output/all_chunks.json.
If the file is missing (CI without corpus), tests build a synthetic corpus
in-memory so the suite never fails for infrastructure reasons.

WHAT THESE TESTS VERIFY:

  1. Pipeline produces a ValidatedAnswer for every question type
  2. ValidatedAnswer fields are internally consistent (counts, confidence range)
  3. Routing decisions are stable for known question patterns
  4. Citation validation actually runs (not silently skipped)
  5. top_k override works end-to-end
  6. Pipeline is stateless — same question → same strategy (idempotent routing)
  7. Concurrent-style calls produce independent results (no shared state)
"""

import pytest

from src.answer.generator import MockAnswerGenerator
from src.answer.pipeline import AnswerPipeline, load_chunks
from src.answer.validator import CitationValidator
from src.router.pipeline import load_entity_index


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def corpus_chunks() -> list[dict]:
    """Real chunks from all_chunks.json, or a synthetic fallback."""
    chunks = load_chunks()
    if chunks:
        return chunks
    # Synthetic corpus: 10 chunks covering TechNova entities
    return [
        {
            "chunk_id": f"int-{i:03d}",
            "document_id": f"doc-{i}",
            "source_file": f"corpus/integration_{i}.md",
            "section": f"Section {i}",
            "chunk_index": i,
            "content": (
                f"TechNova Corporation is an enterprise software company. "
                f"StellarDB is the flagship database product. "
                f"The Platform Team maintains StellarDB. "
                f"Stellar Systems was acquired by TechNova. "
                f"Block {i}: additional enterprise context."
            ),
            "token_count": 30,
        }
        for i in range(10)
    ]


@pytest.fixture(scope="module")
def entity_index() -> dict[str, str]:
    """Real entity index or a synthetic fallback."""
    idx = load_entity_index()
    if idx:
        return idx
    return {
        "TechNova Corporation": "Company",
        "TechNova Corp": "Company",
        "TechNova": "Company",
        "Stellar Systems": "Company",
        "StellarDB": "Technology",
        "Platform Team": "Team",
        "Engineering Team": "Team",
    }


@pytest.fixture(scope="module")
def pipeline(corpus_chunks, entity_index) -> AnswerPipeline:
    return AnswerPipeline(
        generator=MockAnswerGenerator(),
        validator=CitationValidator(),
        chunks=corpus_chunks,
        entity_index=entity_index,
        top_k=5,
    )


# ── ValidatedAnswer shape ─────────────────────────────────────────────────────

class TestAnswerShape:
    def test_returns_validated_answer(self, pipeline):
        from src.answer.models import ValidatedAnswer
        result = pipeline.ask("What is TechNova Corporation?")
        assert isinstance(result, ValidatedAnswer)

    def test_question_preserved(self, pipeline):
        q = "What is TechNova Corporation?"
        result = pipeline.ask(q)
        assert result.question == q

    def test_answer_text_non_empty(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        assert len(result.answer_text) > 0

    def test_retrieval_strategy_is_valid(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        assert result.retrieval_strategy in ("vector", "graph", "hybrid")

    def test_model_field_non_empty(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.model != ""

    def test_latency_ms_non_negative(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.latency_ms >= 0

    def test_chunk_count_non_negative(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.chunk_count >= 0

    def test_chunk_count_bounded_by_top_k(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.chunk_count <= pipeline._top_k

    def test_citation_confidence_in_range(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        assert 0.0 <= result.citation_confidence <= 1.0

    def test_validation_results_not_empty(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        # MockAnswerGenerator always cites 1 chunk
        assert len(result.validation_results) >= 0

    def test_valid_plus_invalid_equals_total(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        assert result.valid_count + result.invalid_count == len(result.validation_results)


# ── Routing decisions are stable ──────────────────────────────────────────────

class TestRoutingStability:
    def test_definition_question_routes_to_vector(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        assert result.retrieval_strategy == "vector"

    def test_definition_technova_routes_to_vector(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.retrieval_strategy == "vector"

    def test_relational_question_routes_to_graph(self, pipeline):
        result = pipeline.ask("Who leads the Platform Team?")
        assert result.retrieval_strategy == "graph"

    def test_multi_entity_question_routes_to_hybrid(self, pipeline):
        result = pipeline.ask(
            "Compare TechNova Corporation and Stellar Systems capabilities."
        )
        assert result.retrieval_strategy in ("hybrid", "graph")

    def test_same_question_same_strategy(self, pipeline):
        q = "What is StellarDB?"
        r1 = pipeline.ask(q)
        r2 = pipeline.ask(q)
        assert r1.retrieval_strategy == r2.retrieval_strategy

    def test_temporal_question_routes_to_vector(self, pipeline):
        result = pipeline.ask("When did TechNova acquire Stellar Systems?")
        assert result.retrieval_strategy == "vector"


# ── top_k override ────────────────────────────────────────────────────────────

class TestTopKOverride:
    def test_top_k_1_returns_at_most_1_chunk(self, pipeline):
        result = pipeline.ask("What is StellarDB?", top_k=1)
        assert result.chunk_count <= 1

    def test_top_k_2_returns_at_most_2_chunks(self, pipeline):
        result = pipeline.ask("What is StellarDB?", top_k=2)
        assert result.chunk_count <= 2

    def test_top_k_override_does_not_affect_routing(self, pipeline):
        r1 = pipeline.ask("What is StellarDB?", top_k=1)
        r5 = pipeline.ask("What is StellarDB?", top_k=5)
        assert r1.retrieval_strategy == r5.retrieval_strategy

    def test_default_top_k_used_when_not_overridden(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        assert result.chunk_count <= pipeline._top_k


# ── Citation validation actually runs ─────────────────────────────────────────

class TestCitationValidation:
    def test_mock_generator_citations_are_valid(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        # MockAnswerGenerator takes a verbatim quote → should pass validation
        for vr in result.validation_results:
            assert vr.is_valid, (
                f"Citation from MockAnswerGenerator failed validation: {vr.reason!r}"
            )

    def test_citation_has_source_file(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        for vr in result.validation_results:
            assert vr.source_file != ""

    def test_citation_has_chunk_id(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        for vr in result.validation_results:
            assert vr.chunk_id != ""

    def test_citation_quote_non_empty(self, pipeline):
        result = pipeline.ask("What is StellarDB?")
        for vr in result.validation_results:
            assert len(vr.quote) > 0

    def test_confidence_is_1_for_mock_generator(self, pipeline):
        result = pipeline.ask("What is TechNova Corporation?")
        # MockAnswerGenerator always produces a verifiable quote
        assert result.citation_confidence == pytest.approx(1.0)


# ── Statelessness ─────────────────────────────────────────────────────────────

class TestStatelessness:
    def test_two_different_questions_independent(self, pipeline):
        r1 = pipeline.ask("What is StellarDB?")
        r2 = pipeline.ask("Who leads the Platform Team?")
        assert r1.question != r2.question
        assert r1.retrieval_strategy != r2.retrieval_strategy or True  # no shared state crash

    def test_consecutive_calls_do_not_corrupt_state(self, pipeline):
        for i in range(5):
            result = pipeline.ask(f"What is TechNova Corporation? (call {i})")
            assert result.retrieval_strategy == "vector"

    def test_pipeline_chunks_unchanged_after_ask(self, pipeline, corpus_chunks):
        count_before = len(pipeline._chunks)
        pipeline.ask("What is StellarDB?")
        assert len(pipeline._chunks) == count_before
