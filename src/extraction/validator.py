"""
Post-extraction validation.

WHY VALIDATION IS NECESSARY:

LLMs are probabilistic. Even with a strict JSON Schema enforcing enum values,
Claude may:
  - List an entity in a relationship that it forgot to include in the entities list
  - Produce a relationship between incompatible types (e.g. Person →ACQUIRED→ Person)
  - Extract duplicate entities with slightly different names

We separate validation from the API call so the extractor can retry with a
corrective message when validation fails. This is a key quality gate — silently
accepting bad data propagates corruption into Neo4j and makes debugging hard.

VALIDATION LEVELS:

  HARD errors (trigger retry):
    - Relationship references an entity name not present in the entity list.
      This means the graph would have a dangling edge reference.

  SOFT warnings (logged, no retry):
    - Type mismatch on a relationship (e.g. ACQUIRED where source is not Company).
      These are surprising but might be edge cases the model correctly identified.
    - Duplicate entity names (same name, same type). The first occurrence is kept.
    - Relationship where source == target (self-loop on most relationship types).
"""

import logging
from dataclasses import dataclass, field

from src.extraction.schemas import (
    ChunkExtractionResult,
    EntityType,
    ExtractedEntity,
    RelationshipType,
)

logger = logging.getLogger(__name__)


# Expected (source_type, target_type) pairs per relationship.
# Used to generate warnings — not enforced as hard errors.
_EXPECTED_TYPES: dict[RelationshipType, tuple[set[EntityType], set[EntityType]]] = {
    RelationshipType.ACQUIRED: (
        {EntityType.COMPANY},
        {EntityType.COMPANY},
    ),
    RelationshipType.DEVELOPED: (
        {EntityType.COMPANY, EntityType.TEAM, EntityType.PERSON},
        {EntityType.TECHNOLOGY, EntityType.PRODUCT},
    ),
    RelationshipType.USES: (
        {EntityType.PROJECT, EntityType.PRODUCT},
        {EntityType.TECHNOLOGY},
    ),
    RelationshipType.DEPENDS_ON: (
        {EntityType.TECHNOLOGY},
        {EntityType.TECHNOLOGY},
    ),
    RelationshipType.OWNS: (
        {EntityType.COMPANY},
        {EntityType.PRODUCT, EntityType.PROJECT},
    ),
    RelationshipType.WORKS_FOR: (
        {EntityType.PERSON},
        {EntityType.COMPANY, EntityType.TEAM},
    ),
    RelationshipType.MANAGES: (
        {EntityType.PERSON},
        {EntityType.PROJECT, EntityType.TEAM},
    ),
    RelationshipType.PART_OF: (
        {EntityType.TEAM, EntityType.DEPARTMENT},
        {EntityType.DEPARTMENT, EntityType.COMPANY},
    ),
    RelationshipType.LED_BY: (
        {EntityType.TEAM, EntityType.DEPARTMENT},
        {EntityType.PERSON},
    ),
    RelationshipType.CREATED_BY: (
        {EntityType.PROJECT, EntityType.PRODUCT},
        {EntityType.PERSON, EntityType.TEAM},
    ),
    RelationshipType.MAINTAINS: (
        {EntityType.TEAM},
        {EntityType.TECHNOLOGY, EntityType.PRODUCT},
    ),
    RelationshipType.PARTNERED_WITH: (
        {EntityType.COMPANY},
        {EntityType.COMPANY},
    ),
}


@dataclass
class ValidationResult:
    is_valid: bool
    hard_errors: list[str] = field(default_factory=list)   # require retry
    soft_warnings: list[str] = field(default_factory=list)  # logged only


def validate_extraction(
    result: ChunkExtractionResult,
    chunk_id: str,
) -> ValidationResult:
    """
    Validate a ChunkExtractionResult.

    Returns ValidationResult with:
      - is_valid=False if any HARD errors found (caller should retry)
      - is_valid=True with soft_warnings if only warnings found
    """
    hard_errors: list[str] = []
    soft_warnings: list[str] = []

    # Build a lookup of entity name → entity type
    entity_index: dict[str, EntityType] = {}
    for entity in result.entities:
        name_lower = entity.name.strip().lower()
        if name_lower in entity_index:
            soft_warnings.append(
                f"Duplicate entity '{entity.name}' (type={entity.entity_type.value}). "
                "Keeping first occurrence."
            )
        else:
            entity_index[name_lower] = entity.entity_type

    # Validate each relationship
    for i, rel in enumerate(result.relationships):
        src_lower = rel.source_entity.strip().lower()
        tgt_lower = rel.target_entity.strip().lower()
        label = f"Relationship[{i}] {rel.source_entity} →{rel.relationship_type.value}→ {rel.target_entity}"

        # HARD: both endpoints must appear in entity list
        if src_lower not in entity_index:
            hard_errors.append(
                f"{label}: source entity '{rel.source_entity}' not found in entities list."
            )
        if tgt_lower not in entity_index:
            hard_errors.append(
                f"{label}: target entity '{rel.target_entity}' not found in entities list."
            )

        # HARD: self-loops don't make sense for most relationship types
        if src_lower == tgt_lower and rel.relationship_type not in {RelationshipType.PARTNERED_WITH}:
            hard_errors.append(f"{label}: source and target are the same entity.")

        # SOFT: type constraint check
        if rel.relationship_type in _EXPECTED_TYPES:
            expected_src_types, expected_tgt_types = _EXPECTED_TYPES[rel.relationship_type]
            if rel.source_type not in expected_src_types:
                soft_warnings.append(
                    f"{label}: unexpected source type '{rel.source_type.value}' "
                    f"(expected one of {[t.value for t in expected_src_types]})."
                )
            if rel.target_type not in expected_tgt_types:
                soft_warnings.append(
                    f"{label}: unexpected target type '{rel.target_type.value}' "
                    f"(expected one of {[t.value for t in expected_tgt_types]})."
                )

    # Log everything
    for warning in soft_warnings:
        logger.warning("[%s] %s", chunk_id[:8], warning)
    for error in hard_errors:
        logger.error("[%s] HARD ERROR: %s", chunk_id[:8], error)

    return ValidationResult(
        is_valid=len(hard_errors) == 0,
        hard_errors=hard_errors,
        soft_warnings=soft_warnings,
    )


def deduplicate_entities(result: ChunkExtractionResult) -> ChunkExtractionResult:
    """
    Remove duplicate entities (same name, case-insensitive) from the result.
    Keeps the first occurrence.
    """
    seen: set[str] = set()
    unique_entities: list[ExtractedEntity] = []
    for entity in result.entities:
        key = (entity.name.strip().lower(), entity.entity_type)
        if key not in seen:
            seen.add(key)
            unique_entities.append(entity)
    return result.model_copy(update={"entities": unique_entities})
