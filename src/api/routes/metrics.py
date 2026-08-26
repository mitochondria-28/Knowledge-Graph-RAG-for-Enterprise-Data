"""
Prometheus metrics endpoint — Phase 11.

GET /metrics returns the standard Prometheus text exposition format.
Prometheus server scrapes this endpoint every 15–60 seconds.

WHY A SEPARATE FILE:

The prometheus_client registry is process-global. Exposing it via a plain
FastAPI route (returning plaintext) keeps it orthogonal to the JSON API.
No Pydantic schema needed — the format is defined by the Prometheus spec.
"""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    response_class=Response,
    summary="Prometheus metrics",
    description=(
        "Prometheus text exposition. Scrape with a Prometheus server or "
        "read manually with `curl http://localhost:8000/metrics`."
    ),
)
def get_metrics() -> Response:
    """Expose all registered Prometheus metrics in text format."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
