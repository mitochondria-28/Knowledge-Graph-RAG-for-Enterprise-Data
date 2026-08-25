"""
Vector (semantic) retriever — wraps pgvector similarity search.

Embeds the question text, then uses cosine distance (<=>)
to find the nearest chunk embeddings in PostgreSQL.

REQUIREMENTS:
  - PostgreSQL running (docker compose up -d postgres)
  - Chunks embedded via Phase 5 (scripts/embed_chunks.py --mock-embeddings)
  - POSTGRES_URL in .env

EMBEDDING FUNCTION:

The retriever accepts any callable (list[str]) → list[list[float]].
In production, this is an OpenAI client.
In evaluation / testing, it's mock_embed_texts() from Phase 5.
This separation means metric tests don't need a real embedding API.
"""

import time
from typing import Callable

from src.evaluation.models import EvalQuestion, RetrievalResult
from src.evaluation.retriever_base import BaseRetriever


class VectorRetriever(BaseRetriever):
    """
    Semantic similarity retriever using pgvector.

    Args:
        conn:      Open psycopg3 connection (with vector registered).
        embed_fn:  Callable: list[str] → list[list[float]].
                   Called with a single-element list for each query.
    """

    def __init__(self, conn, embed_fn: Callable[[list[str]], list[list[float]]]) -> None:
        self._conn = conn
        self._embed_fn = embed_fn

    @property
    def name(self) -> str:
        return "vector"

    def retrieve(self, question: EvalQuestion, k: int) -> RetrievalResult:
        from src.vector.store import search_similar

        start = time.perf_counter()

        # Embed the question text
        embeddings = self._embed_fn([question.question])
        query_vec = embeddings[0]

        # Cosine similarity search
        matches = search_similar(self._conn, query_vec, top_k=k)
        chunk_ids = [m.chunk_id for m in matches]

        elapsed_ms = (time.perf_counter() - start) * 1000
        return RetrievalResult(
            qid=question.qid,
            retriever=self.name,
            retrieved_chunk_ids=chunk_ids,
            latency_ms=elapsed_ms,
        )
