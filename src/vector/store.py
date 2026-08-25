"""
pgvector CRUD: upsert chunks and similarity search.

UPSERT STRATEGY — INSERT ... ON CONFLICT DO UPDATE:

  The chunk_id is a stable UUID5 derived from (doc_hash, chunk_index).
  Re-running the loader on the same chunks should update embeddings
  (in case we upgrade the model) without creating duplicates.

  ON CONFLICT (chunk_id) DO UPDATE SET
      embedding       = EXCLUDED.embedding,
      embedding_model = EXCLUDED.embedding_model,
      embedded_at     = EXCLUDED.embedded_at

  The content/metadata columns are NOT updated on conflict — the content
  doesn't change for a given chunk_id (changing content → new doc_hash →
  new chunk_id).

SIMILARITY SEARCH — cosine distance (<=>):

  pgvector's <=> operator computes cosine distance ∈ [0, 2].
  Cosine similarity = 1 - cosine_distance.
  We ORDER BY distance ASC so the nearest chunk comes first,
  and convert: similarity = 1 - distance.

  Example:
    identical vectors → distance 0.0 → similarity 1.0
    orthogonal vectors → distance 1.0 → similarity 0.0
    opposite vectors → distance 2.0 → similarity -1.0

  For retrieval, similarity ≥ 0.7 is a reasonable default threshold.

PARAMETERIZED QUERIES:

  All SQL uses %s placeholders with psycopg3 parameterized execution.
  No user input or LLM output is ever interpolated into SQL strings.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO chunks (
    chunk_id, document_id, source_file, section, chunk_index,
    content, token_count, doc_hash,
    embedding, embedding_model, embedded_at, metadata
)
VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s
)
ON CONFLICT (chunk_id) DO UPDATE SET
    embedding       = EXCLUDED.embedding,
    embedding_model = EXCLUDED.embedding_model,
    embedded_at     = EXCLUDED.embedded_at
"""

_SEARCH_SQL = """
SELECT
    chunk_id,
    document_id,
    source_file,
    section,
    chunk_index,
    content,
    token_count,
    embedding_model,
    1 - (embedding <=> %s) AS similarity
FROM chunks
WHERE embedded_at IS NOT NULL
ORDER BY embedding <=> %s
LIMIT %s
"""

_SEARCH_WITH_THRESHOLD_SQL = """
SELECT
    chunk_id,
    document_id,
    source_file,
    section,
    chunk_index,
    content,
    token_count,
    embedding_model,
    1 - (embedding <=> %s) AS similarity
FROM chunks
WHERE embedded_at IS NOT NULL
  AND 1 - (embedding <=> %s) >= %s
ORDER BY embedding <=> %s
LIMIT %s
"""


@dataclass
class ChunkMatch:
    chunk_id: str
    document_id: str
    source_file: str
    section: str | None
    chunk_index: int
    content: str
    token_count: int
    embedding_model: str | None
    similarity: float


def upsert_chunks(
    conn: "psycopg.Connection",
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    model: str,
) -> int:
    """
    Upsert chunk rows with their embeddings.

    Args:
        conn:       Open psycopg3 connection with vector registered.
        chunks:     Chunk dicts from all_chunks.json (Phase 1 output).
        embeddings: Parallel list of 1536-d vectors.
        model:      Name of the embedding model used.

    Returns:
        Number of rows inserted or updated.
    """
    assert len(chunks) == len(embeddings), "chunks and embeddings must be same length"
    now = datetime.now(timezone.utc)

    rows = [
        (
            chunk["chunk_id"],
            chunk["document_id"],
            chunk["source_file"],
            chunk.get("section"),
            chunk["chunk_index"],
            chunk["content"],
            chunk["token_count"],
            chunk["doc_hash"],
            embeddings[i],          # psycopg + pgvector accepts list[float]
            model,
            now,
            json.dumps(chunk.get("metadata", {})),
        )
        for i, chunk in enumerate(chunks)
    ]

    with conn.transaction():
        conn.executemany(_UPSERT_SQL, rows)

    logger.debug("Upserted %d chunks into PostgreSQL", len(rows))
    return len(rows)


def search_similar(
    conn: "psycopg.Connection",
    query_embedding: list[float],
    top_k: int = 10,
    similarity_threshold: float | None = None,
) -> list[ChunkMatch]:
    """
    Find the top-k most similar chunks to a query vector.

    Args:
        conn:                Open psycopg3 connection with vector registered.
        query_embedding:     1536-d query vector.
        top_k:               Maximum number of results.
        similarity_threshold: If set, only return chunks with
                              cosine_similarity >= threshold.

    Returns:
        List of ChunkMatch sorted by similarity descending.
    """
    if similarity_threshold is not None:
        rows = conn.execute(
            _SEARCH_WITH_THRESHOLD_SQL,
            (query_embedding, query_embedding, similarity_threshold,
             query_embedding, top_k),
        ).fetchall()
    else:
        rows = conn.execute(
            _SEARCH_SQL,
            (query_embedding, query_embedding, top_k),
        ).fetchall()

    return [
        ChunkMatch(
            chunk_id=row[0],
            document_id=row[1],
            source_file=row[2],
            section=row[3],
            chunk_index=row[4],
            content=row[5],
            token_count=row[6],
            embedding_model=row[7],
            similarity=float(row[8]),
        )
        for row in rows
    ]


def count_chunks(conn: "psycopg.Connection") -> dict[str, int]:
    """Return total chunks and count with embeddings."""
    total = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    embedded = conn.execute(
        "SELECT count(*) FROM chunks WHERE embedded_at IS NOT NULL"
    ).fetchone()[0]
    return {"total": total, "embedded": embedded}
