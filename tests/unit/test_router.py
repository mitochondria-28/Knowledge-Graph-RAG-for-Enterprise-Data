"""
Unit tests for the question router (Phase 7).

Tests verify:
  1. Feature extraction (signals.py) — each signal is correct in isolation
  2. Routing decisions (classifier.py) — rules produce expected strategies
  3. Entity detection and deduplication
  4. Edge cases (empty question, no entities, all signals present)

No databases or API keys required — all tests are pure function calls.
"""

import pytest

from src.router.classifier import route
from src.router.models import RouteFeatures, RoutingDecision
from src.router.signals import (
    _deduplicate_entities,
    build_entity_index,
    extract_features,
)


# ── Shared entity index fixture ───────────────────────────────────────────────

@pytest.fixture
def entity_index() -> dict[str, str]:
    """Minimal entity index matching TechNova corpus canonical names."""
    return {
        "TechNova Corporation": "Company",
        "TechNova Corp":        "Company",   # alias
        "TechNova":             "Company",   # alias
        "Stellar Systems":      "Company",
        "Stellar Systems Inc.": "Company",   # alias
        "Apex Analytics":       "Company",
        "StellarDB":            "Technology",
        "ApexML":               "Technology",
        "Apache Kafka":         "Technology",
        "DataBridge":           "Product",
        "NovaSuite":            "Product",
        "Platform Team":        "Team",
        "Data Engineering Team": "Team",
        "ML Team":              "Team",
        "Engineering Department": "Department",
        "Aisha Patel":          "Person",
        "Sandra Müller":        "Person",
        "Marcus Thompson":      "Person",
        "Robert Klein":         "Person",
        "Project Phoenix":      "Project",
        "Project Nexus":        "Project",
    }


# ── Feature extraction — entity detection ─────────────────────────────────────

