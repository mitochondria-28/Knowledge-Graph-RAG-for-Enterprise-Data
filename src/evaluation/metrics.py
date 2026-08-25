"""
Information retrieval metrics for chunk-level evaluation.

All metrics operate on ranked lists of chunk_ids compared against a
ground-truth set of relevant chunk_ids.

PRECISION@k:
    Of the k chunks we returned, what fraction were actually relevant?
    Precision@k = |retrieved[:k] ∩ relevant| / k

    Example: retrieved=["a","b","c","d","e"], relevant={"a","c"}, k=5
    P@5 = 2/5 = 0.4

RECALL@k:
    Of all relevant chunks, how many appear in our top-k?
    Recall@k = |retrieved[:k] ∩ relevant| / |relevant|

    Example (same): R@5 = 2/2 = 1.0

F1@k:
    Harmonic mean of P@k and R@k.
    F1@k = 2 * P@k * R@k / (P@k + R@k)  if denominator > 0, else 0.0

RECIPROCAL RANK:
    1 / rank of the first relevant result (1-indexed).
    RR = 0.0 if no relevant result appears in the retrieved list.

    Example: retrieved=["b","a","c"], relevant={"a"}
    "a" is at rank 2 → RR = 1/2 = 0.5

MRR (Mean Reciprocal Rank):
    Macro-average of RR across all questions.

WHY THESE METRICS:

  Precision@k   — important when the user sees exactly k results (RAG window)
  Recall@k      — important when missing a chunk means missing the answer
  F1@k          — single number for comparing retrievers head-to-head
  MRR           — penalizes ranking a relevant chunk below irrelevant ones;
                  important for RAG because the LLM reads top chunks first
"""


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Fraction of top-k retrieved chunks that are relevant.
    Returns 0.0 if k == 0.
    """
    if k == 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for cid in top_k if cid in relevant)
    return hits / k


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """
    Fraction of relevant chunks that appear in the top-k retrieved.
    Returns 0.0 if relevant is empty (undefined recall; treat as 0).
    """
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for cid in top_k if cid in relevant)
    return hits / len(relevant)


def f1_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Harmonic mean of precision@k and recall@k."""
    p = precision_at_k(retrieved, relevant, k)
    r = recall_at_k(retrieved, relevant, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """
    1/rank of the first relevant result (1-indexed).
    Returns 0.0 if no relevant result appears.
    """
    for rank, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def macro_average(scores: list[float]) -> float:
    """Unweighted mean of a list of per-question metric values."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
