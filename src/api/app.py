"""
FastAPI application factory — Phase 9.

STARTUP (lifespan):

  1. Load corpus chunks from output/all_chunks.json
  2. Load entity index from output/resolved_entities.json
  3. Choose generator:
       - If ANTHROPIC_API_KEY is set → AnswerGenerator (real Claude)
       - Otherwise              → MockAnswerGenerator (no API call)
  4. Build AnswerPipeline and attach to app.state

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
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import ask as ask_router
from src.api.routes import health as health_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all pipeline resources once at startup."""
    from src.answer.generator import AnswerGenerator, MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.config import settings
    from src.router.pipeline import load_entity_index

    # ── Load corpus and entity index ──────────────────────────────────────────
    chunks = load_chunks()
    entity_index = load_entity_index()
    logger.info("Loaded %d chunks, %d entity names/aliases", len(chunks), len(entity_index))

    # ── Choose generator ──────────────────────────────────────────────────────
    generator: AnswerGenerator | MockAnswerGenerator
    api_key = getattr(settings, "anthropic_api_key", None)

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            generator = AnswerGenerator(client)
            logger.info("Using real AnswerGenerator (claude-haiku-4-5-20251001)")
        except Exception as exc:
            logger.warning("Could not initialise Anthropic client (%s) — using mock", exc)
            generator = MockAnswerGenerator()
    else:
        logger.info("ANTHROPIC_API_KEY not set — using MockAnswerGenerator")
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

    yield  # ── application is running ──────────────────────────────────────

    # Shutdown: nothing to close in this phase (no DB connection pool, etc.)
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
        allow_headers=["Content-Type"],
    )

    # ── Minimal security headers ──────────────────────────────────────────────
    @application.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(health_router.router)
    application.include_router(ask_router.router)

    return application


# Module-level app instance used by uvicorn: `uvicorn src.api.app:app`
app = create_app()
