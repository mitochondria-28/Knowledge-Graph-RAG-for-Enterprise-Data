"""
PostgreSQL + pgvector connection management.

WHY A CONTEXT MANAGER:

Same reasoning as src/graph/connection.py — lazy construction, deterministic
cleanup, easy mocking. psycopg3 connections are not thread-safe so callers
should create one connection per thread / per request.

WHY register_vector():

pgvector stores vectors as a custom PostgreSQL type. `register_vector(conn)`
tells psycopg3 how to serialize Python lists → PostgreSQL vector binary and
how to deserialize vector binary → Python list[float]. Without it, you'd
get a raw bytes object back from queries instead of a usable vector.
"""

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from src.config import settings

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)


@contextmanager
def get_connection(conninfo: str | None = None):
    """
    Yield an open psycopg3 connection with the pgvector type registered.

    Usage:
        with get_connection() as conn:
            conn.execute("SELECT 1")
    """
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:
        raise ImportError(
            "psycopg / pgvector not installed. "
            "Run: pip install 'psycopg[binary]>=3.1' pgvector>=0.3"
        ) from exc

    url = conninfo or settings.postgres_url
    logger.debug("Opening psycopg connection to %s", url.split("@")[-1])

    with psycopg.connect(url) as conn:
        register_vector(conn)
        yield conn

    logger.debug("psycopg connection closed")


def ping(conninfo: str | None = None) -> bool:
    """Return True if PostgreSQL is reachable."""
    try:
        with get_connection(conninfo) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
