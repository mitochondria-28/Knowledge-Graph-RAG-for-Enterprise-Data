"""Unit tests for extraction validator."""

import pytest

from src.extraction.schemas import (
    ChunkExtractionResult,
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipType,
)
from src.extraction.validator import deduplicate_entities, validate_extraction


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entity(name: str, etype: EntityType, confidence: float = 0.99) -> ExtractedEntity:
    return ExtractedEntity(name=name, entity_type=etype, confidence=confidence)


def _make_rel(
    src: str, src_type: EntityType, rel: RelationshipType, tgt: str, tgt_type: EntityType,
    confidence: float = 0.99,
) -> ExtractedRelationship:
    return ExtractedRelationship(
        source_entity=src, source_type=src_type,
        relationship_type=rel,
        target_entity=tgt, target_type=tgt_type,
        confidence=confidence,
    )


# ── Valid extraction ──────────────────────────────────────────────────────────

def test_valid_extraction_passes():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("TechNova Corporation", EntityType.COMPANY),
            _make_entity("Stellar Systems", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "TechNova Corporation", EntityType.COMPANY,
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,
            )
        ],
    )
    vr = validate_extraction(result, "test-chunk-id")
    assert vr.is_valid
    assert len(vr.hard_errors) == 0


def test_empty_extraction_passes():
    result = ChunkExtractionResult()
    vr = validate_extraction(result, "test-chunk-id")
    assert vr.is_valid


# ── Hard errors ───────────────────────────────────────────────────────────────

def test_relationship_source_not_in_entities():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("Stellar Systems", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "TechNova Corporation", EntityType.COMPANY,   # NOT in entities
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,
            )
        ],
    )
    vr = validate_extraction(result, "test-chunk-id")
    assert not vr.is_valid
    assert any("TechNova Corporation" in e for e in vr.hard_errors)


def test_relationship_target_not_in_entities():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("TechNova Corporation", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "TechNova Corporation", EntityType.COMPANY,
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,  # NOT in entities
            )
        ],
    )
    vr = validate_extraction(result, "test-chunk-id")
    assert not vr.is_valid
    assert any("Stellar Systems" in e for e in vr.hard_errors)


def test_self_loop_relationship_is_hard_error():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("TechNova Corporation", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "TechNova Corporation", EntityType.COMPANY,
                RelationshipType.ACQUIRED,
                "TechNova Corporation", EntityType.COMPANY,  # same as source
            )
        ],
    )
    vr = validate_extraction(result, "test-chunk-id")
    assert not vr.is_valid


# ── Soft warnings ─────────────────────────────────────────────────────────────

def test_type_mismatch_is_soft_warning():
    # ACQUIRED should be Company→Company, but source is Person — soft warning
    result = ChunkExtractionResult(
        entities=[
            _make_entity("Robert Klein", EntityType.PERSON),
            _make_entity("Stellar Systems", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "Robert Klein", EntityType.PERSON,   # wrong source type for ACQUIRED
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,
            )
        ],
    )
    vr = validate_extraction(result, "test-chunk-id")
    # Cross-reference is valid (both entities are listed)
    assert vr.is_valid
    # But there should be a soft warning about type mismatch
    assert any("source type" in w for w in vr.soft_warnings)


def test_case_insensitive_entity_matching():
    # Relationship references entity with different casing
    result = ChunkExtractionResult(
        entities=[
            _make_entity("TechNova Corporation", EntityType.COMPANY),
            _make_entity("Stellar Systems", EntityType.COMPANY),
        ],
        relationships=[
            _make_rel(
                "technova corporation", EntityType.COMPANY,  # lowercase
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,
            )
        ],
    )
    # Should pass because matching is case-insensitive
    vr = validate_extraction(result, "test-chunk-id")
    assert vr.is_valid


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_deduplicate_removes_exact_duplicates():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("TechNova Corporation", EntityType.COMPANY),
            _make_entity("TechNova Corporation", EntityType.COMPANY),  # duplicate
            _make_entity("StellarDB", EntityType.TECHNOLOGY),
        ],
        relationships=[],
    )
    deduped = deduplicate_entities(result)
    assert len(deduped.entities) == 2


def test_deduplicate_case_insensitive():
    result = ChunkExtractionResult(
        entities=[
            _make_entity("StellarDB", EntityType.TECHNOLOGY),
            _make_entity("stellardb", EntityType.TECHNOLOGY),  # same, different case
        ],
        relationships=[],
    )
    deduped = deduplicate_entities(result)
    assert len(deduped.entities) == 1
    # Keeps first occurrence
    assert deduped.entities[0].name == "StellarDB"


def test_deduplicate_different_types_not_merged():
    # Same name, different type — these are different entities (unusual but valid)
    result = ChunkExtractionResult(
        entities=[
            _make_entity("Atlas", EntityType.PROJECT),
            _make_entity("Atlas", EntityType.PRODUCT),
        ],
        relationships=[],
    )
    deduped = deduplicate_entities(result)
    # Should keep both since they have different types
    assert len(deduped.entities) == 2
