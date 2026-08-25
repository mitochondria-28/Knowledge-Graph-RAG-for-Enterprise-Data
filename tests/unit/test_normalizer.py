"""Unit tests for the text normalizer."""

import pytest

from src.ingestion.normalizer import normalize_text


def test_strips_leading_trailing_whitespace():
    assert normalize_text("  hello world  ") == "hello world"


def test_normalizes_crlf_line_endings():
    result = normalize_text("line one\r\nline two\r\n")
    assert "\r" not in result
    assert result == "line one\nline two"


def test_collapses_excessive_blank_lines():
    text = "para one\n\n\n\n\n\npara two"
    result = normalize_text(text)
    # More than 3 consecutive newlines should be collapsed
    assert "\n\n\n\n" not in result
    assert "para one" in result
    assert "para two" in result


def test_strips_trailing_whitespace_per_line():
    text = "line one   \nline two  \nline three"
    result = normalize_text(text)
    for line in result.splitlines():
        assert line == line.rstrip()


def test_removes_null_bytes():
    text = "hello\x00world"
    result = normalize_text(text)
    assert "\x00" not in result
    assert "helloworld" in result


def test_preserves_markdown_structure():
    text = "# Title\n\n## Section\n\nSome text here."
    result = normalize_text(text)
    assert "# Title" in result
    assert "## Section" in result
    assert "Some text here." in result


def test_unicode_normalization():
    # 'é' as two codepoints (e + combining accent) should become one codepoint
    composed = "é"       # é as single codepoint
    decomposed = "é"   # é as e + combining accent
    assert normalize_text(decomposed) == normalize_text(composed)


def test_empty_string_returns_empty():
    assert normalize_text("") == ""


def test_only_whitespace_returns_empty():
    assert normalize_text("   \n  \n  ") == ""
