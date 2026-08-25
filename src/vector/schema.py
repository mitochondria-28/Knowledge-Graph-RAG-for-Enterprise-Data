"""
PostgreSQL schema for chunk embeddings.

TABLE DESIGN:

  chunks
  ──────
  chunk_id        TEXT PK  — stable UUID5 from Phase 1, bridges Neo4j ↔ Postgres
  document_id     TEXT     — UUID5 of the source document
  source_file     TEXT     — relative path e.g. corpus/companies/technova.md
  section         TEXT     — nearest Markdown heading at chunk position
  chunk_index     INTEGER  — position within document (0-based)
  content         TEXT     — raw chunk text for LLM context window
  token_count     INTEGER  — cl100k_base token count from Phase 1
  doc_hash        TEXT     — SHA-256 of source doc; changes when content changes
  embedding       vector(1536)   — OpenAI text-embedding-3-small output
  embedding_model TEXT     — which model produced this embedding
  embedded_at     TIMESTAMPTZ    — when embedding was generated
  metadata        JSONB    — extensible bag for future fields

VECTOR DIMENSION — why 1536:

text-embedding-3-small returns 1536-dimensional vectors. The dimension is
fixed at table creation time in the vector(1536) column declaration. Changing
it later requires ALTER TABLE + full re-embedding.

IVFFLAT INDEX — why and when it helps:

IVFFlat (Inverted File with Flat quantization) divides the vector space into
`lists` Voronoi cells. At query time it only searches the nearest `probes`
cells instead of comparing against every row — this is approximate nearest
neighbor (ANN) search.

  lists=100  — suitable for up to ~1M vectors (rule of thumb: sqrt(n))
  probes=10  — at query time; higher = more accurate, slower (default 1)

For 27 chunks, IVFFlat is slower than a sequential scan (the query planner
will likely ignore the index). The index is created here so it's in place
when the dataset grows.

NOTE: IVFFlat requires rows to exist for training. Creating it on an empty
table works but produces a suboptimal structure. In production you'd create
the index after initial bulk load.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536

_DDL_STATEMENTS = [
    # 1. Extension (requires superuser once; skipped if already installed)
    "CREATE EXTENSION IF NOT EXISTS vector",

    # 2. Main table
    f"""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id        TEXT PRIMARY KEY,
        document_id     TEXT NOT NULL,
        source_file     TEXT NOT NULL,
        section         TEXT,
        chunk_index     INTEGER NOT NULL,
        content         TEXT NOT NULL,
        token_count     INTEGER NOT NULL,
        doc_hash        TEXT NOT NULL,
        embedding       vector({EMBEDDING_DIM}),
        embedding_model TEXT,
        embedded_at     TIMESTAMPTZ,
        metadata        JSONB DEFAULT '{{}}'::jsonb
    )
    """,

    # 3. IVFFlat cosine index (ANN search)
    """
    CREATE INDEX IF NOT EXISTS chunks_embedding_cosine_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100)
    """,

    # 4. Supporting indexes for metadata filtering
    "CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id)",
    "CREATE INDEX IF NOT EXISTS chunks_source_file_idx ON chunks (source_file)",
]


def create_schema(conn: "psycopg.Connection") -> None:
    """
    Create the chunks table, vector index, and supporting indexes.
    All statements use IF NOT EXISTS — safe to call on every startup.
    """
    with conn.transaction():
        for ddl in _DDL_STATEMENTS:
            statement = ddl.strip()
            logger.debug("DDL: %s", statement.splitlines()[0])
            conn.execute(statement)
    logger.info("Vector schema ready (%d statements)", len(_DDL_STATEMENTS))


def drop_chunks_table(conn: "psycopg.Connection") -> None:
    """Drop the chunks table entirely. Used by --force flag."""
    with conn.transaction():
        conn.execute("DROP TABLE IF EXISTS chunks CASCADE")
    logger.info("Dropped chunks table")


def get_embedded_chunk_ids(conn: "psycopg.Connection") -> set[str]:
    """Return the set of chunk_ids that already have an embedding."""
    rows = conn.execute(
        "SELECT chunk_id FROM chunks WHERE embedded_at IS NOT NULL"
    ).fetchall()
    return {row[0] for row in rows}
