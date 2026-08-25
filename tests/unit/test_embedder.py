"""
Unit tests for src/vector/embedder.py.

No OpenAI API key required — the real embed_texts() is tested with a mock
OpenAI client; mock_embed_texts() needs no client at all.
"""

import math
import pytest
from unittest.mock import MagicMock, patch

from src.vector.embedder import (
    DEFAULT_MODEL,
    EMBEDDING_DIM,
    CostEstimate,
    embed_texts,
    estimate_cost,
    mock_embed_texts,
)


# ── estimate_cost ─────────────────────────────────────────────────────────────

class TestEstimateCost:
    def _chunks(self, token_counts: list[int]) -> list[dict]:
        return [{"token_count": t} for t in token_counts]

    def test_returns_cost_estimate(self):
        result = estimate_cost(self._chunks([500, 300]), DEFAULT_MODEL)
        assert isinstance(result, CostEstimate)

    def test_total_tokens_summed(self):
        result = estimate_cost(self._chunks([100, 200, 300]), DEFAULT_MODEL)
        assert result.total_tokens == 600

    def test_chunk_count_correct(self):
        result = estimate_cost(self._chunks([100, 100]), DEFAULT_MODEL)
        assert result.chunk_count == 2

    def test_cost_nonzero_for_nonzero_tokens(self):
        result = estimate_cost(self._chunks([1_000_000]), DEFAULT_MODEL)
        assert result.estimated_cost_usd > 0.0

    def test_small_price_for_embedding_3_small(self):
        # 1M tokens at $0.02/M = $0.02
        result = estimate_cost(self._chunks([1_000_000]), "text-embedding-3-small")
        assert abs(result.estimated_cost_usd - 0.02) < 0.001

    def test_higher_price_for_large_model(self):
        chunks = self._chunks([100_000])
        small = estimate_cost(chunks, "text-embedding-3-small")
        large = estimate_cost(chunks, "text-embedding-3-large")
        assert large.estimated_cost_usd > small.estimated_cost_usd

    def test_empty_chunks_zero_cost(self):
        result = estimate_cost([], DEFAULT_MODEL)
        assert result.total_tokens == 0
        assert result.estimated_cost_usd == 0.0
        assert result.chunk_count == 0

    def test_str_representation_includes_model(self):
        result = estimate_cost(self._chunks([500]), DEFAULT_MODEL)
        assert DEFAULT_MODEL in str(result)

    def test_missing_token_count_treated_as_zero(self):
        chunks = [{"content": "no token_count field"}]
        result = estimate_cost(chunks, DEFAULT_MODEL)
        assert result.total_tokens == 0


# ── mock_embed_texts ──────────────────────────────────────────────────────────

class TestMockEmbedTexts:
    def test_returns_one_embedding_per_text(self):
        embeddings = mock_embed_texts(["hello", "world", "foo"])
        assert len(embeddings) == 3

    def test_each_embedding_has_correct_dimension(self):
        embeddings = mock_embed_texts(["test"], dim=1536)
        assert len(embeddings[0]) == 1536

    def test_custom_dimension(self):
        embeddings = mock_embed_texts(["test"], dim=768)
        assert len(embeddings[0]) == 768

    def test_embeddings_are_unit_norm(self):
        embeddings = mock_embed_texts(["a", "b", "c"], dim=64)
        for emb in embeddings:
            norm = math.sqrt(sum(x * x for x in emb))
            assert abs(norm - 1.0) < 1e-6, f"Norm {norm} is not ~1.0"

    def test_deterministic_with_seed(self):
        e1 = mock_embed_texts(["hello"], seed=42)
        e2 = mock_embed_texts(["hello"], seed=42)
        assert e1 == e2

    def test_different_seeds_produce_different_embeddings(self):
        e1 = mock_embed_texts(["hello"], seed=1)
        e2 = mock_embed_texts(["hello"], seed=2)
        assert e1 != e2

    def test_empty_list(self):
        assert mock_embed_texts([]) == []

    def test_all_floats(self):
        embeddings = mock_embed_texts(["test"], dim=8)
        for val in embeddings[0]:
            assert isinstance(val, float)


# ── embed_texts (with mocked OpenAI client) ───────────────────────────────────

def _make_mock_client(embedding_dim: int = 1536, num_inputs: int = 1):
    """Build a mock OpenAI client that returns `num_inputs` fake embeddings."""
    fake_embedding = [0.1] * embedding_dim
    embedding_obj = MagicMock()
    embedding_obj.embedding = fake_embedding

    response = MagicMock()
    response.data = [MagicMock(embedding=fake_embedding) for _ in range(num_inputs)]

    client = MagicMock()
    client.embeddings.create.return_value = response
    return client, fake_embedding


class TestEmbedTexts:
    def test_returns_one_embedding_per_text(self):
        client, _ = _make_mock_client(num_inputs=3)
        client.embeddings.create.return_value.data = [
            MagicMock(embedding=[0.1] * 1536) for _ in range(3)
        ]
        result = embed_texts(client, ["a", "b", "c"])
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        client, _ = _make_mock_client()
        result = embed_texts(client, [])
        assert result == []
        client.embeddings.create.assert_not_called()

    def test_passes_model_to_api(self):
        client, _ = _make_mock_client(num_inputs=1)
        embed_texts(client, ["hello"], model="text-embedding-3-large")
        call_kwargs = client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-large"

    def test_single_batch_when_below_batch_size(self):
        client, _ = _make_mock_client(num_inputs=5)
        client.embeddings.create.return_value.data = [
            MagicMock(embedding=[0.1] * 1536) for _ in range(5)
        ]
        embed_texts(client, ["t"] * 5, batch_size=10)
        assert client.embeddings.create.call_count == 1

    def test_multiple_batches_when_above_batch_size(self):
        texts = ["t"] * 7
        client = MagicMock()
        # Return different number of embeddings per batch: 4 then 3
        def side_effect(**kwargs):
            n = len(kwargs["input"])
            response = MagicMock()
            response.data = [MagicMock(embedding=[0.1] * 1536) for _ in range(n)]
            return response
        client.embeddings.create.side_effect = side_effect
        result = embed_texts(client, texts, batch_size=4)
        assert client.embeddings.create.call_count == 2
        assert len(result) == 7

    def test_preserves_order_across_batches(self):
        texts = [f"text_{i}" for i in range(6)]
        embeddings_by_text = {t: [float(i)] * 1536 for i, t in enumerate(texts)}

        def side_effect(**kwargs):
            batch_texts = kwargs["input"]
            response = MagicMock()
            response.data = [
                MagicMock(embedding=embeddings_by_text[t]) for t in batch_texts
            ]
            return response

        client = MagicMock()
        client.embeddings.create.side_effect = side_effect
        result = embed_texts(client, texts, batch_size=3)
        for i, emb in enumerate(result):
            assert emb[0] == float(i), f"Embedding at index {i} is out of order"
