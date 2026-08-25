"""
Unit tests for Phase 8 answer generator.

Tests verify:
  1. format_context — correct [CHUNK ...] headers in context string
  2. MockAnswerGenerator — returns valid RawAnswer without API calls
  3. AnswerGenerator — correct Claude API call structure and response parsing
  4. Edge cases — no chunks, missing tool_use block, empty citations

No API key or running services required.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.answer.generator import (
    AnswerGenerator,
    MockAnswerGenerator,
    format_context,
    _ANSWER_TOOL,
    _SYSTEM_PROMPT,
    DEFAULT_MODEL,
)
from src.answer.models import Citation, RawAnswer


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "chunk-aaa",
            "document_id": "doc-1",
            "source_file": "corpus/companies/technova_overview.md",
            "section": "Overview",
            "chunk_index": 0,
            "content": "TechNova Corporation was founded in 2010 and specialises in enterprise data infrastructure.",
            "token_count": 18,
        },
        {
            "chunk_id": "chunk-bbb",
            "document_id": "doc-2",
            "source_file": "corpus/people/engineering_org.md",
            "section": "Platform Team",
            "chunk_index": 1,
            "content": "Sandra Müller leads the Platform Team, which is responsible for StellarDB operations.",
            "token_count": 17,
        },
    ]


def _make_mock_client(answer: str, citations: list[dict], confidence: float = 0.9):
    """Build a mock Anthropic client that returns a provide_answer tool call."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "provide_answer"
    tool_block.input = {
        "answer": answer,
        "citations": citations,
        "answer_confidence": confidence,
    }

    response = MagicMock()
    response.content = [tool_block]

    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ── format_context ────────────────────────────────────────────────────────────

class TestFormatContext:
    def test_chunk_header_present(self, sample_chunks):
        ctx = format_context(sample_chunks)
        assert "[CHUNK chunk-aaa |" in ctx
        assert "[CHUNK chunk-bbb |" in ctx

    def test_source_file_in_header(self, sample_chunks):
        ctx = format_context(sample_chunks)
        assert "corpus/companies/technova_overview.md" in ctx
        assert "corpus/people/engineering_org.md" in ctx

    def test_section_in_header(self, sample_chunks):
        ctx = format_context(sample_chunks)
        assert "section: Overview" in ctx
        assert "section: Platform Team" in ctx

    def test_content_present(self, sample_chunks):
        ctx = format_context(sample_chunks)
        assert "TechNova Corporation was founded in 2010" in ctx
        assert "Sandra Müller leads the Platform Team" in ctx

    def test_separator_between_chunks(self, sample_chunks):
        ctx = format_context(sample_chunks)
        assert "---" in ctx

    def test_single_chunk_no_separator(self, sample_chunks):
        ctx = format_context(sample_chunks[:1])
        # Only one chunk — separator not needed
        assert "[CHUNK chunk-aaa |" in ctx

    def test_empty_chunks_returns_empty_string(self):
        assert format_context([]) == ""

    def test_missing_section_defaults_to_unknown(self):
        chunk = {
            "chunk_id": "chunk-x",
            "source_file": "corpus/test.md",
            "content": "some content",
        }
        ctx = format_context([chunk])
        assert "section: unknown" in ctx


# ── MockAnswerGenerator ───────────────────────────────────────────────────────

