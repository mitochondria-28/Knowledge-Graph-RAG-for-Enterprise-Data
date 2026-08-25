"""
Unit tests for src/graph/loader.py and src/graph/schema.py.

All tests use unittest.mock — no running Neo4j required.

Tests verify:
  - Cypher query generation produces correct labels / relationship types
  - Only enum-allowlisted labels / types are accepted
  - Entities are grouped correctly by type before merging
  - Batch splitting works for large lists
  - Schema DDL uses IF NOT EXISTS
  - Parameter dicts contain all expected keys
"""

import pytest
from unittest.mock import MagicMock, call, patch

from src.graph.loader import (
    _entity_merge_cypher,
    _entity_to_params,
    _rel_to_params,
    _relationship_merge_cypher,
    _VALID_ENTITY_LABELS,
    _VALID_REL_TYPES,
    load_entities,
    load_relationships,
)
from src.graph.schema import _CONSTRAINTS, _INDEXES, create_schema


# ── Cypher generation ─────────────────────────────────────────────────────────

class TestEntityMergeCypher:
    def test_company_label_in_query(self):
        cypher = _entity_merge_cypher("Company")
        assert ":Entity:Company" in cypher

    def test_person_label_in_query(self):
        cypher = _entity_merge_cypher("Person")
        assert ":Entity:Person" in cypher

    def test_all_entity_labels_produce_valid_cypher(self):
        for label in _VALID_ENTITY_LABELS:
            cypher = _entity_merge_cypher(label)
            assert "MERGE" in cypher
            assert "UNWIND $batch" in cypher
            assert f":Entity:{label}" in cypher

    def test_invalid_label_raises(self):
        with pytest.raises(AssertionError):
            _entity_merge_cypher("Hacker'; DROP DATABASE neo4j; //")

    def test_cypher_uses_canonical_id_for_merge_key(self):
        cypher = _entity_merge_cypher("Company")
        assert "canonical_id: e.canonical_id" in cypher

    def test_cypher_sets_all_required_properties(self):
        cypher = _entity_merge_cypher("Technology")
        for prop in ["canonical_name", "entity_type", "mention_count",
                     "avg_confidence", "description", "aliases",
                     "source_files", "chunk_ids", "resolved_at"]:
            assert prop in cypher, f"Missing property: {prop}"


class TestRelationshipMergeCypher:
    def test_acquired_rel_type_in_query(self):
        cypher = _relationship_merge_cypher("ACQUIRED")
        assert "-[rel:ACQUIRED]->" in cypher

    def test_all_rel_types_produce_valid_cypher(self):
        for rtype in _VALID_REL_TYPES:
            cypher = _relationship_merge_cypher(rtype)
            assert f"-[rel:{rtype}]->" in cypher
            assert "UNWIND $batch" in cypher
            assert "MATCH (src:Entity" in cypher
            assert "MATCH (tgt:Entity" in cypher

    def test_invalid_rel_type_raises(self):
        with pytest.raises(AssertionError):
            _relationship_merge_cypher("EVIL_INJECTION")

    def test_cypher_uses_canonical_id_for_node_match(self):
        cypher = _relationship_merge_cypher("USES")
        assert "canonical_id: r.source_id" in cypher
        assert "canonical_id: r.target_id" in cypher

    def test_cypher_sets_all_rel_properties(self):
        cypher = _relationship_merge_cypher("MAINTAINS")
        for prop in ["mention_count", "avg_confidence", "source_files",
                     "chunk_ids", "supporting_texts"]:
            assert prop in cypher, f"Missing rel property: {prop}"


# ── Parameter extraction ──────────────────────────────────────────────────────

class TestEntityToParams:
    def _sample_entity(self, **overrides):
        base = {
            "canonical_id": "uuid-001",
            "canonical_name": "TechNova Corporation",
            "entity_type": "Company",
            "mention_count": 9,
            "avg_confidence": 0.98,
            "description": "An enterprise software company.",
            "aliases": ["TechNova Corp", "TechNova"],
            "source_files": ["corpus/companies/technova_overview.md"],
            "chunk_ids": ["c1", "c2"],
            "resolved_at": "2024-01-15T10:00:00+00:00",
        }
        base.update(overrides)
        return base

    def test_all_keys_present(self):
        params = _entity_to_params(self._sample_entity())
        expected_keys = {
            "canonical_id", "canonical_name", "entity_type", "mention_count",
            "avg_confidence", "description", "aliases", "source_files",
            "chunk_ids", "resolved_at",
        }
        assert set(params.keys()) == expected_keys

    def test_values_passed_through(self):
        entity = self._sample_entity()
        params = _entity_to_params(entity)
        assert params["canonical_name"] == "TechNova Corporation"
        assert params["mention_count"] == 9
        assert params["aliases"] == ["TechNova Corp", "TechNova"]

    def test_missing_optional_fields_default_to_empty(self):
        entity = {
            "canonical_id": "x",
            "canonical_name": "X",
            "entity_type": "Company",
            "mention_count": 1,
            "avg_confidence": 0.9,
        }
        params = _entity_to_params(entity)
        assert params["description"] is None
        assert params["aliases"] == []
        assert params["source_files"] == []
        assert params["chunk_ids"] == []


