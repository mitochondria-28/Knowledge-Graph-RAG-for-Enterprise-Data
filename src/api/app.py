"""
FastAPI application factory — Phase 9, instrumented in Phase 11.

STARTUP (lifespan):

  1. Load corpus chunks from output/all_chunks.json
  2. Load entity index from output/resolved_entities.json
  3. Choose generator:
       - If GEMINI_API_KEY is set → AnswerGenerator (real Gemini)
       - Otherwise               → MockAnswerGenerator (no API call)
  4. Build AnswerPipeline and attach to app.state
  5. Set corpus-size Prometheus gauges

All of this happens once at startup. The pipeline is a module-level singleton —
no state is created per request.

WHY LIFESPAN (NOT @app.on_event):

@app.on_event("startup") is deprecated in FastAPI ≥ 0.93.
asynccontextmanager lifespan is the current recommended pattern and supports
both startup and shutdown in one place.

CORS:

CORSMiddleware is added to allow the Phase 13 UI (likely localhost:3000/5173)
to call the API. In production, restrict allow_origins to your actual domain.

SECURITY HEADERS:

A minimal security middleware adds X-Content-Type-Options and
X-Frame-Options on every response. A full hardening pass would add
Content-Security-Policy — out of scope for this phase.

OBSERVABILITY (Phase 11):

  - configure_logging() called once in lifespan → JSON logs to stdout
  - configure_tracing() called once → OTel in-memory spans
  - RequestID middleware → every request gets X-Request-ID header
  - Corpus gauges set at startup → kg_rag_corpus_chunks, kg_rag_corpus_entities
  - GET /metrics → Prometheus text exposition
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
from src.observability.logging import configure_logging
from src.observability.metrics import CORPUS_CHUNKS, CORPUS_ENTITIES
from src.observability.tracing import configure_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all pipeline resources once at startup."""
    from src.answer.generator import AnswerGenerator, MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.config import settings
    from src.router.pipeline import load_entity_index

    # ── Observability ─────────────────────────────────────────────────────────
    configure_logging(level=settings.log_level)
    configure_tracing()

    # ── Load corpus and entity index ──────────────────────────────────────────
    chunks = load_chunks()
    entity_index = load_entity_index()
    logger.info(
        "Corpus loaded",
        extra={"chunk_count": len(chunks), "entity_count": len(entity_index)},
    )

    # ── Choose generator ──────────────────────────────────────────────────────
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

    # ── Build pipeline ────────────────────────────────────────────────────────
    pipeline = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
    )

    # ── Attach to app.state ───────────────────────────────────────────────────
    app.state.pipeline = pipeline
    app.state.chunk_count = len(chunks)
    app.state.entity_count = len(entity_index)
    app.state.generator_type = type(generator).__name__

    # ── Corpus gauges ─────────────────────────────────────────────────────────
    CORPUS_CHUNKS.set(len(chunks))
    CORPUS_ENTITIES.set(len(entity_index))

    yield  # ── application is running ──────────────────────────────────────

    logger.info("Shutting down — pipeline released")


def create_app() -> FastAPI:
    """
    Application factory.

    Calling create_app() rather than using a module-level `app` object
    makes it easy to create isolated instances in tests.
    """
    application = FastAPI(
        title="Enterprise Knowledge Graph RAG",
        description=(
            "Hybrid vector + knowledge graph retrieval with LLM answer "
            "generation and citation validation. Built phase-by-phase as a "
            "portfolio project."
        ),
        version="0.9.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
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
    application.include_router(health_router.router)
    application.include_router(ask_router.router)
    application.include_router(documents_router.router)
    application.include_router(metrics_router.router)

    return application


# Module-level app instance used by uvicorn: `uvicorn src.api.app:app`
app = create_app()
