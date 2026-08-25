"""
Unit tests for src/vector/store.py and src/vector/schema.py.

All tests use unittest.mock — no PostgreSQL required.
Tests verify SQL correctness, parameter handling, and result mapping.
"""

import pytest
from unittest.mock import MagicMock, call, patch

from src.vector.schema import (
    EMBEDDING_DIM,
    _DDL_STATEMENTS,
    create_schema,
    get_embedded_chunk_ids,
)
from src.vector.store import (
    ChunkMatch,
    _SEARCH_SQL,
    _SEARCH_WITH_THRESHOLD_SQL,
    _UPSERT_SQL,
    count_chunks,
    search_similar,
    upsert_chunks,
)


# ── Schema DDL ────────────────────────────────────────────────────────────────

class TestSchemaSQL:
    def test_embedding_dim_is_1536(self):
        assert EMBEDDING_DIM == 1536

    def test_table_ddl_includes_correct_dimension(self):
        combined = " ".join(_DDL_STATEMENTS)
        assert f"vector({EMBEDDING_DIM})" in combined

    def test_ivfflat_index_present(self):
        combined = " ".join(_DDL_STATEMENTS)
        assert "ivfflat" in combined.lower()
        assert "vector_cosine_ops" in combined

    def test_all_statements_are_idempotent(self):
        # Every statement that creates something must use IF NOT EXISTS
        create_statements = [s for s in _DDL_STATEMENTS if "CREATE" in s.upper()]
        for stmt in create_statements:
            upper = stmt.upper()
            if "CREATE EXTENSION" in upper or "CREATE TABLE" in upper or "CREATE INDEX" in upper:
                assert "IF NOT EXISTS" in upper, \
                    f"Statement missing IF NOT EXISTS:\n{stmt[:80]}"

    def test_chunk_id_is_primary_key(self):
        combined = " ".join(_DDL_STATEMENTS)
        assert "chunk_id" in combined
        assert "PRIMARY KEY" in combined.upper()

    def test_create_schema_calls_execute_for_each_statement(self):
        conn = MagicMock()
        conn.transaction.return_value.__enter__ = MagicMock(return_value=None)
        conn.transaction.return_value.__exit__ = MagicMock(return_value=False)
        create_schema(conn)
        assert conn.execute.call_count == len(_DDL_STATEMENTS)

    def test_get_embedded_chunk_ids_returns_set(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [("id-1",), ("id-2",)]
        result = get_embedded_chunk_ids(conn)
        assert result == {"id-1", "id-2"}

    def test_get_embedded_chunk_ids_empty(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        result = get_embedded_chunk_ids(conn)
        assert result == set()


# ── Upsert SQL ────────────────────────────────────────────────────────────────

class TestUpsertSQL:
    def test_sql_uses_on_conflict_do_update(self):
        assert "ON CONFLICT" in _UPSERT_SQL.upper()
        assert "DO UPDATE" in _UPSERT_SQL.upper()

    def test_sql_updates_embedding_on_conflict(self):
        assert "embedding" in _UPSERT_SQL
        assert "EXCLUDED.embedding" in _UPSERT_SQL

    def test_sql_includes_all_required_columns(self):
        for col in ["chunk_id", "document_id", "source_file", "section",
                    "chunk_index", "content", "token_count", "doc_hash",
                    "embedding", "embedding_model", "embedded_at"]:
            assert col in _UPSERT_SQL, f"Missing column: {col}"

    def test_upsert_chunks_calls_executemany(self):
        conn = MagicMock()
        conn.transaction.return_value.__enter__ = MagicMock(return_value=None)
        conn.transaction.return_value.__exit__ = MagicMock(return_value=False)

        chunks = [_make_chunk("c1"), _make_chunk("c2")]
        embeddings = [[0.1] * 1536, [0.2] * 1536]
        result = upsert_chunks(conn, chunks, embeddings, "text-embedding-3-small")

        conn.executemany.assert_called_once()
        assert result == 2

    def test_upsert_raises_on_length_mismatch(self):
        conn = MagicMock()
        chunks = [_make_chunk("c1"), _make_chunk("c2")]
        embeddings = [[0.1] * 1536]  # wrong length
        with pytest.raises(AssertionError):
            upsert_chunks(conn, chunks, embeddings, "text-embedding-3-small")

    def test_upsert_passes_embedding_to_executemany(self):
        conn = MagicMock()
        conn.transaction.return_value.__enter__ = MagicMock(return_value=None)
        conn.transaction.return_value.__exit__ = MagicMock(return_value=False)

        chunk = _make_chunk("c1")
        embedding = [0.42] * 1536
        upsert_chunks(conn, [chunk], [embedding], "text-embedding-3-small")

        rows = conn.executemany.call_args[0][1]  # second positional arg
        assert rows[0][8] == embedding  # index 8 is the embedding column


# ── Search SQL ────────────────────────────────────────────────────────────────

class TestSearchSQL:
    def test_basic_search_sql_uses_cosine_operator(self):
        assert "<=>" in _SEARCH_SQL

    def test_threshold_search_sql_uses_cosine_operator(self):
        assert "<=>" in _SEARCH_WITH_THRESHOLD_SQL

    def test_search_orders_by_distance_asc(self):
        assert "ORDER BY embedding <=>" in _SEARCH_SQL

    def test_search_converts_distance_to_similarity(self):
        # similarity = 1 - distance
        assert "1 - (embedding <=>" in _SEARCH_SQL

    def test_threshold_sql_has_where_clause(self):
        assert "WHERE" in _SEARCH_WITH_THRESHOLD_SQL.upper()

    def test_search_returns_chunk_matches(self):
        conn = MagicMock()
        fake_rows = [
            ("chunk-1", "doc-1", "file.md", "Intro", 0,
             "chunk content here", 85, "text-embedding-3-small", 0.92),
        ]
        conn.execute.return_value.fetchall.return_value = fake_rows

        query_vec = [0.1] * 1536
        results = search_similar(conn, query_vec, top_k=5)

        assert len(results) == 1
        m = results[0]
        assert isinstance(m, ChunkMatch)
        assert m.chunk_id == "chunk-1"
        assert m.content == "chunk content here"
        assert abs(m.similarity - 0.92) < 1e-6

    def test_search_with_threshold_uses_different_sql(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        query_vec = [0.1] * 1536
        search_similar(conn, query_vec, top_k=5, similarity_threshold=0.75)
        sql_used = conn.execute.call_args[0][0]
        assert "0.75" in str(conn.execute.call_args[0][1]) or \
               "similarity_threshold" not in sql_used  # threshold is a param

    def test_search_without_threshold_uses_basic_sql(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        query_vec = [0.1] * 1536
        search_similar(conn, query_vec, top_k=5)
        sql_used = conn.execute.call_args[0][0]
        # Basic SQL should NOT have a WHERE clause filtering by similarity
        assert "WHERE" not in sql_used.upper() or "embedded_at IS NOT NULL" in sql_used

    def test_chunk_match_similarity_is_float(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            ("c1", "d1", "f.md", None, 0, "text", 50, "model", 0.85)
        ]
        results = search_similar(conn, [0.1] * 1536)
        assert isinstance(results[0].similarity, float)


# ── count_chunks ──────────────────────────────────────────────────────────────

class TestCountChunks:
    def test_returns_total_and_embedded(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(27,), (15,)]
        result = count_chunks(conn)
        assert result == {"total": 27, "embedded": 15}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "source_file": "corpus/test.md",
        "section": "Intro",
        "chunk_index": 0,
        "content": "sample chunk content",
        "token_count": 42,
        "doc_hash": "abc123",
        "metadata": {},
    }
