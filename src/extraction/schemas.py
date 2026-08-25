"""
Pydantic schemas for the entity & relationship extraction pipeline.

These schemas serve three purposes:
  1. Validate LLM output — Pydantic raises ValidationError if Claude returns
     a type outside the ontology enum or a confidence outside [0, 1].
  2. Document the ontology in code — the enums ARE the ontology.
  3. Provide serializable data records stored in the extraction cache.

IMPORTANT: Every value in EntityType and RelationshipType is a CONTRACT.
Neo4j node labels (Phase 4) and Cypher query templates (Phase 8) will
reference these exact strings. Never change them without updating both.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Ontology definitions ──────────────────────────────────────────────────────

class EntityType(str, Enum):
    COMPANY    = "Company"
    PERSON     = "Person"
    PRODUCT    = "Product"
    PROJECT    = "Project"
    TECHNOLOGY = "Technology"
    TEAM       = "Team"
    DEPARTMENT = "Department"


class RelationshipType(str, Enum):
    ACQUIRED      = "ACQUIRED"       # Company  → Company
    DEVELOPED     = "DEVELOPED"      # Company/Team/Person → Technology/Product
    USES          = "USES"           # Project/Product → Technology
    DEPENDS_ON    = "DEPENDS_ON"     # Technology → Technology
    OWNS          = "OWNS"           # Company → Product/Project
    WORKS_FOR     = "WORKS_FOR"      # Person → Company/Team
    MANAGES       = "MANAGES"        # Person → Project/Team
    PART_OF       = "PART_OF"        # Team → Department; Department → Company
    LED_BY        = "LED_BY"         # Team/Department → Person
    CREATED_BY    = "CREATED_BY"     # Project/Product → Person/Team
    MAINTAINS     = "MAINTAINS"      # Team → Technology/Product
    PARTNERED_WITH = "PARTNERED_WITH" # Company → Company


# ── Per-entity / per-relationship models (Claude output) ─────────────────────

class ExtractedEntity(BaseModel):
    name: str = Field(
        description="Canonical entity name as written in the text. "
                    "Use the most complete form (e.g. 'TechNova Corporation', not 'TechNova')."
    )
    entity_type: EntityType
    description: str | None = Field(
        default=None,
        description="One sentence describing this entity based on context in the chunk.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedRelationship(BaseModel):
    source_entity: str = Field(description="Must match the 'name' of an entity in the entities list.")
    source_type: EntityType
    relationship_type: RelationshipType
    target_entity: str = Field(description="Must match the 'name' of an entity in the entities list.")
    target_type: EntityType
    supporting_text: str | None = Field(
        default=None,
        description="Short direct quote from the text that supports this relationship.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


# ── Chunk-level extraction result (direct Claude tool output) ─────────────────

class ChunkExtractionResult(BaseModel):
    """
    What Claude returns via the extraction tool.
    This is validated immediately after the API call.
    """
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


# ── Persisted record (stored in cache and output) ─────────────────────────────

class ExtractionRecord(BaseModel):
    """
    Complete extraction record for one chunk, including provenance and cost metadata.
    This is what gets stored in the cache and written to output/extractions.json.
    """
    chunk_id: str
    document_id: str
    source_file: str
    doc_hash: str
    section: str
    extraction: ChunkExtractionResult
    input_tokens: int
    output_tokens: int
    attempts: int               # how many API calls were needed (retry tracking)
    extracted_at: str           # ISO-8601 UTC
    model: str

    def to_dict(self) -> dict:
        return self.model_dump()


# ── Run-level stats ───────────────────────────────────────────────────────────

class ExtractionRunStats(BaseModel):
    chunks_processed: int = 0
    chunks_cached: int = 0
    chunks_failed: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
