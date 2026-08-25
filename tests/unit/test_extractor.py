"""
Unit tests for the extractor — Claude API calls are mocked.

WHY MOCK THE API:

These tests verify the extraction pipeline logic — retry behavior, response
parsing, error handling — without making real API calls. Running real API
calls in unit tests creates problems:
  - Tests fail without a network connection
  - Tests cost money on every run
  - Tests are slow (LLM inference latency)
  - Test outcomes are non-deterministic (LLM outputs vary)

We use unittest.mock.patch to replace the Anthropic client with a mock that
returns a controlled, pre-defined response.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.extraction.extractor import (
    ExtractionError,
    _build_user_message,
    _parse_tool_response,
    extract_chunk,
)
from src.extraction.schemas import ChunkExtractionResult


# ── Test data ─────────────────────────────────────────────────────────────────

SAMPLE_CHUNK_CONTENT = """\
Project Phoenix is TechNova's internal engineering initiative to migrate \
NovaSuite's data layer to StellarDB. The project is owned by TechNova Corporation \
and is managed by the Platform Team under the leadership of Aisha Patel.
"""

VALID_TOOL_RESPONSE = {
    "entities": [
        {"name": "Project Phoenix", "entity_type": "Project", "confidence": 0.99},
        {"name": "TechNova Corporation", "entity_type": "Company", "confidence": 0.99},
        {"name": "NovaSuite", "entity_type": "Product", "confidence": 0.95},
        {"name": "StellarDB", "entity_type": "Technology", "confidence": 0.99},
        {"name": "Platform Team", "entity_type": "Team", "confidence": 0.99},
        {"name": "Aisha Patel", "entity_type": "Person", "confidence": 0.99},
    ],
    "relationships": [
        {
            "source_entity": "TechNova Corporation",
            "source_type": "Company",
            "relationship_type": "OWNS",
            "target_entity": "Project Phoenix",
            "target_type": "Project",
            "supporting_text": "owned by TechNova Corporation",
            "confidence": 0.99,
        },
        {
            "source_entity": "Project Phoenix",
            "source_type": "Project",
            "relationship_type": "USES",
            "target_entity": "StellarDB",
            "target_type": "Technology",
            "supporting_text": "migrate NovaSuite's data layer to StellarDB",
            "confidence": 0.97,
        },
        {
            "source_entity": "Platform Team",
            "source_type": "Team",
            "relationship_type": "MANAGES",
            "target_entity": "Project Phoenix",
            "target_type": "Project",
            "supporting_text": "managed by the Platform Team",
            "confidence": 0.99,
        },
        {
            "source_entity": "Platform Team",
            "source_type": "Team",
            "relationship_type": "LED_BY",
            "target_entity": "Aisha Patel",
            "target_type": "Person",
            "supporting_text": "under the leadership of Aisha Patel",
            "confidence": 0.99,
        },
    ],
}


# ── Mock builders ─────────────────────────────────────────────────────────────

def _make_mock_response(tool_input: dict, input_tokens: int = 1000, output_tokens: int = 300):
    """Build a mock anthropic.Message that looks like a tool_use response."""
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_entities_and_relationships"
    mock_block.input = tool_input

    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = mock_usage
    return mock_response


def _make_mock_client(tool_input: dict, **kwargs):
    """Return a mock Anthropic client whose messages.create returns the given tool_input."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(tool_input, **kwargs)
    return mock_client


# ── Tests: _parse_tool_response ───────────────────────────────────────────────

def test_parse_tool_response_extracts_input():
    response = _make_mock_response({"entities": [], "relationships": []})
    result = _parse_tool_response(response)
    assert result == {"entities": [], "relationships": []}


def test_parse_tool_response_returns_none_if_no_tool_block():
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"           # not a tool_use block
    mock_response.content = [mock_block]
    assert _parse_tool_response(mock_response) is None


