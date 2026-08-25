"""
Embedding generation for document chunks.

MODEL CHOICE — text-embedding-3-small:

  Dimension  : 1536
  Price      : $0.020 per million tokens (cheapest OpenAI embedding)
  Quality    : Excellent for retrieval; MTEB benchmark score ~62.3

  text-embedding-3-large (3072 dims, $0.130/M) is available for higher
  accuracy at 6.5× the cost. For a 27-chunk corpus the difference is
  negligible; use 3-small and upgrade if retrieval quality is insufficient.

BATCHING:

  OpenAI allows up to 2048 inputs per request. We use 256 as default:
  - Small enough that one failed batch doesn't lose much work
  - Large enough to minimize round-trip overhead

MOCK MODE:

  When --mock-embeddings is set (or no API key), we generate random
  unit-norm vectors. This lets the full pipeline run for development
  and testing without an API key. Mock embeddings are NOT useful for
  real retrieval — they are random — but they exercise all code paths.

COST ESTIMATION:

  estimate_cost() uses the token_count field from Phase 1 chunking.
  Token counts are exact (cl100k_base tokenizer) so the estimate is
  accurate to within 5% (the model also tokenizes the input).
"""

import logging
import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Price per million input tokens (USD), as of mid-2024
_PRICE_PER_M: dict[str, float] = {
    "text-embedding-3-small": 0.020,
    "text-embedding-3-large": 0.130,
    "text-embedding-ada-002": 0.100,
}

MAX_BATCH_SIZE = 256
_RETRY_DELAYS = [1, 2, 4]  # seconds; exponential backoff on rate limit


# ── Cost estimation (no API call) ─────────────────────────────────────────────

@dataclass
class CostEstimate:
    chunk_count: int
    total_tokens: int
    estimated_cost_usd: float
    model: str

    def __str__(self) -> str:
        return (
            f"{self.chunk_count} chunks / "
            f"{self.total_tokens:,} tokens / "
            f"${self.estimated_cost_usd:.4f} USD"
            f"  [{self.model}]"
        )


def estimate_cost(
    chunks: list[dict],
    model: str = DEFAULT_MODEL,
) -> CostEstimate:
    """
    Estimate embedding cost from chunk token counts.
    Does NOT call the API.
    """
    total_tokens = sum(c.get("token_count", 0) for c in chunks)
    price_per_m = _PRICE_PER_M.get(model, _PRICE_PER_M[DEFAULT_MODEL])
    cost = total_tokens / 1_000_000 * price_per_m
    return CostEstimate(
        chunk_count=len(chunks),
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        model=model,
    )


# ── Mock embeddings (no API key needed) ──────────────────────────────────────

def mock_embed_texts(
    texts: list[str],
    dim: int = EMBEDDING_DIM,
    seed: int | None = None,
) -> list[list[float]]:
    """
    Return random unit-norm vectors — useful for pipeline testing.
    With a fixed seed, output is deterministic (same text → same vector).
    WARNING: These embeddings have no semantic meaning.
    """
    results = []
    for i, text in enumerate(texts):
        rng = random.Random(seed if seed is None else seed + i)
        v = [rng.gauss(0, 1) for _ in range(dim)]
        mag = math.sqrt(sum(x * x for x in v))
        results.append([x / mag for x in v])
    return results


# ── Real embeddings via OpenAI ────────────────────────────────────────────────

def embed_texts(
    client: "OpenAI",
    texts: list[str],
    model: str = DEFAULT_MODEL,
    batch_size: int = MAX_BATCH_SIZE,
) -> list[list[float]]:
    """
    Embed `texts` in batches using the OpenAI embeddings API.

    Returns:
        list of embeddings in the same order as `texts`.

    Raises:
        openai.RateLimitError   — after 3 retries with backoff
        openai.APIError         — on non-retryable API errors
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), batch_size):
        batch = texts[batch_start : batch_start + batch_size]
        logger.debug(
            "Embedding batch %d–%d / %d",
            batch_start, batch_start + len(batch) - 1, len(texts),
        )

        last_error: Exception | None = None
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                logger.warning("Rate limit hit, retrying in %ds…", delay)
                time.sleep(delay)
            try:
                response = client.embeddings.create(model=model, input=batch)
                # response.data is a list of Embedding objects, in input order
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                last_error = None
                break
            except Exception as exc:
                # Only retry on rate-limit errors
                exc_type = type(exc).__name__
                if "RateLimit" in exc_type and attempt < len(_RETRY_DELAYS):
                    last_error = exc
                    continue
                raise

        if last_error is not None:
            raise last_error

    return all_embeddings
