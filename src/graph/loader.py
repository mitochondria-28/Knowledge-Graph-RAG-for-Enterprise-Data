"""
MERGE-based graph loader for entities and relationships.

SECURITY NOTE — why we interpolate labels but not values:

  Node labels and relationship types are part of Cypher syntax, not data.
  Neo4j does NOT support parameterized labels — you cannot write:
      MERGE (n:$label {id: $id})   ← INVALID Cypher syntax

  We therefore interpolate the label string into the query template.
  This is safe ONLY because the label comes from our EntityType / RelationshipType
  enum — a closed, hardcoded allowlist defined in src/extraction/schemas.py.

  The actual data values (names, IDs, counts, texts) are ALWAYS parameters.
  This guarantees that no user input or LLM output can inject Cypher.

WHY UNWIND FOR BATCHING:

Instead of sending one MERGE per entity, we use UNWIND to send a list:

  UNWIND $batch AS e
  MERGE (n:Entity:Company {canonical_id: e.canonical_id})
  SET n.canonical_name = e.canonical_name ...

This lets Neo4j execute the whole batch in a single round trip and a single
transaction, which is 10–50× faster than individual MERGE calls for large
datasets. The batch size (default 500) is a tuning parameter — larger batches
use more heap but fewer round trips.

WHY SET OVERWRITES ON MERGE:

We use `SET n.property = value` (not `SET n += map`) so that a re-run
always brings properties up to date. If an entity gains more mentions in a
future extraction cycle, re-running the loader will update mention_count.
This is the idempotent "upsert" behaviour.

NODE LABELS:

Every entity gets the base label :Entity plus its type label:
  :Entity:Company, :Entity:Person, :Entity:Technology, ...

The base label is used for the canonical_id uniqueness constraint.
The type label is used for fast type-filtered Cypher queries.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.extraction.schemas import EntityType, RelationshipType

if TYPE_CHECKING:
    from neo4j import Session

logger = logging.getLogger(__name__)

# ── Allowlisted label / rel-type strings from our enums ───────────────────────

_VALID_ENTITY_LABELS: frozenset[str] = frozenset(e.value for e in EntityType)
_VALID_REL_TYPES: frozenset[str] = frozenset(r.value for r in RelationshipType)

# Default batch size: 500 entities / relationships per transaction
_DEFAULT_BATCH_SIZE = 500


# ── Cypher templates (label/rel_type interpolated from enum allowlist) ─────────

def _entity_merge_cypher(entity_label: str) -> str:
    """
    Build the MERGE query for one entity type.
    `entity_label` must come from EntityType enum — caller's responsibility.
    """
    assert entity_label in _VALID_ENTITY_LABELS, f"Unknown label: {entity_label!r}"
    return f"""
UNWIND $batch AS e
MERGE (n:Entity:{entity_label} {{canonical_id: e.canonical_id}})
SET n.canonical_name  = e.canonical_name,
    n.entity_type     = e.entity_type,
    n.mention_count   = e.mention_count,
    n.avg_confidence  = e.avg_confidence,
    n.description     = e.description,
    n.aliases         = e.aliases,
    n.source_files    = e.source_files,
    n.chunk_ids       = e.chunk_ids,
    n.resolved_at     = e.resolved_at
RETURN count(n) AS processed
""".strip()


def _relationship_merge_cypher(rel_type: str) -> str:
    """
    Build the MERGE query for one relationship type.
    `rel_type` must come from RelationshipType enum — caller's responsibility.
    """
    assert rel_type in _VALID_REL_TYPES, f"Unknown rel_type: {rel_type!r}"
    return f"""
UNWIND $batch AS r
MATCH (src:Entity {{canonical_id: r.source_id}})
MATCH (tgt:Entity {{canonical_id: r.target_id}})
MERGE (src)-[rel:{rel_type}]->(tgt)
SET rel.mention_count    = r.mention_count,
    rel.avg_confidence   = r.avg_confidence,
    rel.source_files     = r.source_files,
    rel.chunk_ids        = r.chunk_ids,
    rel.supporting_texts = r.supporting_texts
