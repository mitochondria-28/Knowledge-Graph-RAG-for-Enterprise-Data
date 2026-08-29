"""
FastAPI application factory — Phase 9, instrumented in Phase 11, auth in Phase 14.

STARTUP (lifespan):

  1. Initialise SQLite auth DB (create tables if missing)
  2. Load corpus chunks from output/all_chunks.json
  3. Load entity index from output/resolved_entities.json
  4. Choose generator:
       - If GEMINI_API_KEY is set → AnswerGenerator (real Gemini)
       - Otherwise               → MockAnswerGenerator (no API call)
  5. Build AnswerPipeline and attach to app.state
  6. Set corpus-size Prometheus gauges

Per-user isolation:
  Each authenticated user owns their own corpus directory and output directory.
  User pipelines are stored in app.state.user_pipelines: dict[user_id, AnswerPipeline].
  The default global pipeline (app.state.pipeline) is kept for backward-compatibility.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import ask as ask_router
from src.api.routes import documents as documents_router
from src.api.routes import health as health_router
from src.api.routes import metrics as metrics_router
from src.auth.router import router as auth_router
from src.observability.logging import configure_logging
from src.observability.metrics import CORPUS_CHUNKS, CORPUS_ENTITIES
from src.observability.tracing import configure_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all pipeline resources once at startup."""
    from src.answer.generator import AnswerGenerator, MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.auth.database import init_db
    from src.config import settings
    from src.router.pipeline import load_entity_index

    # ── Observability ─────────────────────────────────────────────────────────
    configure_logging(level=settings.log_level)
    configure_tracing()

    # ── Auth DB ───────────────────────────────────────────────────────────────
    init_db()
    logger.info("Auth database initialised")

    # ── Per-user pipeline registry ────────────────────────────────────────────
    app.state.user_pipelines: dict = {}

    # ── Global (default) pipeline ─────────────────────────────────────────────
    chunks = load_chunks()
    entity_index = load_entity_index()
    logger.info(
        "Corpus loaded",
        extra={"chunk_count": len(chunks), "entity_count": len(entity_index)},
    )

    generator: AnswerGenerator | MockAnswerGenerator
    api_key = getattr(settings, "gemini_api_key", None)

    if api_key:
        try:
            from src.answer.generator import make_generator
            generator = make_generator(api_key=api_key)
            logger.info("Using real AnswerGenerator (gemini-2.5-flash)")
        except Exception as exc:
            logger.warning("Could not initialise Gemini client (%s) — using mock", exc)
            generator = MockAnswerGenerator()
    else:
        logger.info("GEMINI_API_KEY not set — using MockAnswerGenerator")
        generator = MockAnswerGenerator()

    app.state.pipeline = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
    )
    app.state.chunk_count = len(chunks)
    app.state.entity_count = len(entity_index)
    app.state.generator_type = type(generator).__name__
    app.state._default_generator = generator

    CORPUS_CHUNKS.set(len(chunks))
    CORPUS_ENTITIES.set(len(entity_index))

    yield

    logger.info("Shutting down — pipeline released")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Enterprise Knowledge Graph RAG",
        description=(
            "Hybrid vector + knowledge graph retrieval with LLM answer "
            "generation and citation validation. Built phase-by-phase as a "
            "portfolio project."
        ),
        version="0.10.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS — allow credentials so Authorization header works ────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "Authorization"],
    )

    # ── Request-ID + security + latency logging middleware ────────────────────
    @application.middleware("http")
    async def request_middleware(request: Request, call_next) -> Response:
        import time
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info(
            "HTTP request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(auth_router)
    application.include_router(health_router.router)
    application.include_router(ask_router.router)
    application.include_router(documents_router.router)
    application.include_router(metrics_router.router)

    return application


app = create_app()
