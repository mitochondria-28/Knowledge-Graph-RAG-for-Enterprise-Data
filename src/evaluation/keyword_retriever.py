"""
Keyword (bag-of-words) retriever — the baseline.

WHY A KEYWORD BASELINE:

Before comparing vector vs. graph, we need to show that both are better
than the simplest possible approach. Keyword matching is that baseline:
it requires no model, no database, no embeddings — just the chunk text.

ALGORITHM:

  1. Tokenize query and chunk content (lowercase, whitespace split)
  2. Remove English stopwords (very common words that carry no meaning)
  3. Score each chunk: |query_tokens ∩ chunk_tokens|
  4. Return top-k by score, with ties broken by chunk_index (document order)

This is essentially unigram BM25 without the IDF weighting. It gets simple
entity questions right ("StellarDB" appears in StellarDB docs) but fails
on:
  - Paraphrase questions ("What is the database system TechNova uses?" →
    doesn't contain the word "StellarDB")
  - Multi-hop questions (no single chunk mentions all 3-hop entities)

Seeing keyword retriever fail on these cases motivates both vector and graph
retrievers.

RUNS WITHOUT ANY DATABASE OR API KEY.
"""

import time
from collections import defaultdict

from src.evaluation.models import EvalQuestion, RetrievalResult
from src.evaluation.retriever_base import BaseRetriever

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "and", "or", "but", "if", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "up", "about", "into", "through", "during",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "how", "when", "where", "why", "than", "then", "so", "yet", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "too", "very", "just", "because", "as",
    "its", "their", "his", "her", "it", "he", "she", "they", "we", "you",
    "i", "me", "him", "us", "them", "my", "your", "our",
})


def _tokenize(text: str) -> set[str]:
    tokens = set(text.lower().split())
    return tokens - _STOPWORDS


class KeywordRetriever(BaseRetriever):
    """
    Bag-of-words overlap scorer over pre-loaded chunk content.
    No database or API key required.
    """

    def __init__(self, chunks: list[dict]) -> None:
        """
        Args:
            chunks: List of chunk dicts from all_chunks.json.
                    Must contain 'chunk_id', 'content', 'chunk_index'.
        """
        self._chunks = chunks
        # Pre-tokenize all chunks once at init
        self._chunk_tokens: list[set[str]] = [
            _tokenize(c["content"]) for c in chunks
        ]

    @property
    def name(self) -> str:
        return "keyword"

    def retrieve(self, question: EvalQuestion, k: int) -> RetrievalResult:
        start = time.perf_counter()
        q_tokens = _tokenize(question.question)

        if not q_tokens:
            return RetrievalResult(
                qid=question.qid,
                retriever=self.name,
                retrieved_chunk_ids=[],
                latency_ms=0.0,
            )

        # Score = token overlap count
        scores = [
            len(q_tokens & chunk_tokens)
            for chunk_tokens in self._chunk_tokens
        ]

        # Sort by score desc, then by chunk_index asc (document order tie-break)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: (-scores[i], self._chunks[i].get("chunk_index", 0)),
        )

        top_k_ids = [
            self._chunks[i]["chunk_id"]
            for i in ranked_indices[:k]
            if scores[i] > 0  # only return chunks with at least one matching token
        ]

        elapsed_ms = (time.perf_counter() - start) * 1000
        return RetrievalResult(
            qid=question.qid,
            retriever=self.name,
            retrieved_chunk_ids=top_k_ids,
            latency_ms=elapsed_ms,
        )
