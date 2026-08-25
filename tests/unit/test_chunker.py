"""Unit tests for the document chunker."""

from pathlib import Path

import pytest

from src.ingestion.chunker import (
    DocumentChunk,
    _extract_sections,
    _section_at_offset,
    chunk_document,
    make_chunk_id,
    make_document_id,
)
from src.ingestion.loader import RawDocument


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_doc(content: str, filename: str = "test_doc.md", doc_type: str = "company") -> RawDocument:
    """Create a minimal RawDocument for testing without hitting the filesystem."""
    import hashlib
    file_path = Path(f"/fake/{doc_type}s/{filename}")
    doc_hash = hashlib.sha256(content.encode()).hexdigest()
    return RawDocument(
        file_path=file_path,
        content=content,
        doc_type=doc_type,
        title="Test Document",
        doc_hash=doc_hash,
        char_count=len(content),
    )


SAMPLE_CONTENT = """\
# TechNova Overview

## About the Company

TechNova Corporation is an enterprise software company founded in 2010.
It provides NovaSuite, a business intelligence platform.

## Acquisitions

In 2022, TechNova acquired Stellar Systems for $340 million.
Stellar Systems developed StellarDB, a distributed database.

In 2023, TechNova acquired Apex Analytics for $220 million.
Apex Analytics built ApexML, a machine learning platform.

## Products

NovaSuite is TechNova's flagship product. It serves over 1,400 customers worldwide.
"""


# ── Tests: section extraction ─────────────────────────────────────────────────

def test_extract_sections_finds_all_headings():
    sections = _extract_sections(SAMPLE_CONTENT)
    headings = [name for _, name in sections]
    assert "TechNova Overview" in headings
    assert "About the Company" in headings
    assert "Acquisitions" in headings
    assert "Products" in headings


def test_extract_sections_returns_correct_offsets():
    content = "# Title\n\n## Section A\n\nText."
    sections = _extract_sections(content)
    # First heading is at offset 0
    assert sections[0][0] == 0
    assert sections[0][1] == "Title"


def test_section_at_offset_before_any_heading():
    sections = [(10, "Section A"), (50, "Section B")]
    assert _section_at_offset(0, sections) == "Introduction"


def test_section_at_offset_inside_section():
    sections = [(0, "Title"), (50, "Section A"), (200, "Section B")]
    # Position 100 is inside Section A
    assert _section_at_offset(100, sections) == "Section A"


def test_section_at_offset_at_exact_heading():
    sections = [(0, "Title"), (50, "Section A")]
    assert _section_at_offset(50, sections) == "Section A"


# ── Tests: ID generation ──────────────────────────────────────────────────────

def test_make_document_id_is_deterministic():
    path = Path("/corpus/companies/technova.md")
    id1 = make_document_id(path)
    id2 = make_document_id(path)
    assert id1 == id2


def test_make_document_id_different_paths_differ():
    id1 = make_document_id(Path("/corpus/companies/acme.md"))
    id2 = make_document_id(Path("/corpus/companies/beta.md"))
    assert id1 != id2


def test_make_chunk_id_is_deterministic():
    cid1 = make_chunk_id("abc123", 0)
    cid2 = make_chunk_id("abc123", 0)
    assert cid1 == cid2


def test_make_chunk_id_differs_by_index():
    cid0 = make_chunk_id("abc123", 0)
    cid1 = make_chunk_id("abc123", 1)
    assert cid0 != cid1


def test_make_chunk_id_differs_by_doc_hash():
    cid1 = make_chunk_id("hash_a", 0)
    cid2 = make_chunk_id("hash_b", 0)
    assert cid1 != cid2


# ── Tests: chunk_document ─────────────────────────────────────────────────────

def test_chunk_document_returns_non_empty_list():
    doc = _make_doc(SAMPLE_CONTENT)
    chunks = chunk_document(doc, chunk_size=100, chunk_overlap=20)
    assert len(chunks) >= 1


def test_chunk_document_all_chunks_have_required_fields():
    doc = _make_doc(SAMPLE_CONTENT)
    chunks = chunk_document(doc, chunk_size=100, chunk_overlap=20)
    for chunk in chunks:
        assert chunk.chunk_id
        assert chunk.document_id
        assert isinstance(chunk.chunk_index, int)
        assert chunk.content
        assert chunk.section
        assert chunk.source_file
        assert chunk.doc_type
        assert chunk.doc_hash
        assert chunk.token_count > 0
        assert chunk.ingestion_timestamp


def test_chunk_document_chunk_indices_are_sequential():
    doc = _make_doc(SAMPLE_CONTENT)
    chunks = chunk_document(doc, chunk_size=100, chunk_overlap=20)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_document_is_deterministic():
    doc = _make_doc(SAMPLE_CONTENT)
    chunks1 = chunk_document(doc, chunk_size=200, chunk_overlap=50)
    chunks2 = chunk_document(doc, chunk_size=200, chunk_overlap=50)
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]


def test_chunk_document_covers_all_content():
    """All text in the document should appear in at least one chunk."""
    doc = _make_doc(SAMPLE_CONTENT)
    chunks = chunk_document(doc, chunk_size=150, chunk_overlap=30)
    all_chunk_text = " ".join(c.content for c in chunks)
    # Key phrases from the original content should appear in combined chunks
    assert "TechNova" in all_chunk_text
    assert "Stellar Systems" in all_chunk_text
    assert "ApexML" in all_chunk_text


def test_chunk_document_section_assignment():
    doc = _make_doc(SAMPLE_CONTENT)
    chunks = chunk_document(doc, chunk_size=80, chunk_overlap=10)
    # At least one chunk should be assigned to a named section
    sections_found = {c.section for c in chunks}
    assert len(sections_found) > 1  # Multiple sections should appear


def test_chunk_ids_change_when_content_changes():
    content_v1 = "# Title\n\nOriginal content about Acme Corporation."
    content_v2 = "# Title\n\nModified content about Beta Corporation."
    doc_v1 = _make_doc(content_v1)
    doc_v2 = _make_doc(content_v2)
    chunks_v1 = chunk_document(doc_v1, chunk_size=200, chunk_overlap=20)
    chunks_v2 = chunk_document(doc_v2, chunk_size=200, chunk_overlap=20)
    # The document hashes differ → chunk IDs differ
    assert chunks_v1[0].chunk_id != chunks_v2[0].chunk_id


def test_to_dict_produces_all_expected_keys():
    doc = _make_doc("# Title\n\nSome content.")
    chunk = chunk_document(doc)[0]
    d = chunk.to_dict()
    expected_keys = {
        "chunk_id", "document_id", "chunk_index", "content",
        "section", "source_file", "doc_type", "doc_hash",
        "token_count", "char_count", "ingestion_timestamp", "metadata",
    }
    assert expected_keys.issubset(set(d.keys()))
