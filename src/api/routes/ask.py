"""
POST /ask endpoint — user-isolated corpus.

Every authenticated user owns their own pipeline.  On serverless deployments
chunks are loaded from the user_corpus DB table.  On local dev the same table
lives in SQLite, with a file-based fallback for backward compatibility.
There is NO fallback to the global corpus.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.api.schemas import AskRequest, AskResponse, CitationOut
from src.auth.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.observability.metrics import REQUEST_ERRORS, REQUEST_TOTAL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])


def _get_user_pipeline(request: Request, user: User, db: Session):
    """
    Return the per-user AnswerPipeline, building it lazily.

    Load order:
      1. In-memory cache (app.state.user_pipelines) — fastest, warm invocation
      2. DB (user_corpus table) — serverless-safe, survives cold starts
      3. Filesystem (output/users/{user_id}/) — local-dev fallback only
    """
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.auth.models import UserCorpus
    from src.config import settings
    from src.router.pipeline import load_entity_index

    user_pipelines: dict = getattr(request.app.state, "user_pipelines", {})
    if user.id in user_pipelines:
        return user_pipelines[user.id]

    chunks: list = []
    entity_index: dict = {}

    # DB-first — works on serverless (PostgreSQL) and local (SQLite)
    corpus_row = db.query(UserCorpus).filter(UserCorpus.user_id == user.id).first()
    if corpus_row:
        chunks = corpus_row.chunks or []
        entity_index = corpus_row.entity_index or {}
    else:
        # File fallback — local dev only, pre-DB migration
        base = Path(settings.temp_dir) if settings.temp_dir else Path(settings.output_dir)
        user_output = base / "users" / user.id
        chunks_path = user_output / "all_chunks.json"
        entities_path = user_output / "resolved_entities.json"
        chunks = load_chunks(chunks_path) if chunks_path.exists() else []
        entity_index = load_entity_index(entities_path) if entities_path.exists() else {}

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
    logger.info("Built pipeline for user %s with %d chunks", user.id, len(chunks))
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
    db: Session = Depends(get_db),
) -> AskResponse:
    pipeline = _get_user_pipeline(request, current_user, db)

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
