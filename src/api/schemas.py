"""
Pydantic request/response schemas for the FastAPI layer — Phase 9.

WHY SEPARATE SCHEMAS FROM DOMAIN MODELS:

src/answer/models.py contains the internal pipeline's dataclasses —
they're designed for Python-to-Python use and may evolve freely.

These schemas are the public API contract. They:
  - Validate and document every incoming request field
  - Provide stable field names + types for API consumers
  - Can be versioned independently from internal models

Keeping them separate means we can rename an internal field without
breaking the API, and vice versa.
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Body for POST /ask."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The natural-language question to answer.",
        examples=["Who leads the Platform Team?"],
    )
    top_k: int = Field(
        5,
        ge=1,
        le=20,
        description="Number of chunks to retrieve as context (1–20).",
    )


class CitationOut(BaseModel):
    """One citation entry in the response, with validation status."""

    chunk_id: str = Field(description="UUID of the source chunk.")
    source_file: str = Field(description="Relative path to the source document.")
    quote: str = Field(description="Verbatim phrase from the chunk cited by the LLM.")
    is_valid: bool = Field(description="True if the quote was verified in the chunk.")
    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Match quality: 1.0=exact, 0.8–1.0=fuzzy, <0.8=not found.",
    )
    reason: str = Field(description="Human-readable validation outcome.")


class AskResponse(BaseModel):
    """Full response for POST /ask."""

    question: str
    answer: str = Field(description="Answer generated from retrieved context.")
    citations: list[CitationOut]
    citation_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of citations verified against source chunks (0–1).",
    )
    retrieval_strategy: str = Field(
        description="Routing decision: 'vector', 'graph', or 'hybrid'."
    )
    model: str = Field(description="Claude model used for generation.")
    latency_ms: float = Field(description="Generation latency in milliseconds.")
    chunk_count: int = Field(description="Number of chunks provided as context.")


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str = Field(description="Always 'ok' if the service is up.")


class ReadyResponse(BaseModel):
    """Response for GET /ready — indicates whether the pipeline is initialised."""
    status: str = Field(description="'ready' if chunks are loaded, 'not_ready' otherwise.")
    chunk_count: int = Field(description="Number of corpus chunks in memory.")
    entity_count: int = Field(description="Number of entity names/aliases in the entity index.")
    generator: str = Field(description="Generator class name (e.g. 'MockAnswerGenerator').")