class TestMockAnswerGenerator:
    def test_returns_raw_answer(self, sample_chunks):
        gen = MockAnswerGenerator()
        result = gen.generate("Who leads the Platform Team?", sample_chunks)
        assert isinstance(result, RawAnswer)

    def test_model_is_mock(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        assert result.model == "mock"

    def test_has_at_least_one_citation(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        assert len(result.citations) >= 1

    def test_citation_chunk_id_is_top_chunks_id(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        assert result.citations[0].chunk_id == "chunk-aaa"

    def test_quote_is_substring_of_chunk_content(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        top_content = sample_chunks[0]["content"].lower()
        assert result.citations[0].quote.lower() in top_content

    def test_no_chunks_returns_empty_answer(self):
        result = MockAnswerGenerator().generate("Q?", [])
        assert result.citations == []
        assert result.chunk_count == 0
        assert "No context" in result.answer_text

    def test_chunk_count_matches_input(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        assert result.chunk_count == len(sample_chunks)

    def test_latency_is_nonnegative(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks)
        assert result.latency_ms >= 0.0

    def test_question_is_preserved(self, sample_chunks):
        q = "Who leads the Platform Team?"
        result = MockAnswerGenerator().generate(q, sample_chunks)
        assert result.question == q

    def test_strategy_is_preserved(self, sample_chunks):
        result = MockAnswerGenerator().generate("Q?", sample_chunks, strategy="graph")
        assert result.retrieval_strategy == "graph"


# ── AnswerGenerator ───────────────────────────────────────────────────────────

class TestAnswerGenerator:
    def test_calls_messages_create(self, sample_chunks):
        client = _make_mock_client("TechNova was founded in 2010.", [
            {"chunk_id": "chunk-aaa", "quote": "TechNova Corporation was founded in 2010"}
        ])
        gen = AnswerGenerator(client)
        gen.generate("When was TechNova founded?", sample_chunks)
        assert client.messages.create.called

    def test_tool_choice_is_provide_answer(self, sample_chunks):
        client = _make_mock_client("answer text", [])
        gen = AnswerGenerator(client)
        gen.generate("Q?", sample_chunks)

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "provide_answer"}

    def test_tools_contains_answer_tool(self, sample_chunks):
        client = _make_mock_client("answer text", [])
        gen = AnswerGenerator(client)
        gen.generate("Q?", sample_chunks)

        tools = client.messages.create.call_args.kwargs["tools"]
        tool_names = [t["name"] for t in tools]
        assert "provide_answer" in tool_names

    def test_system_prompt_sent(self, sample_chunks):
        client = _make_mock_client("answer text", [])
        gen = AnswerGenerator(client)
        gen.generate("Q?", sample_chunks)

        call_kwargs = client.messages.create.call_args.kwargs
        assert "provide_answer" in call_kwargs["system"]

    def test_question_in_user_message(self, sample_chunks):
        client = _make_mock_client("answer text", [])
        gen = AnswerGenerator(client)
        gen.generate("Who leads the team?", sample_chunks)

        messages = client.messages.create.call_args.kwargs["messages"]
        user_content = messages[0]["content"]
        assert "Who leads the team?" in user_content

    def test_chunk_content_in_user_message(self, sample_chunks):
        client = _make_mock_client("answer text", [])
        gen = AnswerGenerator(client)
        gen.generate("Q?", sample_chunks)

        messages = client.messages.create.call_args.kwargs["messages"]
        content = messages[0]["content"]
        assert "chunk-aaa" in content
        assert "TechNova Corporation was founded" in content

    def test_parses_answer_text(self, sample_chunks):
        client = _make_mock_client("TechNova was founded in 2010.", [])
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", sample_chunks)
        assert result.answer_text == "TechNova was founded in 2010."

    def test_parses_citations(self, sample_chunks):
        client = _make_mock_client("answer", [
            {"chunk_id": "chunk-aaa", "quote": "TechNova Corporation was founded"},
            {"chunk_id": "chunk-bbb", "quote": "Sandra Müller leads"},
        ])
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", sample_chunks)
        assert len(result.citations) == 2
        assert result.citations[0].chunk_id == "chunk-aaa"
        assert result.citations[1].chunk_id == "chunk-bbb"

    def test_citation_source_file_resolved(self, sample_chunks):
        client = _make_mock_client("answer", [
            {"chunk_id": "chunk-aaa", "quote": "some quote"}
        ])
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", sample_chunks)
        assert result.citations[0].source_file == "corpus/companies/technova_overview.md"

    def test_unknown_source_for_hallucinated_chunk_id(self, sample_chunks):
        client = _make_mock_client("answer", [
            {"chunk_id": "chunk-NONEXISTENT", "quote": "some quote"}
        ])
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", sample_chunks)
        assert result.citations[0].source_file == "unknown"

    def test_llm_confidence_captured(self, sample_chunks):
        client = _make_mock_client("answer", [], confidence=0.75)
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", sample_chunks)
        assert result.llm_confidence == 0.75

    def test_raises_if_no_tool_use_block(self, sample_chunks):
        """Claude must return provide_answer — ValueError if it doesn't."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.name = "not_provide_answer"

        response = MagicMock()
        response.content = [text_block]

        client = MagicMock()
        client.messages.create.return_value = response

        gen = AnswerGenerator(client)
        with pytest.raises(ValueError, match="provide_answer"):
            gen.generate("Q?", sample_chunks)

    def test_empty_chunks_returns_early(self):
        client = MagicMock()
        gen = AnswerGenerator(client)
        result = gen.generate("Q?", [])
        # Should not call Claude at all
        assert not client.messages.create.called
        assert result.chunk_count == 0
        assert result.citations == []

    def test_custom_model_passed_to_api(self, sample_chunks):
        client = _make_mock_client("answer", [])
        gen = AnswerGenerator(client, model="claude-sonnet-4-6")
        gen.generate("Q?", sample_chunks)

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
