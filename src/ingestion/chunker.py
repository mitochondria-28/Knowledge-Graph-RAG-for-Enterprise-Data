"""
Document chunker — splits normalized text into overlapping chunks with
stable, deterministic IDs and section-aware metadata.

KEY CONCEPTS:

Token-based splitting (not character-based):
  LLMs charge by token, not character. A 500-character chunk might be 80
  tokens or 200 tokens depending on the content. We size chunks in tokens
  so we have predictable context window usage when we later pass chunks to
  Claude for extraction and generation.

Overlapping chunks:
  Chunk N and Chunk N+1 share `chunk_overlap` tokens at their boundary.
  This prevents a sentence that spans a chunk boundary from being split
  across two chunks with neither containing full context.

  Without overlap:   [... end of chunk 1] [start of chunk 2 ...]
  Key sentence:      [... "Acme acquired] [Beta Corp in 2022" ...]
  → Extraction on chunk 1 sees "Acme acquired" with no target.
  → Extraction on chunk 2 sees a bare "Beta Corp in 2022" with no subject.

  With overlap:      [... "Acme acquired Beta Corp in 2022" appears in BOTH]
  → Either chunk can extract the full relationship.

Stable chunk IDs:
  chunk_id = UUID5(doc_hash + ":" + str(chunk_index))
  - Same document content → always produces the same chunk IDs.
  - Modified document → doc_hash changes → all chunk IDs change.
  - This lets Neo4j and PostgreSQL use chunk_id as a stable foreign key
    across systems without a central ID registry.

Section detection:
  We parse Markdown headings to label each chunk with the section it came
  from. This metadata survives into the vector DB and can be used to filter
  or boost retrieval ("only search within the 'Architecture' section").
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.ingestion.loader import RawDocument

logger = logging.getLogger(__name__)

# cl100k_base is the tokenizer used by GPT-4 and Claude approximates it well
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def make_document_id(file_path: Path) -> str:
    """Stable UUID derived from the file path (not content).

    This is intentionally path-based, not content-based, so a document
    keeps the same document_id even when its content is updated. The
    doc_hash captures content changes.
    """
    return str(uuid5(NAMESPACE_URL, str(file_path)))


def make_chunk_id(doc_hash: str, chunk_index: int) -> str:
    """Deterministic UUID derived from content hash + position.

    When the document content changes, doc_hash changes, so all chunk IDs
    change. This is correct: old chunks are invalidated and must be
    re-extracted and re-embedded.
    """
    return str(uuid5(NAMESPACE_URL, f"{doc_hash}:{chunk_index}"))


def _extract_sections(content: str) -> list[tuple[int, str]]:
    """
    Parse all Markdown headings (H1–H6) and return their character offsets.

    Returns: sorted list of (char_offset, heading_text)
    """
    sections: list[tuple[int, str]] = []
    for match in re.finditer(r"^#{1,6}\s+(.+)$", content, re.MULTILINE):
        sections.append((match.start(), match.group(1).strip()))
    return sections  # already sorted by re.finditer (left-to-right)


def _section_at_offset(offset: int, sections: list[tuple[int, str]]) -> str:
    """
    Return the text of the most recent heading that precedes `offset`.
    Falls back to "Introduction" if no heading precedes the chunk.
    """
    current = "Introduction"
    for section_offset, heading in sections:
        if section_offset <= offset:
            current = heading
        else:
            break  # headings are sorted; no need to continue
    return current


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    """A single chunk of a source document, ready for embedding and extraction."""

    chunk_id: str            # UUID5(doc_hash:chunk_index) — stable, cross-system key
    document_id: str         # UUID5(file_path) — stable across content updates
    chunk_index: int         # 0-based position within the document
    content: str             # the actual text of the chunk
    section: str             # nearest preceding Markdown heading
    source_file: str         # original file path (for citations)
    doc_type: str            # "company" | "project" | "technology" | "people"
    doc_hash: str            # SHA-256 of normalized document content
    token_count: int         # actual token count (not estimated)
    char_count: int
    ingestion_timestamp: str # ISO-8601 UTC
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "section": self.section,
            "source_file": self.source_file,
            "doc_type": self.doc_type,
            "doc_hash": self.doc_hash,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "ingestion_timestamp": self.ingestion_timestamp,
            "metadata": self.metadata,
        }


# ── Main chunking function ────────────────────────────────────────────────────

def chunk_document(
    doc: RawDocument,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[DocumentChunk]:
    """
    Split a RawDocument into overlapping chunks with stable IDs.

    The splitter tries separators in order:
      1. Double newline (paragraph boundary) — preferred
      2. Single newline (line boundary)
      3. ". " / "! " / "? " (sentence boundary)
      4. " " (word boundary)
      5. "" (character boundary — last resort, avoids cutting mid-token)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=_count_tokens,
        add_start_index=True,   # populates metadata["start_index"] per chunk
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
    )

    document_id = make_document_id(doc.file_path)
    sections = _extract_sections(doc.content)
    timestamp = datetime.now(timezone.utc).isoformat()

    raw_chunks = splitter.create_documents(
        texts=[doc.content],
        metadatas=[{"source": str(doc.file_path)}],
    )

    chunks: list[DocumentChunk] = []
    for i, raw in enumerate(raw_chunks):
        start_index: int = raw.metadata.get("start_index", 0)
        text = raw.page_content
        token_count = _count_tokens(text)

        chunks.append(DocumentChunk(
            chunk_id=make_chunk_id(doc.doc_hash, i),
            document_id=document_id,
            chunk_index=i,
            content=text,
            section=_section_at_offset(start_index, sections),
            source_file=str(doc.file_path),
            doc_type=doc.doc_type,
            doc_hash=doc.doc_hash,
            token_count=token_count,
            char_count=len(text),
            ingestion_timestamp=timestamp,
            metadata={
                "title": doc.title,
                "start_index": start_index,
            },
        ))

    avg_tokens = sum(c.token_count for c in chunks) // max(len(chunks), 1)
    logger.debug(
        "Chunked '%s': %d chunks (avg %d tokens)",
        doc.title, len(chunks), avg_tokens,
    )
    return chunks
