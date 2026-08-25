"""
Neo4j schema: constraints and indexes.

WHY CONSTRAINTS BEFORE LOADING:

1. UNIQUENESS CONSTRAINT on Entity.canonical_id ensures MERGE is O(log n)
   instead of O(n). Without it, Neo4j must scan all Entity nodes to check for
   duplicates on every MERGE.

2. UNIQUE constraint implicitly creates a B-tree index on the constrained
   property, so we get fast lookup for free.

3. IF NOT EXISTS means this is idempotent — safe to run on every startup.

WHY SEPARATE INDEXES FOR canonical_name AND entity_type:

These properties are used in Phase 5–7 for text search and type filtering.
Creating them now is cheap (the dataset is small); retrofitting indexes on a
large live graph is expensive.

NODE LABEL STRATEGY:

Each node gets TWO labels:
  - :Entity  — base label used in constraints, universal MATCH patterns
  - :Company / :Person / etc. — type-specific label for fast type-filtered queries

Example:
  MATCH (n:Person) WHERE n.canonical_name STARTS WITH 'Aisha'  ← uses type index
  MATCH (n:Entity {canonical_id: $id})                         ← uses constraint
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session

logger = logging.getLogger(__name__)

# Constraint and index DDL. IF NOT EXISTS makes every statement idempotent.
_CONSTRAINTS = [
    # Primary uniqueness constraint — also implicitly creates a B-tree index
    """
    CREATE CONSTRAINT entity_canonical_id IF NOT EXISTS
    FOR (n:Entity) REQUIRE n.canonical_id IS UNIQUE
    """,
]

_INDEXES = [
    # Range index for name prefix/equality searches
    """
    CREATE INDEX entity_name_idx IF NOT EXISTS
    FOR (n:Entity) ON (n.canonical_name)
    """,
    # Range index for type-based filtering
    """
    CREATE INDEX entity_type_idx IF NOT EXISTS
    FOR (n:Entity) ON (n.entity_type)
    """,
]


def create_schema(session: "Session") -> None:
    """
    Create uniqueness constraints and indexes.
    All statements use IF NOT EXISTS so they are safe to re-run.
    """
    for ddl in _CONSTRAINTS:
        statement = ddl.strip()
        logger.debug("Running DDL: %s", statement.splitlines()[0])
        session.run(statement)

    for ddl in _INDEXES:
        statement = ddl.strip()
        logger.debug("Running DDL: %s", statement.splitlines()[0])
        session.run(statement)

    logger.info("Schema setup complete (%d constraints, %d indexes)",
                len(_CONSTRAINTS), len(_INDEXES))


def drop_all_entities_and_relationships(session: "Session") -> int:
    """
    Delete all Entity nodes and their relationships.
    Used by the --force flag to enable a clean re-load.
    Returns the count of deleted nodes.
    """
    result = session.run(
        "MATCH (n:Entity) DETACH DELETE n RETURN count(n) AS deleted"
    )
    deleted = result.single()["deleted"]
    logger.info("Deleted %d Entity nodes (DETACH DELETE)", deleted)
    return deleted
