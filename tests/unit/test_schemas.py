"""Unit tests for extraction schemas."""

import pytest
from pydantic import ValidationError

from src.extraction.schemas import (
    ChunkExtractionResult,
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipType,
)


# ── EntityType enum ───────────────────────────────────────────────────────────

def test_entity_type_values():
    assert EntityType.COMPANY.value == "Company"
    assert EntityType.PERSON.value == "Person"
    assert EntityType.TECHNOLOGY.value == "Technology"


def test_entity_type_from_string():
    assert EntityType("Company") == EntityType.COMPANY
    assert EntityType("Technology") == EntityType.TECHNOLOGY


def test_entity_type_invalid_raises():
    with pytest.raises(ValueError):
        EntityType("InvalidType")


# ── RelationshipType enum ─────────────────────────────────────────────────────

def test_relationship_type_values():
    assert RelationshipType.ACQUIRED.value == "ACQUIRED"
    assert RelationshipType.MAINTAINS.value == "MAINTAINS"


def test_relationship_type_invalid_raises():
    with pytest.raises(ValueError):
        RelationshipType("BOUGHT_BY")


# ── ExtractedEntity ───────────────────────────────────────────────────────────

def test_extracted_entity_valid():
    entity = ExtractedEntity(
        name="TechNova Corporation",
        entity_type=EntityType.COMPANY,
        confidence=0.99,
    )
    assert entity.name == "TechNova Corporation"
    assert entity.entity_type == EntityType.COMPANY
    assert entity.description is None


def test_extracted_entity_with_description():
    entity = ExtractedEntity(
        name="StellarDB",
        entity_type=EntityType.TECHNOLOGY,
        description="A distributed database developed by Stellar Systems.",
        confidence=0.95,
    )
    assert entity.description is not None


def test_extracted_entity_confidence_too_high():
    with pytest.raises(ValidationError):
        ExtractedEntity(name="X", entity_type=EntityType.COMPANY, confidence=1.5)


def test_extracted_entity_confidence_negative():
    with pytest.raises(ValidationError):
        ExtractedEntity(name="X", entity_type=EntityType.COMPANY, confidence=-0.1)


def test_extracted_entity_invalid_type():
    with pytest.raises(ValidationError):
        ExtractedEntity(name="X", entity_type="UnknownType", confidence=0.9)


# ── ExtractedRelationship ─────────────────────────────────────────────────────

def test_extracted_relationship_valid():
    rel = ExtractedRelationship(
        source_entity="TechNova Corporation",
        source_type=EntityType.COMPANY,
        relationship_type=RelationshipType.ACQUIRED,
        target_entity="Stellar Systems",
        target_type=EntityType.COMPANY,
        confidence=0.99,
    )
    assert rel.relationship_type == RelationshipType.ACQUIRED
    assert rel.supporting_text is None


def test_extracted_relationship_with_supporting_text():
    rel = ExtractedRelationship(
        source_entity="TechNova Corporation",
        source_type=EntityType.COMPANY,
        relationship_type=RelationshipType.ACQUIRED,
        target_entity="Stellar Systems",
        target_type=EntityType.COMPANY,
        supporting_text="TechNova acquired Stellar Systems for $340 million.",
        confidence=0.99,
    )
    assert "340 million" in rel.supporting_text


def test_extracted_relationship_invalid_rel_type():
    with pytest.raises(ValidationError):
        ExtractedRelationship(
            source_entity="A",
            source_type=EntityType.COMPANY,
            relationship_type="BOUGHT_BY",  # not in enum
            target_entity="B",
            target_type=EntityType.COMPANY,
            confidence=0.9,
        )


# ── ChunkExtractionResult ─────────────────────────────────────────────────────

def test_chunk_extraction_result_empty():
    result = ChunkExtractionResult()
    assert result.entities == []
    assert result.relationships == []


def test_chunk_extraction_result_from_dict():
    data = {
        "entities": [
            {"name": "Project Phoenix", "entity_type": "Project", "confidence": 0.99}
        ],
        "relationships": [
            {
                "source_entity": "Project Phoenix",
                "source_type": "Project",
                "relationship_type": "USES",
                "target_entity": "StellarDB",
                "target_type": "Technology",
                "confidence": 0.97,
            }
        ],
    }
    result = ChunkExtractionResult.model_validate(data)
    assert len(result.entities) == 1
    assert len(result.relationships) == 1
    assert result.entities[0].name == "Project Phoenix"
    assert result.relationships[0].relationship_type == RelationshipType.USES