# ── Tests: _build_user_message ────────────────────────────────────────────────

def test_build_user_message_first_attempt():
    msg = _build_user_message("some content", last_error=None, attempt=1)
    assert "some content" in msg
    assert "ERRORS" not in msg


def test_build_user_message_retry_includes_error():
    msg = _build_user_message(
        "some content",
        last_error="source entity 'X' not found in entities list.",
        attempt=2,
    )
    assert "ERRORS" in msg
    assert "X" in msg
    assert "some content" in msg


# ── Tests: extract_chunk (happy path) ─────────────────────────────────────────

def test_extract_chunk_success():
    client = _make_mock_client(VALID_TOOL_RESPONSE)
    record = extract_chunk(
        chunk_id="test-chunk-0001",
        document_id="test-doc-0001",
        source_file="corpus/projects/project_phoenix.md",
        doc_hash="abc123",
        section="Project Overview",
        content=SAMPLE_CHUNK_CONTENT,
        client=client,
    )
    assert record.chunk_id == "test-chunk-0001"
    assert len(record.extraction.entities) == 6
    assert len(record.extraction.relationships) == 4
    assert record.attempts == 1
    assert record.input_tokens == 1000
    assert record.output_tokens == 300


def test_extract_chunk_records_model():
    client = _make_mock_client(VALID_TOOL_RESPONSE)
    record = extract_chunk(
        chunk_id="test-chunk-0002",
        document_id="test-doc-0001",
        source_file="corpus/projects/project_phoenix.md",
        doc_hash="abc123",
        section="Project Overview",
        content=SAMPLE_CHUNK_CONTENT,
        client=client,
        model="claude-sonnet-4-6",
    )
    assert record.model == "claude-sonnet-4-6"


# ── Tests: extract_chunk (retry behavior) ─────────────────────────────────────

def test_extract_chunk_retries_on_validation_failure():
    """
    First call returns a relationship whose source entity is not in the entities list.
    Second call returns a valid response.
    The extractor should succeed on attempt 2.
    """
    invalid_response = {
        "entities": [
            {"name": "StellarDB", "entity_type": "Technology", "confidence": 0.99},
        ],
        "relationships": [
            {
                "source_entity": "Missing Entity",   # NOT in entities list → hard error
                "source_type": "Company",
                "relationship_type": "DEVELOPS",     # invalid rel type will be caught earlier
                "target_entity": "StellarDB",
                "target_type": "Technology",
                "confidence": 0.9,
            }
        ],
    }

    # Use a simpler valid response for retry
    valid_retry = {
        "entities": [
            {"name": "StellarDB", "entity_type": "Technology", "confidence": 0.99},
        ],
        "relationships": [],
    }

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _make_mock_response(invalid_response),
        _make_mock_response(valid_retry),
    ]

    record = extract_chunk(
        chunk_id="test-chunk-retry",
        document_id="test-doc",
        source_file="corpus/test.md",
        doc_hash="hash",
        section="Test",
        content="StellarDB is a database.",
        client=mock_client,
    )
    assert record.attempts == 2
    assert mock_client.messages.create.call_count == 2


def test_extract_chunk_raises_after_max_retries():
    """If all retries fail, ExtractionError is raised."""
    # Always return a response with a dangling relationship reference
    bad_response = {
        "entities": [],
        "relationships": [
            {
                "source_entity": "X",
                "source_type": "Company",
                "relationship_type": "ACQUIRED",
                "target_entity": "Y",
                "target_type": "Company",
                "confidence": 0.9,
            }
        ],
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(bad_response)

    with pytest.raises(ExtractionError):
        extract_chunk(
            chunk_id="test-chunk-fail",
            document_id="test-doc",
            source_file="corpus/test.md",
            doc_hash="hash",
            section="Test",
            content="Some content.",
            client=mock_client,
        )
    # Should have been called MAX_RETRIES times
    assert mock_client.messages.create.call_count == 3
