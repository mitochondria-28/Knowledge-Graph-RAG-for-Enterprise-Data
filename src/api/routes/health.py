"""
Health and readiness endpoints — Phase 9.

GET /health — liveness probe.
    Returns 200 OK as long as the Python process is running.
    Used by load balancers and container orchestrators to decide
    whether to restart the container.

GET /ready — readiness probe.
    Returns 200 if the pipeline is initialised (chunks loaded, entity
    index populated). Returns 503 if startup hasn't completed yet.
    Used by orchestrators to decide whether to send traffic to this instance.

WHY TWO SEPARATE PROBES:

Kubernetes and most load balancers distinguish liveness (is the process alive?)
from readiness (can it serve requests?). During startup, /health returns 200
but /ready returns 503, preventing traffic from being sent before the pipeline
is ready — without killing the pod unnecessarily.
"""

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from src.api.schemas import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe — is the process running?",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    summary="Readiness probe — is the pipeline initialised?",
)
def ready(request: Request):
    state = request.app.state
    chunk_count: int = getattr(state, "chunk_count", 0)
    entity_count: int = getattr(state, "entity_count", 0)
    generator: str = getattr(state, "generator_type", "unknown")

    body = ReadyResponse(
        status="ready" if chunk_count > 0 else "not_ready",
        chunk_count=chunk_count,
        entity_count=entity_count,
        generator=generator,
    )

    http_status = status.HTTP_200_OK if chunk_count > 0 else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body.model_dump(), status_code=http_status)
