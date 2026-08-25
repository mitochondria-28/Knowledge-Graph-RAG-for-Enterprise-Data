"""
Data models for the entity resolution pipeline.

THREE TYPES OF RECORDS:

  EntityMention     — a single occurrence of an entity name in one chunk
                      (intermediate, not persisted)

  ResolvedEntity    — the canonical entity after all mentions are merged
                      (persisted to resolved_entities.json)

  ResolvedRelationship — a relationship between two canonical entities,
                         deduplicated across all chunks that mentioned it
                         (persisted to resolved_relationships.json)
"""

from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from src.extraction.schemas import EntityType, RelationshipType


# ── Intermediate ──────────────────────────────────────────────────────────────

class EntityMention(BaseModel):
    """
    One occurrence of an entity extracted from one chunk.
    Many mentions → one ResolvedEntity.
    """
    name: str
    entity_type: EntityType
    chunk_id: str
    source_file: str
    confidence: float
    description: str | None = None


class RelationshipMention(BaseModel):
    """
    One occurrence of a relationship extracted from one chunk.
    Many mentions → one ResolvedRelationship.
    """
    source_name: str
    source_type: EntityType
    relationship_type: RelationshipType
    target_name: str
    target_type: EntityType
    chunk_id: str
    source_file: str
    confidence: float
    supporting_text: str | None = None


# ── Resolved (output) ─────────────────────────────────────────────────────────

class ResolvedEntity(BaseModel):
    """
    The canonical form of an entity after resolution.
    This is what gets stored as a Neo4j node in Phase 4.
    """
    canonical_id: str         # UUID5(entity_type:canonical_name) — stable, cross-system key
    canonical_name: str       # chosen canonical display name
    entity_type: EntityType
    aliases: list[str]        # all other names this entity was seen as
    chunk_ids: list[str]      # every chunk where any alias appeared
    source_files: list[str]   # deduplicated list of source documents
    mention_count: int        # total number of mentions across all chunks
    avg_confidence: float
    description: str | None   # best description from any mention
    resolved_at: str          # ISO-8601 UTC timestamp

    def to_dict(self) -> dict:
        return self.model_dump()


class ResolvedRelationship(BaseModel):
    """
    A deduplicated relationship between two canonical entities.
    This is what gets stored as a Neo4j edge in Phase 4.
    """
    rel_id: str               # UUID5(source_id:rel_type:target_id)
    source_id: str            # canonical_id of source entity
    source_name: str          # canonical name (for readability)
    source_type: EntityType
    relationship_type: RelationshipType
    target_id: str            # canonical_id of target entity
    target_name: str
    target_type: EntityType
    chunk_ids: list[str]      # all chunks where this relationship was found
    source_files: list[str]   # deduplicated source documents
    mention_count: int        # how many chunks mentioned this relationship
    avg_confidence: float
    supporting_texts: list[str]  # direct quotes from source chunks

    def to_dict(self) -> dict:
        return self.model_dump()


class ReviewItem(BaseModel):
    """
    A pair of entity names that are similar but below the auto-merge threshold.
    Written to resolution_review.json for human inspection.
    """
    name_a: str
    name_b: str
    entity_type: EntityType
    similarity: float
    normalized_a: str
    normalized_b: str
    reason: str = "similarity in [review_threshold, auto_threshold)"


class ResolutionResult(BaseModel):
    """Summary of a resolution run."""
    entities: list[ResolvedEntity]
    relationships: list[ResolvedRelationship]
    review_items: list[ReviewItem]
    raw_entity_mentions: int       # total mentions before resolution
    raw_relationship_mentions: int
    unique_names_before: int       # distinct (name, type) pairs before merging
    unique_entities_after: int     # canonical entities after merging
    merge_count: int               # number of names that were merged into another
    review_count: int              # number of pairs flagged for review


# ── ID generation (matches Phase 1 pattern) ──────────────────────────────────

def make_entity_id(entity_type: EntityType, canonical_name: str) -> str:
    """Stable UUID for an entity, derived from type + canonical name."""
    return str(uuid5(NAMESPACE_URL, f"{entity_type.value}:{canonical_name}"))


def make_relationship_id(source_id: str, rel_type: RelationshipType, target_id: str) -> str:
    """Stable UUID for a relationship, derived from endpoint IDs + type."""
    return str(uuid5(NAMESPACE_URL, f"{source_id}:{rel_type.value}:{target_id}"))
