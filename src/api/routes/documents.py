"""
POST /documents/upload — save an uploaded file into the user's private corpus,
                         ingest it, and hot-reload their pipeline.
GET  /documents        — list every document the current user has uploaded.

Each user's files live under:
  corpus/users/{user_id}/     — raw uploads (by doc_type sub-folder)
  output/users/{user_id}/     — chunked output (all_chunks.json, documents.json …)

There is NO fallback to the global corpus.  New users start with zero documents.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.ingestion.loader import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

_TYPE_TO_DIR: dict[str, str] = {
    "company":    "companies",
    "project":    "projects",
    "technology": "technologies",
    "people":     "people",
    "general":    "general",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _user_corpus_dir(user: User) -> Path:
    from src.config import settings
    return Path(settings.corpus_dir) / "users" / user.id


def _user_output_dir(user: User) -> Path:
    from src.config import settings
    return Path(settings.output_dir) / "users" / user.id


@router.post("/upload", summary="Upload and ingest a document into the user's private corpus.")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("general"),
    current_user: User = Depends(get_current_user),
) -> dict:
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.ingestion.pipeline import run_ingestion
    from src.router.pipeline import load_entity_index

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            ),
        )

    # Save file into user's own corpus directory
    folder   = _TYPE_TO_DIR.get(doc_type, "general")
    corpus_dir = _user_corpus_dir(current_user)
    dest_dir   = corpus_dir / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path  = dest_dir / file.filename

    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB upload limit.",
        )

    dest_path.write_bytes(contents)
    logger.info(
        "Saved upload for user %s: %s (%d bytes)",
        current_user.id, dest_path, len(contents),
    )

    # Run ingestion into user's own output directory
    output_dir = _user_output_dir(current_user)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        stats = run_ingestion(corpus_dir=corpus_dir, output_dir=output_dir)
    except Exception as exc:
        logger.exception(
            "Ingestion failed for user %s, file %s", current_user.id, dest_path
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc

    # Rebuild the user's pipeline from the freshly ingested chunks
    chunks_path   = output_dir / "all_chunks.json"
    entities_path = output_dir / "resolved_entities.json"
    chunks        = load_chunks(chunks_path) if chunks_path.exists() else []
    entity_index  = (
        load_entity_index(entities_path) if entities_path.exists() else {}
    )

    generator = getattr(request.app.state, "_default_generator", None)
    if generator is None:
        from src.answer.generator import MockAnswerGenerator
        generator = MockAnswerGenerator()

    user_pipelines: dict = getattr(request.app.state, "user_pipelines", {})
    user_pipelines[current_user.id] = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
    )
    request.app.state.user_pipelines = user_pipelines

    logger.info(
        "Pipeline rebuilt for user %s: %d chunks", current_user.id, len(chunks)
    )

    return {
        "filename": file.filename,
        "doc_type": doc_type,
        "stats":    stats,
    }


@router.get("", summary="List documents uploaded by the current user.")
def list_documents(current_user: User = Depends(get_current_user)) -> list[dict]:
    """Returns only documents this user uploaded. New users receive an empty list."""
    index_path = _user_output_dir(current_user) / "documents.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read documents index at %s", index_path)
        return []
