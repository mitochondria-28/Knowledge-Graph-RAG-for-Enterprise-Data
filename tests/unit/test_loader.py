"""Unit tests for the document loader."""

import hashlib
from pathlib import Path

import pytest

from src.ingestion.loader import (
    _extract_title,
    _infer_doc_type,
    _sha256,
    discover_documents,
    load_document,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_md_file(tmp_path: Path) -> Path:
    doc = tmp_path / "companies" / "acme_overview.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "# Acme Corporation Overview\n\n"
        "Acme Corporation is a fictional enterprise company.\n\n"
        "## Products\n\nAcme produces widgets and gadgets.",
        encoding="utf-8",
    )
    return doc


@pytest.fixture
def txt_file(tmp_path: Path) -> Path:
    doc = tmp_path / "projects" / "project_x.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text("Project X is an initiative.\n\nIt does things.", encoding="utf-8")
    return doc


# ── Tests: _infer_doc_type ────────────────────────────────────────────────────

def test_infer_doc_type_company(tmp_path):
    path = tmp_path / "companies" / "file.md"
    assert _infer_doc_type(path) == "company"


def test_infer_doc_type_project(tmp_path):
    path = tmp_path / "projects" / "file.md"
    assert _infer_doc_type(path) == "project"


def test_infer_doc_type_technology(tmp_path):
    path = tmp_path / "technologies" / "file.md"
    assert _infer_doc_type(path) == "technology"


def test_infer_doc_type_fallback(tmp_path):
    path = tmp_path / "unknown_dir" / "file.md"
    assert _infer_doc_type(path) == "general"


# ── Tests: _extract_title ─────────────────────────────────────────────────────

def test_extract_title_from_h1():
    content = "# My Great Document\n\nSome content here."
    assert _extract_title(content, Path("anything.md")) == "My Great Document"


def test_extract_title_fallback_to_filename():
    content = "No headings here, just text."
    path = Path("my_important_document.md")
    title = _extract_title(content, path)
    assert title == "My Important Document"


def test_extract_title_ignores_h2():
    content = "## Sub-heading Only\n\nContent."
    path = Path("fallback.md")
    # Should fall back to filename since there is no H1
    title = _extract_title(content, path)
    assert title == "Fallback"


# ── Tests: load_document ──────────────────────────────────────────────────────

def test_load_document_returns_raw_document(sample_md_file):
    doc = load_document(sample_md_file)
    assert doc.title == "Acme Corporation Overview"
    assert doc.doc_type == "company"
    assert "Acme Corporation" in doc.content
    assert len(doc.doc_hash) == 64          # SHA-256 hex digest is 64 chars
    assert doc.char_count > 0


def test_load_document_hash_is_deterministic(sample_md_file):
    doc1 = load_document(sample_md_file)
    doc2 = load_document(sample_md_file)
    assert doc1.doc_hash == doc2.doc_hash


def test_load_document_different_files_different_hashes(sample_md_file, txt_file):
    doc1 = load_document(sample_md_file)
    doc2 = load_document(txt_file)
    assert doc1.doc_hash != doc2.doc_hash


def test_load_document_rejects_unsupported_extension(tmp_path):
    pdf_file = tmp_path / "file.pdf"
    pdf_file.write_bytes(b"%PDF fake content")
    with pytest.raises(ValueError, match="Unsupported extension"):
        load_document(pdf_file)


# ── Tests: discover_documents ─────────────────────────────────────────────────

def test_discover_documents_finds_markdown(tmp_path):
    (tmp_path / "a.md").write_text("content", encoding="utf-8")
    (tmp_path / "b.txt").write_text("content", encoding="utf-8")
    (tmp_path / "c.pdf").write_bytes(b"%PDF")

    found = discover_documents(tmp_path)
    names = {p.name for p in found}
    assert "a.md" in names
    assert "b.txt" in names
    assert "c.pdf" not in names


def test_discover_documents_is_sorted(tmp_path):
    for name in ["c.md", "a.md", "b.md"]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    found = discover_documents(tmp_path)
    assert found == sorted(found)


def test_discover_documents_empty_directory(tmp_path):
    assert discover_documents(tmp_path) == []