class TestRelToParams:
    def _sample_rel(self, **overrides):
        base = {
            "source_id": "uuid-src",
            "target_id": "uuid-tgt",
            "relationship_type": "ACQUIRED",
            "mention_count": 2,
            "avg_confidence": 0.97,
            "source_files": ["f.md"],
            "chunk_ids": ["c1"],
            "supporting_texts": ["TechNova acquired Stellar Systems."],
        }
        base.update(overrides)
        return base

    def test_all_keys_present(self):
        params = _rel_to_params(self._sample_rel())
        expected_keys = {
            "source_id", "target_id", "mention_count", "avg_confidence",
            "source_files", "chunk_ids", "supporting_texts",
        }
        assert set(params.keys()) == expected_keys

    def test_missing_optional_fields_default_empty(self):
        rel = {"source_id": "a", "target_id": "b",
               "relationship_type": "USES", "mention_count": 1, "avg_confidence": 0.9}
        params = _rel_to_params(rel)
        assert params["source_files"] == []
        assert params["chunk_ids"] == []
        assert params["supporting_texts"] == []


# ── load_entities (with mocked session) ──────────────────────────────────────

def _mock_session_result(processed_count: int = 1):
    """Return a mock Neo4j result that has a .single()['processed'] value."""
    single_mock = MagicMock()
    single_mock.__getitem__ = lambda self, key: processed_count
    result_mock = MagicMock()
    result_mock.single.return_value = single_mock
    return result_mock


class TestLoadEntities:
    def _make_entities(self, count: int, entity_type: str = "Company"):
        return [
            {
                "canonical_id": f"id-{i}",
                "canonical_name": f"Company {i}",
                "entity_type": entity_type,
                "mention_count": 1,
                "avg_confidence": 0.9,
                "description": None,
                "aliases": [],
                "source_files": [],
                "chunk_ids": [],
                "resolved_at": "",
            }
            for i in range(count)
        ]

    def test_session_run_called_once_for_single_type_under_batch_size(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(3)
        entities = self._make_entities(3, "Company")
        counts = load_entities(session, entities, batch_size=500)
        assert session.run.call_count == 1
        assert counts["Company"] == 3

    def test_batch_splitting_calls_run_multiple_times(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(2)
        # 5 entities with batch_size=2 → ceil(5/2) = 3 batches
        entities = self._make_entities(5, "Person")
        load_entities(session, entities, batch_size=2)
        assert session.run.call_count == 3

    def test_two_entity_types_run_separately(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(1)
        entities = self._make_entities(2, "Company") + self._make_entities(3, "Technology")
        load_entities(session, entities, batch_size=500)
        # One run() call per entity type
        assert session.run.call_count == 2

    def test_correct_label_in_cypher_for_each_type(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(1)
        entities = self._make_entities(1, "Person")
        load_entities(session, entities)
        call_args = session.run.call_args
        assert ":Entity:Person" in call_args[0][0]

    def test_unknown_entity_type_skipped(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(0)
        entities = [{"canonical_id": "x", "canonical_name": "X",
                     "entity_type": "UNKNOWN_TYPE", "mention_count": 1, "avg_confidence": 0.9}]
        counts = load_entities(session, entities)
        assert session.run.call_count == 0
        assert counts == {}

    def test_empty_entities_no_db_calls(self):
        session = MagicMock()
        counts = load_entities(session, [])
        assert session.run.call_count == 0
        assert counts == {}


# ── load_relationships (with mocked session) ──────────────────────────────────

class TestLoadRelationships:
    def _make_rels(self, count: int, rel_type: str = "ACQUIRED"):
        return [
            {
                "source_id": f"src-{i}",
                "target_id": f"tgt-{i}",
                "relationship_type": rel_type,
                "mention_count": 1,
                "avg_confidence": 0.9,
                "source_files": [],
                "chunk_ids": [],
                "supporting_texts": [],
            }
            for i in range(count)
        ]

    def test_session_run_called_once_for_single_type(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(2)
        rels = self._make_rels(2, "ACQUIRED")
        counts = load_relationships(session, rels, batch_size=500)
        assert session.run.call_count == 1
        assert counts["ACQUIRED"] == 2

    def test_correct_rel_type_in_cypher(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(1)
        rels = self._make_rels(1, "MAINTAINS")
        load_relationships(session, rels)
        cypher = session.run.call_args[0][0]
        assert "-[rel:MAINTAINS]->" in cypher

    def test_batch_splitting_for_relationships(self):
        session = MagicMock()
        session.run.return_value = _mock_session_result(1)
        # 7 rels with batch_size=3 → ceil(7/3) = 3 calls
        rels = self._make_rels(7, "USES")
        load_relationships(session, rels, batch_size=3)
        assert session.run.call_count == 3

    def test_unknown_rel_type_skipped(self):
        session = MagicMock()
        rels = self._make_rels(1, "NOT_A_REAL_TYPE")
        counts = load_relationships(session, rels)
        assert session.run.call_count == 0
        assert counts == {}

    def test_empty_rels_no_db_calls(self):
        session = MagicMock()
        counts = load_relationships(session, [])
        assert session.run.call_count == 0
        assert counts == {}


# ── schema ────────────────────────────────────────────────────────────────────

class TestSchema:
    def test_create_schema_runs_all_statements(self):
        session = MagicMock()
        create_schema(session)
        total_statements = len(_CONSTRAINTS) + len(_INDEXES)
        assert session.run.call_count == total_statements

    def test_all_constraints_use_if_not_exists(self):
        for ddl in _CONSTRAINTS:
            assert "IF NOT EXISTS" in ddl.upper(), \
                f"Constraint missing IF NOT EXISTS: {ddl[:60]}"

    def test_all_indexes_use_if_not_exists(self):
        for ddl in _INDEXES:
            assert "IF NOT EXISTS" in ddl.upper(), \
                f"Index missing IF NOT EXISTS: {ddl[:60]}"

    def test_uniqueness_constraint_covers_canonical_id(self):
        combined = " ".join(_CONSTRAINTS)
        assert "canonical_id" in combined
        assert "UNIQUE" in combined.upper()
