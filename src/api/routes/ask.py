"""
POST /ask endpoint — user-isolated corpus.

Every authenticated user owns their own pipeline backed exclusively by
corpus/users/{user_id}/ and output/users/{user_id}/.  There is NO fallback
to the global corpus — a new user starts with zero documents and will get an
explicit "no documents" response until they upload something.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.schemas import AskRequest, AskResponse, CitationOut
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.observability.metrics import REQUEST_ERRORS, REQUEST_TOTAL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])


def _get_user_pipeline(request: Request, user: User):
    """
    Return the cached per-user AnswerPipeline, building it lazily on first call.

    Only the user's own chunks are loaded.  If they have not uploaded anything
    yet the pipeline is built with an empty chunk list — callers must handle
    the empty-corpus case gracefully.
    """
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.config import settings
    from src.router.pipeline import load_entity_index

    user_pipelines: dict = getattr(request.app.state, "user_pipelines", {})
    if user.id in user_pipelines:
        return user_pipelines[user.id]

    user_output = Path(settings.output_dir) / "users" / user.id
    chunks_path  = user_output / "all_chunks.json"
    entities_path = user_output / "resolved_entities.json"

    # Strictly user-owned data — no global fallback
    chunks       = load_chunks(chunks_path) if chunks_path.exists() else []
    entity_index = (
        load_entity_index(entities_path) if entities_path.exists() else {}
    )

    generator = getattr(request.app.state, "_default_generator", None)
    if generator is None:
        from src.answer.generator import MockAnswerGenerator
        generator = MockAnswerGenerator()

    pipeline = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
    )
    user_pipelines[user.id] = pipeline
    request.app.state.user_pipelines = user_pipelines
    logger.info(
        "Built pipeline for user %s with %d chunks", user.id, len(chunks)
    )
    return pipeline


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Answer a question using the user's private knowledge base.",
    responses={
        400: {"description": "No documents uploaded yet"},
        500: {"description": "Internal pipeline error"},
    },
)
def ask(
    body: AskRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    pipeline = _get_user_pipeline(request, current_user)

    # Inform the user clearly if their corpus is empty
    if not pipeline._chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Your knowledge base is empty. "
                "Please upload at least one document before asking questions."
            ),
        )

    try:
        validated = pipeline.ask(body.question, top_k=body.top_k)
    except Exception as exc:
        REQUEST_ERRORS.labels(error_type=type(exc).__name__).inc()
        logger.exception(
            "Pipeline error for question %r (user=%s)", body.question, current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing the question.",
        ) from exc

    REQUEST_TOTAL.labels(
        status_code="200", strategy=validated.retrieval_strategy
    ).inc()

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
