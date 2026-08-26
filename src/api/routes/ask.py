"""
POST /ask endpoint — Phase 9.

FLOW:

  1. Pydantic validates AskRequest (question non-empty, top_k in 1–20)
  2. Pipeline fetched from app.state (loaded at startup, not per-request)
  3. pipeline.ask(question, top_k) → ValidatedAnswer
  4. Response mapped to AskResponse schema

ERROR HANDLING:

  503  Pipeline not yet initialised (startup still running or failed)
  422  Invalid request body (Pydantic ValidationError — FastAPI handles automatically)
  500  Unexpected pipeline error (logged server-side, opaque message to client)

WHY NOT ASYNC:

pipeline.ask() is synchronous CPU work (routing + retrieval + Claude call).
FastAPI will run sync route handlers in a thread pool automatically, so we
don't need to wrap it in run_in_executor ourselves. Adding async here would
be wrong — it would block the event loop during the Claude HTTP call.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status

from src.api.schemas import AskRequest, AskResponse, CitationOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Answer a question using the knowledge graph RAG pipeline.",
    responses={
        503: {"description": "Pipeline not yet initialised"},
        500: {"description": "Internal pipeline error"},
    },
)
def ask(body: AskRequest, request: Request) -> AskResponse:
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline is not initialised — try again in a moment.",
        )

    try:
        validated = pipeline.ask(body.question, top_k=body.top_k)
    except Exception as exc:
        logger.exception("Pipeline error for question %r", body.question)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing the question.",
        ) from exc

    citations_out = [
        CitationOut(
            chunk_id=vr.chunk_id,
            source_file=vr.source_file,
            quote=vr.quote,
            is_valid=vr.is_valid,
            match_score=vr.match_score,
            reason=vr.reason,
        )
        for vr in validated.validation_results
    ]

    return AskResponse(
        question=validated.question,
        answer=validated.answer_text,
        citations=citations_out,
        citation_confidence=validated.citation_confidence,
        retrieval_strategy=validated.retrieval_strategy,
        model=validated.model,
        latency_ms=validated.latency_ms,
        chunk_count=validated.chunk_count,
    )
