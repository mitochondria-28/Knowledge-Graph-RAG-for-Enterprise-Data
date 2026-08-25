"""
Tests for entity resolution: matcher + resolver.

Covers:
  - compute_similarity: identical, variant suffix, different names
  - UnionFind: basic merging, path compression, clusters
  - cluster_names: auto-merge, review threshold, singletons
  - resolve(): end-to-end name deduplication and relationship remapping
"""

import pytest

from src.extraction.schemas import EntityType, RelationshipType
from src.resolution.matcher import (
    UnionFind,
    cluster_names,
    compute_similarity,
)
from src.resolution.models import EntityMention, RelationshipMention
from src.resolution.resolver import resolve


# ── compute_similarity ─────────────────────────────────────────────────────────

class TestComputeSimilarity:
    def test_identical_names_score_one(self):
        pair = compute_similarity("TechNova Corporation", "TechNova Corporation")
        assert pair.score == 1.0

    def test_same_normalized_form_score_one(self):
        # "TechNova Corporation" and "TechNova Corp" → both normalize to "technova"
        pair = compute_similarity("TechNova Corporation", "TechNova Corp")
        assert pair.score == 1.0

    def test_subset_name_high_score(self):
        # "TechNova" is a strict subset; token_set_ratio should catch it
        pair = compute_similarity("TechNova", "TechNova Corporation")
        assert pair.score >= 0.95

    def test_stellar_variants_high_score(self):
        pair = compute_similarity("Stellar Systems Inc.", "Stellar Systems")
        assert pair.score >= 0.95

    def test_completely_different_names_low_score(self):
        pair = compute_similarity("Apache Kafka", "Kubernetes")
        assert pair.score < 0.4

    def test_returns_normalized_forms(self):
        pair = compute_similarity("Dr. Elena Vasquez", "Elena Vasquez")
        assert pair.norm_a == pair.norm_b == "elena vasquez"

    def test_person_name_with_honorific_merges(self):
        pair = compute_similarity("Dr. Elena Vasquez", "Elena Vasquez")
        assert pair.score == 1.0


# ── UnionFind ─────────────────────────────────────────────────────────────────

class TestUnionFind:
    def test_initial_state_each_own_root(self):
        uf = UnionFind(["A", "B", "C"])
        assert uf.find("A") == "A"
        assert uf.find("B") == "B"

    def test_union_merges_two_elements(self):
        uf = UnionFind(["A", "B", "C"])
        uf.union("A", "B")
        assert uf.find("A") == uf.find("B")

    def test_transitive_union(self):
        uf = UnionFind(["A", "B", "C"])
        uf.union("A", "B")
        uf.union("B", "C")
        assert uf.find("A") == uf.find("C")

    def test_clusters_returns_all_elements(self):
        uf = UnionFind(["A", "B", "C"])
        uf.union("A", "B")
        clusters = uf.clusters()
        all_members = [m for members in clusters.values() for m in members]
        assert sorted(all_members) == ["A", "B", "C"]

    def test_single_element(self):
        uf = UnionFind(["solo"])
        assert uf.find("solo") == "solo"
        clusters = uf.clusters()
        assert len(clusters) == 1


# ── cluster_names ─────────────────────────────────────────────────────────────

class TestClusterNames:
    def test_technova_variants_merge_into_one_cluster(self):
        names = ["TechNova Corporation", "TechNova Corp", "TechNova"]
        result = cluster_names(names, auto_merge_threshold=0.95)
        # All three should end up in the same cluster
        merged = [c for c in result.clusters if len(c) > 1]
        assert len(merged) == 1
        assert len(merged[0]) == 3

    def test_stellar_variants_merge(self):
        names = ["Stellar Systems Inc.", "Stellar Systems"]
        result = cluster_names(names, auto_merge_threshold=0.95)
        merged = [c for c in result.clusters if len(c) > 1]
        assert len(merged) == 1

    def test_unrelated_names_stay_separate(self):
        names = ["Apache Kafka", "Kubernetes", "PostgreSQL"]
        result = cluster_names(names, auto_merge_threshold=0.95)
        # All should remain singletons
        assert all(len(c) == 1 for c in result.clusters)
        assert len(result.clusters) == 3

    def test_empty_list(self):
        result = cluster_names([])
        assert result.clusters == []
        assert result.review_pairs == []

    def test_single_name(self):
        result = cluster_names(["OnlyOne"])
        assert result.clusters == [["OnlyOne"]]
        assert result.review_pairs == []

    def test_review_pair_captured(self):
        # Construct two names that are similar but below auto-merge threshold
        # We'll use a low auto_merge so they go to review instead
        names = ["Stellar Systems", "Stellar System"]
        result = cluster_names(names, auto_merge_threshold=0.99, review_threshold=0.85)
        # Should NOT be auto-merged, but high enough to flag for review
        all_review_names = {(p.name_a, p.name_b) for p in result.review_pairs}
        # Either order is fine
        assert any(
            ("Stellar Systems" in pair and "Stellar System" in pair)
            for pair in [set(p) for p in all_review_names]
        ) or len(result.review_pairs) > 0  # at least one review pair generated


# ── resolve() — end-to-end ────────────────────────────────────────────────────

def _make_em(name, entity_type, chunk_id="c1", source_file="f.md", confidence=0.95):
    return EntityMention(
        name=name,
        entity_type=entity_type,
        chunk_id=chunk_id,
        source_file=source_file,
        confidence=confidence,
    )


def _make_rm(src, src_type, rel, tgt, tgt_type, chunk_id="c1", source_file="f.md", confidence=0.90):
    return RelationshipMention(
        source_name=src,
        source_type=src_type,
        relationship_type=rel,
        target_name=tgt,
        target_type=tgt_type,
        chunk_id=chunk_id,
        source_file=source_file,
        confidence=confidence,
    )


