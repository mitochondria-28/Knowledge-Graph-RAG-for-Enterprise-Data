"""
Unit tests for src/evaluation/metrics.py.

Every metric function is pure (no side effects, no I/O) so these tests
are fast and deterministic. They form the numeric foundation of the
evaluation framework — if these are wrong, every comparison is wrong.
"""

import pytest
from src.evaluation.metrics import (
    f1_at_k,
    macro_average,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


# ── precision_at_k ────────────────────────────────────────────────────────────

class TestPrecisionAtK:
    def test_perfect_precision(self):
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, k=3) == pytest.approx(1.0)

    def test_zero_precision(self):
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, k=3) == pytest.approx(0.0)

    def test_partial_precision(self):
        retrieved = ["a", "x", "b", "y", "c"]
        relevant = {"a", "b", "c"}
        # At k=5: 3 hits / 5 = 0.6
        assert precision_at_k(retrieved, relevant, k=5) == pytest.approx(0.6)

    def test_precision_only_considers_top_k(self):
        # c is relevant but at position 6, outside k=5 window
        retrieved = ["a", "x", "y", "z", "w", "c"]
        relevant = {"a", "c"}
        # At k=5: only "a" is in top-5 and relevant → 1/5 = 0.2
        assert precision_at_k(retrieved, relevant, k=5) == pytest.approx(0.2)

    def test_k_zero_returns_zero(self):
        assert precision_at_k(["a", "b"], {"a"}, k=0) == pytest.approx(0.0)

    def test_empty_retrieved(self):
        assert precision_at_k([], {"a", "b"}, k=5) == pytest.approx(0.0)

    def test_retrieved_shorter_than_k(self):
        # Only 2 retrieved but k=5: denominator is still k, not len(retrieved)
        retrieved = ["a", "b"]
        relevant = {"a", "b"}
        assert precision_at_k(retrieved, relevant, k=5) == pytest.approx(2 / 5)

    def test_all_relevant_at_k1(self):
        retrieved = ["a", "x", "y"]
        relevant = {"a"}
        assert precision_at_k(retrieved, relevant, k=1) == pytest.approx(1.0)

    def test_not_relevant_at_k1(self):
        retrieved = ["x", "a", "y"]
        relevant = {"a"}
        assert precision_at_k(retrieved, relevant, k=1) == pytest.approx(0.0)


# ── recall_at_k ───────────────────────────────────────────────────────────────

class TestRecallAtK:
    def test_perfect_recall(self):
        retrieved = ["a", "b", "c", "x", "y"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(1.0)

    def test_zero_recall(self):
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert recall_at_k(retrieved, relevant, k=3) == pytest.approx(0.0)

    def test_partial_recall(self):
        retrieved = ["a", "x", "y", "z", "w"]
        relevant = {"a", "b", "c"}
        # Only "a" found in top-5 → 1/3
        assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(1 / 3)

    def test_empty_relevant_returns_zero(self):
        assert recall_at_k(["a", "b"], set(), k=5) == pytest.approx(0.0)

    def test_recall_ignores_positions_beyond_k(self):
        retrieved = ["x", "y", "a", "b", "c", "EXTRA_RELEVANT"]
        relevant = {"a", "b", "c", "EXTRA_RELEVANT"}
        # At k=5: a, b, c are found but EXTRA_RELEVANT is at position 6
        assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(3 / 4)

    def test_single_relevant_found_at_rank_1(self):
        retrieved = ["a", "x", "y"]
        relevant = {"a"}
        assert recall_at_k(retrieved, relevant, k=5) == pytest.approx(1.0)


# ── f1_at_k ───────────────────────────────────────────────────────────────────

class TestF1AtK:
    def test_perfect_f1(self):
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert f1_at_k(retrieved, relevant, k=3) == pytest.approx(1.0)

    def test_zero_f1_no_hits(self):
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert f1_at_k(retrieved, relevant, k=3) == pytest.approx(0.0)

    def test_f1_harmonic_mean(self):
        # P@5 = 2/5, R@5 = 2/2 = 1.0 → F1 = 2*0.4*1.0/(0.4+1.0)
        retrieved = ["a", "x", "b", "y", "z"]
        relevant = {"a", "b"}
        p = 2 / 5
        r = 2 / 2
        expected = 2 * p * r / (p + r)
        assert f1_at_k(retrieved, relevant, k=5) == pytest.approx(expected)

    def test_zero_precision_and_recall_returns_zero(self):
        assert f1_at_k([], set(), k=5) == pytest.approx(0.0)


# ── reciprocal_rank ───────────────────────────────────────────────────────────

class TestReciprocalRank:
    def test_first_result_is_relevant(self):
        retrieved = ["a", "b", "c"]
        relevant = {"a"}
        assert reciprocal_rank(retrieved, relevant) == pytest.approx(1.0)

    def test_second_result_is_relevant(self):
        retrieved = ["x", "a", "b"]
        relevant = {"a"}
        assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)

    def test_third_result_is_relevant(self):
        retrieved = ["x", "y", "a"]
        relevant = {"a"}
        assert reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 3)

    def test_no_relevant_result(self):
        retrieved = ["x", "y", "z"]
        relevant = {"a"}
        assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.0)

    def test_empty_retrieved(self):
        assert reciprocal_rank([], {"a"}) == pytest.approx(0.0)

    def test_empty_relevant(self):
        assert reciprocal_rank(["a", "b"], set()) == pytest.approx(0.0)

    def test_first_of_many_relevant(self):
        # Multiple relevant — we only care about the rank of the FIRST hit
        retrieved = ["x", "a", "b"]
        relevant = {"a", "b"}
        # "a" is at rank 2 → RR = 0.5
        assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)


