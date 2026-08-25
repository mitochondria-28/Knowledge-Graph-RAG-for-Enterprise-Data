"""
Neo4j driver management.

WHY A CONTEXT MANAGER:

The Neo4j Python driver maintains a connection pool. If we create the driver
at module import time, test isolation becomes hard (tests fight over one pool).
If we create it in every function, we pay pool setup cost repeatedly. A context
manager gives us:

  - Lazy construction (only connect when actually needed)
  - Deterministic cleanup (driver.close() always called via __exit__)
  - Easy mocking in unit tests (patch Neo4jConnection.__enter__)

THREAD SAFETY:

The neo4j.Driver is thread-safe and should be reused across the application's
lifetime. Sessions (driver.session()) are NOT thread-safe and must be used from
one thread at a time. This module returns the driver; callers create short-lived
sessions themselves.
"""

import logging
from typing import TYPE_CHECKING

from src.config import settings

if TYPE_CHECKING:
    from neo4j import Driver

logger = logging.getLogger(__name__)


class Neo4jConnection:
    """
    Context manager that holds an open Neo4j driver for the duration of a block.

    Usage:
        with Neo4jConnection() as driver:
            with driver.session(database="neo4j") as session:
                session.run("MATCH (n) RETURN count(n)")
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver: "Driver | None" = None

    def __enter__(self) -> "Driver":
        try:
            from neo4j import GraphDatabase
            from neo4j.exceptions import AuthError, ServiceUnavailable
        except ImportError as exc:
            raise ImportError(
                "neo4j driver not installed. "
                "Run: pip install 'enterprise-kg-rag[graph]'  "
                "or: pip install neo4j>=5.20"
            ) from exc

        logger.debug("Opening Neo4j connection to %s", self._uri)
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        # Verify connectivity — raises ServiceUnavailable / AuthError
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            self._driver.close()
            self._driver = None
            raise
        logger.debug("Neo4j connection established")
        return self._driver

    def __exit__(self, *_) -> None:
        if self._driver is not None:
            self._driver.close()
            logger.debug("Neo4j connection closed")
            self._driver = None


def ping(uri: str | None = None, user: str | None = None, password: str | None = None) -> bool:
    """Return True if Neo4j is reachable with the given credentials."""
    try:
        with Neo4jConnection(uri, user, password):
            return True
    except Exception:
        return False
