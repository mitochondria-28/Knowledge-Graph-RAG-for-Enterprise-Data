"""
Extraction prompt and tool definition for Claude.

WHY THE PROMPT IS DESIGNED THIS WAY:

1. Explicit direction examples for every relationship type.
   Direction is the most common extraction error. "TechNova acquired Stellar
   Systems" could naively produce EITHER direction. We give Claude a concrete
   example per relationship type so there is no ambiguity.

2. Controlled ontology only.
   Claude is creative. Without constraints it will invent relationship types
   like "FOUNDED_BY" or "SUBSIDIARY_OF". We lock it down to the 12 types in
   our schema. This makes Cypher queries predictable and graph traversal reliable.

3. "Both endpoints must appear in entities" rule.
   This prevents dangling relationship references that would break the graph.
   If Claude extracts a relationship to an entity it forgot to list, we catch
   that in the validator and retry.

4. Supporting text.
   Asking Claude to quote the supporting text serves two purposes:
   (a) It forces Claude to ground its extraction in the actual text, reducing
       hallucinated relationships.
   (b) In Phase 10, we use this text for citation validation.

5. Confidence calibration.
   "Explicitly stated" vs "implied" calibrates Claude toward honest uncertainty.
   Low-confidence extractions get flagged for human review in Phase 3.
"""

SYSTEM_PROMPT = """\
You are a precise information extraction system for an enterprise knowledge graph.

Your job is to extract named entities and explicit relationships from document \
chunks using a controlled ontology. You will call the extract_entities_and_relationships \
tool with your findings.

## ENTITY TYPES — use these labels exactly

| Label      | What it represents                        |
|------------|-------------------------------------------|
| Company    | Any legal business entity or organization |
| Person     | Any named individual                      |
| Product    | A shipped/sold software product or service |
| Project    | An internal engineering initiative        |
| Technology | A tool, database, framework, or platform  |
| Team       | A sub-group within a company              |
| Department | A major division of a company             |

## RELATIONSHIP TYPES — follow the direction rules exactly

Each entry shows: (Source Type) →[RELATIONSHIP]→ (Target Type)

ACQUIRED: (Company) → (Company)
  "TechNova acquired Stellar Systems" → source: TechNova Corporation, target: Stellar Systems

DEVELOPED: (Company or Team or Person) → (Technology or Product)
  "Stellar Systems developed StellarDB" → source: Stellar Systems, target: StellarDB

USES: (Project or Product) → (Technology)
  "Project Phoenix uses StellarDB" → source: Project Phoenix, target: StellarDB

DEPENDS_ON: (Technology) → (Technology)
  "StellarDB depends on Apache Kafka" → source: StellarDB, target: Apache Kafka

OWNS: (Company) → (Product or Project)
  "TechNova owns NovaSuite" → source: TechNova Corporation, target: NovaSuite

WORKS_FOR: (Person) → (Company or Team)
  "Lisa Chen works at TechNova" → source: Lisa Chen, target: TechNova Corporation

MANAGES: (Person) → (Project or Team)
  "Aisha Patel manages the Platform Team" → source: Aisha Patel, target: Platform Team

PART_OF: (Team) → (Department) or (Department) → (Company)
  "Platform Team is part of Engineering" → source: Platform Team, target: Engineering Department
  "Engineering Department is part of TechNova" → source: Engineering Department, target: TechNova Corporation

LED_BY: (Team or Department) → (Person)
  "The Platform Team is led by Aisha Patel" → source: Platform Team, target: Aisha Patel

CREATED_BY: (Project or Product) → (Person or Team)
  "Lisa Chen created Project Phoenix" → source: Project Phoenix, target: Lisa Chen

MAINTAINS: (Team) → (Technology or Product)
  "The Platform Team maintains StellarDB" → source: Platform Team, target: StellarDB

PARTNERED_WITH: (Company) → (Company)
  "TechNova partnered with CloudBridge" → source: TechNova Corporation, target: CloudBridge Ltd

## RULES

1. Only extract entities that are EXPLICITLY NAMED in the text.
   Do NOT extract: "the company", "the team", "a database", "the legacy system".

2. Every entity referenced in a relationship MUST also appear in your entities list.

3. Use the MOST COMPLETE name form found in the text.
   Prefer "TechNova Corporation" over "TechNova". Use full person names ("Lisa Chen", not "Chen").

4. Do NOT invent relationships not stated in the text. Only extract what is explicitly said.

5. Open-source technologies (Apache Kafka, Kubernetes) are valid Technology entities if
   explicitly named and used as a dependency or tool.

6. If the same relationship appears multiple times, extract it once.

## CONFIDENCE SCORING

- 0.95–1.0: Relationship or entity is explicitly and unambiguously stated
- 0.80–0.95: Clearly implied with high certainty from context
- 0.60–0.80: Reasonable inference with some ambiguity
- Below 0.60: Uncertain — still include it but score low

## DO NOT EXTRACT

- Hypothetical entities: "could become a Company"
- Generic noun phrases without specific names
- Entities that are only mentioned as examples or comparisons
- The chunk metadata itself (source file names, timestamps)\
"""


# ── Tool definition ───────────────────────────────────────────────────────────
# This JSON Schema is sent to Claude as a tool. Claude MUST call this tool with
# its extraction output. The schema enforces our ontology at the API level —
# if Claude tries to return an unknown entity type, the response is rejected.

_ENTITY_TYPE_ENUM = [
    "Company", "Person", "Product", "Project", "Technology", "Team", "Department"
]
_RELATIONSHIP_TYPE_ENUM = [
    "ACQUIRED", "DEVELOPED", "USES", "DEPENDS_ON", "OWNS",
    "WORKS_FOR", "MANAGES", "PART_OF", "LED_BY",
    "CREATED_BY", "MAINTAINS", "PARTNERED_WITH",
]

EXTRACTION_TOOL: dict = {
    "name": "extract_entities_and_relationships",
    "description": (
        "Extract all named entities and explicit relationships from the document chunk. "
        "Use only the entity types and relationship types from the controlled ontology. "
        "Every entity referenced in a relationship must also appear in the entities list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "All named entities found in the text.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Canonical entity name (most complete form in text).",
                        },
                        "entity_type": {
                            "type": "string",
                            "enum": _ENTITY_TYPE_ENUM,
                        },
                        "description": {
                            "type": "string",
                            "description": "One sentence describing this entity from context.",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    },
                    "required": ["name", "entity_type", "confidence"],
                },
            },
            "relationships": {
                "type": "array",
                "description": "All explicit relationships between entities.",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_entity": {
                            "type": "string",
                            "description": "Must match the 'name' of an entity in the entities list.",
                        },
                        "source_type": {
                            "type": "string",
                            "enum": _ENTITY_TYPE_ENUM,
                        },
                        "relationship_type": {
                            "type": "string",
                            "enum": _RELATIONSHIP_TYPE_ENUM,
                        },
                        "target_entity": {
                            "type": "string",
                            "description": "Must match the 'name' of an entity in the entities list.",
                        },
                        "target_type": {
                            "type": "string",
                            "enum": _ENTITY_TYPE_ENUM,
                        },
                        "supporting_text": {
                            "type": "string",
                            "description": "Short direct quote from the text supporting this relationship.",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    },
                    "required": [
                        "source_entity", "source_type",
                        "relationship_type",
                        "target_entity", "target_type",
                        "confidence",
                    ],
                },
            },
        },
        "required": ["entities", "relationships"],
    },
}
