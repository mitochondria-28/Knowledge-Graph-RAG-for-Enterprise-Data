"""
POST /documents/upload — ingest a document into the user's private corpus.
GET  /documents        — list every document the current user has uploaded.

On serverless (Vercel):
  - Files are written to TEMP_DIR/corpus/users/{user_id}/ (e.g. /tmp).
  - After ingestion, chunks + entity index are persisted to the user_corpus DB
    table so they survive cold starts (ephemeral filesystem).
  - Documents list is also stored in user_corpus.documents.

On local dev:
  - Paths default to corpus/users/{user_id}/ and output/users/{user_id}/.
  - Same DB persistence applies; SQLite is used instead of PostgreSQL.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from src.auth.database import get_db
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
    base = Path(settings.temp_dir) if settings.temp_dir else Path(settings.corpus_dir)
    return base / "users" / user.id


def _user_output_dir(user: User) -> Path:
    from src.config import settings
    base = Path(settings.temp_dir) if settings.temp_dir else Path(settings.output_dir)
    return base / "users" / user.id


@router.post("/upload", summary="Upload and ingest a document into the user's private corpus.")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("general"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.auth.models import UserCorpus
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

    folder     = _TYPE_TO_DIR.get(doc_type, "general")
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

    chunks_path   = output_dir / "all_chunks.json"
    entities_path = output_dir / "resolved_entities.json"
    chunks        = load_chunks(chunks_path) if chunks_path.exists() else []
    entity_index  = load_entity_index(entities_path) if entities_path.exists() else {}

    # Persist to DB so chunks survive serverless cold starts
    doc_meta = {
        "filename":    file.filename,
        "doc_type":    doc_type,
        "uploaded_at": datetime.utcnow().isoformat(),
        "size_bytes":  len(contents),
    }
    corpus_row = db.query(UserCorpus).filter(UserCorpus.user_id == current_user.id).first()
    if corpus_row is None:
        corpus_row = UserCorpus(
            user_id=current_user.id,
            chunks=chunks,
            entity_index=entity_index,
            documents=[doc_meta],
        )
        db.add(corpus_row)
    else:
        # Replace existing entry for same filename; keep others
        existing_docs = [d for d in (corpus_row.documents or [])
                         if d.get("filename") != file.filename]
        corpus_row.chunks       = chunks
        corpus_row.entity_index = entity_index
        corpus_row.documents    = existing_docs + [doc_meta]
        corpus_row.updated_at   = datetime.utcnow()
    db.commit()

    # Hot-reload in-memory pipeline
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
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Returns only documents this user uploaded. New users receive an empty list."""
    from src.auth.models import UserCorpus

    # DB-first — works on serverless and local
    corpus_row = db.query(UserCorpus).filter(UserCorpus.user_id == current_user.id).first()
    if corpus_row is not None:
        return corpus_row.documents or []

    # Filesystem fallback — local dev only (pre-DB migration)
    index_path = _user_output_dir(current_user) / "documents.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read documents index at %s", index_path)
        return []
