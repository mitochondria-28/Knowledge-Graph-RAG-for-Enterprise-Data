"""
Abstract base class for all retrievers.

WHY AN ABC:

The harness accepts any object that implements retrieve(). This lets us
swap retrievers freely:
  - KeywordRetriever (no DB, always works)
  - VectorRetriever  (pgvector, requires PostgreSQL + embeddings)
  - GraphRetriever   (Neo4j, requires running graph)

Tests mock this interface, so metric tests don't need any real retriever.
"""

from abc import ABC, abstractmethod

from src.evaluation.models import EvalQuestion, RetrievalResult


class BaseRetriever(ABC):
    """Common interface for keyword, vector, and graph retrievers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier used in reports (e.g. 'vector', 'graph')."""

    @abstractmethod
    def retrieve(self, question: EvalQuestion, k: int) -> RetrievalResult:
        """
        Return the top-k most relevant chunk IDs for a question.

        Args:
            question: The EvalQuestion containing the question text and hints.
            k:        Number of results to return.

        Returns:
            RetrievalResult with ranked chunk IDs and latency.
        """