RETURN count(rel) AS processed
""".strip()


# ── Result tracking ────────────────────────────────────────────────────────────

@dataclass
class LoadStats:
    nodes_merged: int = 0
    relationships_merged: int = 0
    entity_counts: dict[str, int] = field(default_factory=dict)
    rel_counts: dict[str, int] = field(default_factory=dict)


# ── Entity loading ─────────────────────────────────────────────────────────────

def _entity_to_params(entity: dict[str, Any]) -> dict[str, Any]:
    """Extract Neo4j parameter dict from a resolved entity dict."""
    return {
        "canonical_id":   entity["canonical_id"],
        "canonical_name": entity["canonical_name"],
        "entity_type":    entity["entity_type"],
        "mention_count":  entity["mention_count"],
        "avg_confidence": entity["avg_confidence"],
        "description":    entity.get("description"),
        "aliases":        entity.get("aliases", []),
        "source_files":   entity.get("source_files", []),
        "chunk_ids":      entity.get("chunk_ids", []),
        "resolved_at":    entity.get("resolved_at", ""),
    }


def load_entities(
    session: "Session",
    entities: list[dict[str, Any]],
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """
    MERGE all entities into Neo4j. Returns counts per entity type.

    Groups entities by type so each MERGE query uses the correct label.
    Entities are sent in batches of `batch_size` to avoid large transactions.
    """
    # Group by entity_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        etype = entity["entity_type"]
        if etype not in _VALID_ENTITY_LABELS:
            logger.warning("Skipping entity with unknown type %r: %s", etype, entity.get("canonical_name"))
            continue
        by_type[etype].append(_entity_to_params(entity))

    counts: dict[str, int] = {}
    for etype, params_list in by_type.items():
        cypher = _entity_merge_cypher(etype)
        total = 0
        for i in range(0, len(params_list), batch_size):
            batch = params_list[i : i + batch_size]
            result = session.run(cypher, batch=batch)
            total += result.single()["processed"]
        counts[etype] = total
        logger.debug("Merged %d %s nodes", total, etype)

    return counts


# ── Relationship loading ───────────────────────────────────────────────────────

def _rel_to_params(rel: dict[str, Any]) -> dict[str, Any]:
    """Extract Neo4j parameter dict from a resolved relationship dict."""
    return {
        "source_id":       rel["source_id"],
        "target_id":       rel["target_id"],
        "mention_count":   rel["mention_count"],
        "avg_confidence":  rel["avg_confidence"],
        "source_files":    rel.get("source_files", []),
        "chunk_ids":       rel.get("chunk_ids", []),
        "supporting_texts": rel.get("supporting_texts", []),
    }


def load_relationships(
    session: "Session",
    relationships: list[dict[str, Any]],
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """
    MERGE all relationships into Neo4j. Returns counts per relationship type.

    Groups relationships by type — each type needs its own MERGE query because
    Neo4j relationship types are part of the Cypher syntax.
    """
    by_type: dict[str, list[dict]] = defaultdict(list)
    for rel in relationships:
        rtype = rel["relationship_type"]
        if rtype not in _VALID_REL_TYPES:
            logger.warning("Skipping relationship with unknown type %r", rtype)
            continue
        by_type[rtype].append(_rel_to_params(rel))

    counts: dict[str, int] = {}
    for rtype, params_list in by_type.items():
        cypher = _relationship_merge_cypher(rtype)
        total = 0
        for i in range(0, len(params_list), batch_size):
            batch = params_list[i : i + batch_size]
            result = session.run(cypher, batch=batch)
            total += result.single()["processed"]
        counts[rtype] = total
        logger.debug("Merged %d %s relationships", total, rtype)

    return counts