class TestEntityDetection:
    def test_detects_canonical_name(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        assert "StellarDB" in f.detected_entities

    def test_detects_alias(self, entity_index):
        f = extract_features("When did TechNova Corp acquire Stellar Systems?", entity_index)
        # TechNova Corp is an alias → should be detected
        names_lower = [n.lower() for n in f.detected_entities]
        assert any("technova" in n for n in names_lower)

    def test_detects_multiple_entities(self, entity_index):
        f = extract_features(
            "What is the relationship between StellarDB and ApexML?", entity_index
        )
        assert len(f.detected_entities) >= 2

    def test_no_false_positives_on_empty(self, entity_index):
        f = extract_features("How does machine learning work?", entity_index)
        assert f.detected_entities == []

    def test_entity_count_matches_detected(self, entity_index):
        f = extract_features("StellarDB and ApexML both use Apache Kafka", entity_index)
        assert f.entity_count == len(f.detected_entities)

    def test_case_insensitive_detection(self, entity_index):
        f = extract_features("who manages the platform team?", entity_index)
        assert "Platform Team" in f.detected_entities


class TestEntityDeduplication:
    def test_shorter_substring_removed(self):
        names = ["Stellar Systems Inc.", "Stellar Systems", "Stellar"]
        result = _deduplicate_entities(names)
        assert len(result) == 1
        assert result[0] == "Stellar Systems Inc."

    def test_non_overlapping_names_kept(self):
        names = ["StellarDB", "ApexML"]
        result = _deduplicate_entities(names)
        assert len(result) == 2

    def test_empty_input(self):
        assert _deduplicate_entities([]) == []

    def test_single_name_unchanged(self):
        assert _deduplicate_entities(["TechNova Corporation"]) == ["TechNova Corporation"]


# ── Feature extraction — linguistic signals ───────────────────────────────────

class TestDefinitionPattern:
    def test_what_is(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        assert f.is_definition is True

    def test_what_are(self, entity_index):
        f = extract_features("What are the main features of StellarDB?", entity_index)
        assert f.is_definition is True

    def test_what_does_do(self, entity_index):
        f = extract_features("What does StellarDB do?", entity_index)
        assert f.is_definition is True

    def test_non_definition(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        assert f.is_definition is False


class TestTemporalPattern:
    def test_when_did(self, entity_index):
        f = extract_features("When did TechNova acquire Stellar Systems?", entity_index)
        assert f.is_temporal is True

    def test_when_was(self, entity_index):
        f = extract_features("When was TechNova founded?", entity_index)
        assert f.is_temporal is True

    def test_non_temporal(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        assert f.is_temporal is False


class TestPersonQuery:
    def test_who_question(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        assert f.is_person_query is True
        assert f.question_word == "who"

    def test_what_is_not_person_query(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        assert f.is_person_query is False


class TestRelationalVerbs:
    def test_leads(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        assert f.has_relational_pattern is True
        assert "leads" in f.relational_verbs_found

    def test_maintains(self, entity_index):
        f = extract_features("The Platform Team maintains StellarDB", entity_index)
        assert "maintains" in f.relational_verbs_found

    def test_acquired(self, entity_index):
        f = extract_features("TechNova acquired Stellar Systems", entity_index)
        assert f.has_acquisition_language is True

    def test_no_relational_verb(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        assert f.has_relational_pattern is False


class TestHopDepth:
    def test_no_hops_for_definition(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        assert f.hop_depth <= 1

    def test_one_hop_for_direct_relationship(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        assert f.hop_depth >= 1

    def test_multi_hop_for_chained_clause(self, entity_index):
        q = "Who leads the team that maintains StellarDB?"
        f = extract_features(q, entity_index)
        assert f.has_multi_hop_pattern is True
        assert f.hop_depth >= 2

    def test_multi_hop_for_acquired_from(self, entity_index):
        q = "What projects use technology acquired from Stellar Systems?"
        f = extract_features(q, entity_index)
        assert f.has_multi_hop_pattern is True


# ── Routing decisions ─────────────────────────────────────────────────────────

def _features(**kwargs) -> RouteFeatures:
    """Build RouteFeatures with defaults for fields not specified."""
    defaults = dict(
        detected_entities=[],
        entity_count=0,
        question_word="what",
        is_definition=False,
        is_temporal=False,
        is_person_query=False,
        relational_verbs_found=[],
        relative_clause_count=0,
        hop_depth=0,
        has_relational_pattern=False,
        has_multi_hop_pattern=False,
        has_acquisition_language=False,
    )
    defaults.update(kwargs)
    return RouteFeatures(**defaults)


class TestRoutingRules:
    # R1: Multi-hop + entities → GRAPH
    def test_r1_multi_hop_with_entities(self):
        f = _features(
            detected_entities=["StellarDB", "Platform Team"],
            entity_count=2,
            has_multi_hop_pattern=True,
            hop_depth=2,
        )
        d = route(f)
        assert d.strategy == "graph"
        assert d.hop_depth >= 2
        assert d.confidence >= 0.85

    # R2: Multi-hop without entities → HYBRID
    def test_r2_multi_hop_no_entities(self):
        f = _features(has_multi_hop_pattern=True, hop_depth=2)
        d = route(f)
        assert d.strategy == "hybrid"

    # R3: "Who" + relational verb → GRAPH
    def test_r3_person_query_with_relational_verb(self):
        f = _features(
            is_person_query=True,
            has_relational_pattern=True,
            relational_verbs_found=["leads"],
            detected_entities=["Platform Team"],
            entity_count=1,
            hop_depth=1,
        )
        d = route(f)
        assert d.strategy == "graph"

    # R4: Relational verb + entity → GRAPH
    def test_r4_relational_with_entity(self):
        f = _features(
            has_relational_pattern=True,
            relational_verbs_found=["maintains"],
            detected_entities=["StellarDB"],
            entity_count=1,
            hop_depth=1,
        )
        d = route(f)
        assert d.strategy == "graph"

    # R5: Definition pattern → VECTOR
    def test_r5_definition_pattern(self):
        f = _features(is_definition=True)
        d = route(f)
        assert d.strategy == "vector"
        assert d.confidence >= 0.80

    # R6: Temporal pattern → VECTOR
    def test_r6_temporal_pattern(self):
        f = _features(is_temporal=True)
        d = route(f)
        assert d.strategy == "vector"

    # R7: Many entities → HYBRID
    def test_r7_many_entities(self):
        f = _features(
            detected_entities=["TechNova Corporation", "Stellar Systems", "Apex Analytics"],
            entity_count=3,
        )
        d = route(f)
        assert d.strategy == "hybrid"

    # R8: Acquisition language + entities → GRAPH
    def test_r8_acquisition_language(self):
        f = _features(
            has_acquisition_language=True,
            detected_entities=["TechNova Corporation", "Stellar Systems"],
            entity_count=2,
        )
        d = route(f)
        assert d.strategy == "graph"
        assert d.hop_depth >= 2

    # R9: Single entity, no relational → VECTOR
    def test_r9_single_entity_no_relation(self):
        f = _features(
            detected_entities=["StellarDB"],
            entity_count=1,
        )
        d = route(f)
        assert d.strategy == "vector"

    # R10: Default fallback → HYBRID
    def test_r10_default_fallback(self):
        f = _features()  # all defaults = no signals
        d = route(f)
        assert d.strategy == "hybrid"
        assert d.confidence < 0.70  # low confidence on fallback


# ── End-to-end: full question → routing decision ──────────────────────────────

class TestEndToEnd:
    """Integration tests using real question text + entity index."""

    def test_simple_entity_routes_to_vector(self, entity_index):
        f = extract_features("What is StellarDB?", entity_index)
        d = route(f)
        assert d.strategy == "vector"

    def test_temporal_routes_to_vector(self, entity_index):
        f = extract_features("When did TechNova acquire Stellar Systems?", entity_index)
        d = route(f)
        assert d.strategy == "vector"

    def test_one_hop_person_routes_to_graph(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        d = route(f)
        assert d.strategy == "graph"

    def test_two_hop_routes_to_graph(self, entity_index):
        f = extract_features(
            "Who leads the team that maintains StellarDB?", entity_index
        )
        d = route(f)
        assert d.strategy == "graph"
        assert d.hop_depth >= 2

    def test_three_hop_routes_to_graph(self, entity_index):
        f = extract_features(
            "Who leads the team responsible for technology developed by a company "
            "TechNova acquired?",
            entity_index,
        )
        d = route(f)
        assert d.strategy == "graph"

    def test_multi_entity_routes_to_hybrid_or_graph(self, entity_index):
        f = extract_features(
            "What acquisitions has TechNova made and what technology did each bring?",
            entity_index,
        )
        d = route(f)
        # Multi-entity question → graph or hybrid both acceptable
        assert d.strategy in ("graph", "hybrid")

    def test_decision_contains_detected_entities(self, entity_index):
        f = extract_features("Who leads the Platform Team?", entity_index)
        d = route(f)
        assert "Platform Team" in d.detected_entities

    def test_all_decisions_have_reason(self, entity_index):
        questions = [
            "What is StellarDB?",
            "When did TechNova acquire Stellar Systems?",
            "Who leads the Platform Team?",
            "Who leads the team that maintains StellarDB?",
        ]
        for q in questions:
            f = extract_features(q, entity_index)
            d = route(f)
            assert d.reason, f"Empty reason for: {q}"

    def test_confidence_is_valid_range(self, entity_index):
        questions = [
            "What is StellarDB?",
            "Who leads the team that maintains StellarDB?",
            "When did TechNova acquire Apex Analytics?",
        ]
        for q in questions:
            f = extract_features(q, entity_index)
            d = route(f)
            assert 0.0 <= d.confidence <= 1.0, f"Confidence {d.confidence} out of range"


# ── build_entity_index ────────────────────────────────────────────────────────

class TestBuildEntityIndex:
    def test_canonical_names_included(self):
        entities = [
            {"canonical_name": "TechNova Corporation", "entity_type": "Company", "aliases": []},
        ]
        idx = build_entity_index(entities)
        assert "TechNova Corporation" in idx
        assert idx["TechNova Corporation"] == "Company"

    def test_aliases_included(self):
        entities = [
            {
                "canonical_name": "TechNova Corporation",
                "entity_type": "Company",
                "aliases": ["TechNova Corp", "TechNova"],
            }
        ]
        idx = build_entity_index(entities)
        assert "TechNova Corp" in idx
        assert "TechNova" in idx
        assert idx["TechNova Corp"] == "Company"

    def test_empty_entities(self):
        assert build_entity_index([]) == {}

    def test_multiple_entity_types(self):
        entities = [
            {"canonical_name": "StellarDB", "entity_type": "Technology", "aliases": []},
            {"canonical_name": "Platform Team", "entity_type": "Team", "aliases": []},
        ]
        idx = build_entity_index(entities)
        assert idx["StellarDB"] == "Technology"
        assert idx["Platform Team"] == "Team"