# ── macro_average ─────────────────────────────────────────────────────────────

class TestMacroAverage:
    def test_simple_average(self):
        assert macro_average([0.4, 0.6, 0.8]) == pytest.approx(0.6)

    def test_empty_list_returns_zero(self):
        assert macro_average([]) == pytest.approx(0.0)

    def test_single_value(self):
        assert macro_average([0.75]) == pytest.approx(0.75)

    def test_all_zeros(self):
        assert macro_average([0.0, 0.0, 0.0]) == pytest.approx(0.0)

    def test_all_ones(self):
        assert macro_average([1.0, 1.0, 1.0]) == pytest.approx(1.0)


# ── Integration: end-to-end evaluation scenario ───────────────────────────────

class TestEndToEnd:
    """Simulate a mini evaluation over 3 questions to verify metric pipeline."""

    def test_good_retriever_scores_higher(self):
        """A retriever that finds relevant chunks should outscore one that does not."""
        relevant_1 = {"c1", "c2"}
        relevant_2 = {"c3"}
        relevant_3 = {"c4", "c5"}

        # Good retriever: hits the relevant chunk first each time
        good_results = [
            (["c1", "c2", "x", "y", "z"], relevant_1),
            (["c3", "x", "y", "z", "w"], relevant_2),
            (["c4", "c5", "x", "y", "z"], relevant_3),
        ]
        # Bad retriever: misses or ranks relevant chunks low
        bad_results = [
            (["x", "y", "z", "c1", "c2"], relevant_1),  # relevant at end
            (["x", "y", "z", "w", "v"], relevant_2),    # miss
            (["x", "c4", "y", "z", "w"], relevant_3),   # partial, low rank
        ]

        good_f1s = [f1_at_k(r, rel, 5) for r, rel in good_results]
        bad_f1s  = [f1_at_k(r, rel, 5) for r, rel in bad_results]
        good_mrrs = [reciprocal_rank(r, rel) for r, rel in good_results]
        bad_mrrs  = [reciprocal_rank(r, rel) for r, rel in bad_results]

        assert macro_average(good_f1s) > macro_average(bad_f1s)
        assert macro_average(good_mrrs) > macro_average(bad_mrrs)

    def test_vector_should_beat_keyword_on_semantic_question(self):
        """
        Keyword retrieval fails when query words don't appear in chunk text.
        (Simulated: keyword retriever misses, vector retriever hits.)
        """
        relevant = {"chunk-semantic"}
        # Keyword: no token overlap → miss
        keyword_retrieved = ["chunk-unrelated-1", "chunk-unrelated-2"]
        # Vector: semantic match → hit
        vector_retrieved = ["chunk-semantic", "chunk-unrelated-1"]

        assert f1_at_k(keyword_retrieved, relevant, 5) == pytest.approx(0.0)
        assert f1_at_k(vector_retrieved, relevant, 5) > 0.0