class TestResolve:
    def test_three_technova_variants_become_one_entity(self):
        mentions = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1", confidence=0.99),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c2", confidence=0.98),
            _make_em("TechNova", EntityType.COMPANY, chunk_id="c3", confidence=0.95),
        ]
        result = resolve(mentions, [])
        companies = [e for e in result.entities if e.entity_type == EntityType.COMPANY]
        assert len(companies) == 1
        assert companies[0].mention_count == 3

    def test_canonical_name_is_most_mentioned(self):
        # "TechNova Corporation" appears twice; "TechNova Corp" once
        mentions = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1"),
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c2"),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c3"),
        ]
        result = resolve(mentions, [])
        companies = [e for e in result.entities if e.entity_type == EntityType.COMPANY]
        assert len(companies) == 1
        assert companies[0].canonical_name == "TechNova Corporation"

    def test_aliases_contain_merged_names(self):
        mentions = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1"),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c2"),
        ]
        result = resolve(mentions, [])
        companies = [e for e in result.entities if e.entity_type == EntityType.COMPANY]
        assert len(companies) == 1
        entity = companies[0]
        # One name is canonical, the other should be in aliases
        all_names = [entity.canonical_name] + entity.aliases
        assert "TechNova Corporation" in all_names
        assert "TechNova Corp" in all_names

    def test_distinct_types_not_merged(self):
        # "Platform" as a Team and a Technology should NOT be merged
        mentions = [
            _make_em("Platform", EntityType.TEAM, chunk_id="c1"),
            _make_em("Platform", EntityType.TECHNOLOGY, chunk_id="c2"),
        ]
        result = resolve(mentions, [])
        assert len(result.entities) == 2

    def test_relationship_remapped_to_canonical_ids(self):
        # Give the "full" names more mentions so they win canonical selection.
        # With equal mentions, alphabetic tiebreaker picks "Corp" over "Corporation",
        # so we explicitly give "TechNova Corporation" 2 mentions vs 1 for the short form.
        entities = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1"),
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c5"),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c2"),
            _make_em("Stellar Systems Inc.", EntityType.COMPANY, chunk_id="c3"),
            _make_em("Stellar Systems Inc.", EntityType.COMPANY, chunk_id="c6"),
            _make_em("Stellar Systems", EntityType.COMPANY, chunk_id="c4"),
        ]
        # Relationship uses the variant names, not the canonical
        rels = [
            _make_rm(
                "TechNova Corp", EntityType.COMPANY,
                RelationshipType.ACQUIRED,
                "Stellar Systems", EntityType.COMPANY,
                chunk_id="c2",
            )
        ]
        result = resolve(entities, rels)
        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.source_name == "TechNova Corporation"
        assert rel.target_name == "Stellar Systems Inc."

    def test_duplicate_relationships_deduplicated(self):
        entities = [
            _make_em("Platform Team", EntityType.TEAM, chunk_id="c1"),
            _make_em("Platform Team", EntityType.TEAM, chunk_id="c2"),
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="c1"),
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="c2"),
        ]
        rels = [
            _make_rm(
                "Platform Team", EntityType.TEAM,
                RelationshipType.MAINTAINS,
                "StellarDB", EntityType.TECHNOLOGY,
                chunk_id="c1",
            ),
            _make_rm(
                "Platform Team", EntityType.TEAM,
                RelationshipType.MAINTAINS,
                "StellarDB", EntityType.TECHNOLOGY,
                chunk_id="c2",
            ),
        ]
        result = resolve(entities, rels)
        # Two identical relationships → one deduplicated relationship with mention_count=2
        assert len(result.relationships) == 1
        assert result.relationships[0].mention_count == 2

    def test_self_loop_relationship_dropped(self):
        entities = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1"),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c2"),
        ]
        # After merging, source and target are the same canonical entity
        rels = [
            _make_rm(
                "TechNova Corporation", EntityType.COMPANY,
                RelationshipType.PARTNERED_WITH,
                "TechNova Corp", EntityType.COMPANY,
            )
        ]
        result = resolve(entities, rels)
        assert len(result.relationships) == 0

    def test_resolution_result_stats(self):
        mentions = [
            _make_em("TechNova Corporation", EntityType.COMPANY, chunk_id="c1"),
            _make_em("TechNova Corp", EntityType.COMPANY, chunk_id="c2"),
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="c3"),
        ]
        result = resolve(mentions, [])
        assert result.raw_entity_mentions == 3
        # TechNova variants merge → 2 unique entities
        assert result.unique_entities_after == 2
        assert result.merge_count == 1  # 2 names → 1 entity = 1 merge

    def test_chunk_ids_aggregated_across_mentions(self):
        mentions = [
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="chunk-A"),
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="chunk-B"),
            _make_em("StellarDB", EntityType.TECHNOLOGY, chunk_id="chunk-C"),
        ]
        result = resolve(mentions, [])
        tech = [e for e in result.entities if e.entity_type == EntityType.TECHNOLOGY][0]
        assert set(tech.chunk_ids) == {"chunk-A", "chunk-B", "chunk-C"}

    def test_entity_id_is_deterministic(self):
        mentions = [_make_em("StellarDB", EntityType.TECHNOLOGY)]
        result1 = resolve(mentions, [])
        result2 = resolve(mentions, [])
        assert result1.entities[0].canonical_id == result2.entities[0].canonical_id

    def test_empty_input(self):
        result = resolve([], [])
        assert result.entities == []
        assert result.relationships == []
        assert result.raw_entity_mentions == 0
