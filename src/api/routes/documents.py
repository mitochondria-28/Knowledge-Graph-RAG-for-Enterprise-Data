"""
POST /documents/upload — save an uploaded file, ingest it, and hot-reload pipeline chunks.
GET  /documents        — list every ingested document from the output index.

Uploaded files are written to corpus/uploads/{folder}/ where {folder} is the
subdirectory name that the ingestion loader maps to the chosen doc_type.  The
ingestion pipeline is then run against the uploads directory so hash-based
deduplication skips already-processed files and only chunks the new one.

After ingestion, pipeline._chunks is replaced in-place so that questions asked
immediately after upload use the freshly chunked content without a restart.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from src.ingestion.loader import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# Maps the UI-facing doc_type label → corpus subdirectory name (matching _DIR_TO_TYPE in loader.py)
_TYPE_TO_DIR: dict[str, str] = {
    "company": "companies",
    "project": "projects",
    "technology": "technologies",
    "people": "people",
    "general": "general",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", summary="Upload and ingest a document.")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("general"),
) -> dict:
    from src.answer.pipeline import load_chunks
    from src.config import settings
    from src.ingestion.pipeline import run_ingestion

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            ),
        )

    folder = _TYPE_TO_DIR.get(doc_type, "general")
    uploads_dir = settings.corpus_dir / "uploads"
    dest_dir = uploads_dir / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    # Read with size guard
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB upload limit.",
        )

    dest_path.write_bytes(contents)
    logger.info("Saved upload: %s (%d bytes)", dest_path, len(contents))

    # Ingest only the uploads directory; hash-dedup skips already-processed files
    try:
        stats = run_ingestion(
            corpus_dir=uploads_dir,
            output_dir=settings.output_dir,
        )
    except Exception as exc:
        logger.exception("Ingestion failed for %s", dest_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc

    # Hot-reload chunks so the running pipeline immediately serves the new content
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is not None:
        pipeline._chunks = load_chunks()
        request.app.state.chunk_count = len(pipeline._chunks)
        logger.info("Hot-reloaded %d chunks into live pipeline", len(pipeline._chunks))

    return {
        "filename": file.filename,
        "doc_type": doc_type,
        "stats": stats,
    }


@router.get("", summary="List all ingested documents.")
def list_documents() -> list[dict]:
    from src.config import settings

    index_path = settings.output_dir / "documents.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read documents index at %s", index_path)
        return []
