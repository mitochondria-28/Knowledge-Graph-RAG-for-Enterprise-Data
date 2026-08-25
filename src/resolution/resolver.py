"""
Core entity resolution algorithm.

Takes all entity and relationship mentions from extraction output and
produces deduplicated, canonical entities and relationships.

FLOW:

  1. Build EntityMention + RelationshipMention lists from extraction records
  2. For each entity type, get unique names and cluster by similarity
  3. Per cluster: pick canonical name, collect aliases + chunk_ids
  4. Build a name → canonical_id lookup for relationship remapping
  5. Remap relationships: replace raw names with canonical IDs
  6. Deduplicate relationships: merge mentions of the same canonical relationship
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from src.extraction.schemas import EntityType, RelationshipType
from src.resolution.matcher import ClusteringResult, cluster_names
from src.resolution.models import (
    EntityMention,
    RelationshipMention,
    ResolvedEntity,
    ResolvedRelationship,
    ResolutionResult,
    ReviewItem,
    make_entity_id,
    make_relationship_id,
)
from src.resolution.normalizer import canonical_sort_key, normalize_for_comparison

logger = logging.getLogger(__name__)


def resolve(
    entity_mentions: list[EntityMention],
    relationship_mentions: list[RelationshipMention],
    auto_merge_threshold: float = 0.95,
    review_threshold: float = 0.82,
) -> ResolutionResult:
    """
    Run the full entity resolution pipeline.

    Args:
        entity_mentions:       All entity mentions from all chunks.
        relationship_mentions: All relationship mentions from all chunks.
        auto_merge_threshold:  Similarity ≥ this → automatically merge.
        review_threshold:      Similarity ≥ this (but < auto) → flag for review.

    Returns:
        ResolutionResult with canonical entities, relationships, and review items.
    """
    # ── Step 1: Count mentions per (name, type) ───────────────────────────────
    # mention_counts[(name, type)] = count
    mention_counts: dict[tuple[str, EntityType], int] = defaultdict(int)
    # mention_data[(name, type)] = list of EntityMention objects
    mention_data: dict[tuple[str, EntityType], list[EntityMention]] = defaultdict(list)

    for em in entity_mentions:
        key = (em.name, em.entity_type)
        mention_counts[key] += 1
        mention_data[key].append(em)

    # ── Step 2: Cluster by entity type ───────────────────────────────────────
    # Group unique names by entity type
    names_by_type: dict[EntityType, list[str]] = defaultdict(list)
    for (name, etype) in mention_counts:
        names_by_type[etype].append(name)

    # For each type, cluster similar names
    resolved_entities: list[ResolvedEntity] = []
    review_items: list[ReviewItem] = []
    # name_to_canonical[(name, type)] = canonical_id
    name_to_canonical: dict[tuple[str, EntityType], str] = {}
    merge_count = 0
    timestamp = datetime.now(timezone.utc).isoformat()

    for etype, unique_names in names_by_type.items():
        clustering: ClusteringResult = cluster_names(
            unique_names,
            auto_merge_threshold=auto_merge_threshold,
            review_threshold=review_threshold,
        )

        # Collect review pairs for this entity type
        for pair in clustering.review_pairs:
            review_items.append(ReviewItem(
                name_a=pair.name_a,
                name_b=pair.name_b,
                entity_type=etype,
                similarity=round(pair.score, 4),
                normalized_a=pair.norm_a,
                normalized_b=pair.norm_b,
            ))

        # Process each cluster
        for cluster_names_list in clustering.clusters:
            if len(cluster_names_list) > 1:
                merge_count += len(cluster_names_list) - 1

            # Pick canonical name: most-mentioned, then longest, then alphabetic
            sorted_names = sorted(
                cluster_names_list,
                key=lambda n: canonical_sort_key(n, mention_counts.get((n, etype), 0)),
            )
            canonical_name = sorted_names[0]
            aliases = [n for n in sorted_names if n != canonical_name]
            canonical_id = make_entity_id(etype, canonical_name)

            # Register all names in this cluster → canonical_id
            for name in cluster_names_list:
                name_to_canonical[(name, etype)] = canonical_id

            # Aggregate all mentions for this cluster
            all_cluster_mentions: list[EntityMention] = []
            for name in cluster_names_list:
                all_cluster_mentions.extend(mention_data.get((name, etype), []))

            chunk_ids = list(dict.fromkeys(m.chunk_id for m in all_cluster_mentions))
            source_files = list(dict.fromkeys(m.source_file for m in all_cluster_mentions))
            avg_confidence = (
                sum(m.confidence for m in all_cluster_mentions) / len(all_cluster_mentions)
                if all_cluster_mentions else 0.0
            )
            # Best description: first non-None description
            description = next(
                (m.description for m in all_cluster_mentions if m.description),
                None,
            )

            resolved_entities.append(ResolvedEntity(
                canonical_id=canonical_id,
                canonical_name=canonical_name,
                entity_type=etype,
                aliases=aliases,
                chunk_ids=chunk_ids,
                source_files=source_files,
                mention_count=len(all_cluster_mentions),
                avg_confidence=round(avg_confidence, 4),
                description=description,
                resolved_at=timestamp,
            ))

            logger.debug(
                "Resolved cluster [%s]: canonical='%s' aliases=%s",
                etype.value, canonical_name, aliases,
            )

    # Sort entities by type then canonical name for deterministic output
    resolved_entities.sort(key=lambda e: (e.entity_type.value, e.canonical_name))

    # ── Step 3: Remap relationships to canonical IDs ──────────────────────────
    # rel_key → list of RelationshipMention
    rel_groups: dict[tuple[str, RelationshipType, str], list[RelationshipMention]] = defaultdict(list)
    unmapped = 0

    for rm in relationship_mentions:
        src_canonical_id = name_to_canonical.get((rm.source_name, rm.source_type))
        tgt_canonical_id = name_to_canonical.get((rm.target_name, rm.target_type))

        if src_canonical_id is None:
            logger.warning(
                "Relationship source '%s' (%s) not in entity index — skipping.",
                rm.source_name, rm.source_type.value,
            )
            unmapped += 1
            continue
        if tgt_canonical_id is None:
            logger.warning(
                "Relationship target '%s' (%s) not in entity index — skipping.",
                rm.target_name, rm.target_type.value,
            )
            unmapped += 1
            continue

        # Skip self-loops
        if src_canonical_id == tgt_canonical_id:
            continue

        rel_key = (src_canonical_id, rm.relationship_type, tgt_canonical_id)
        rel_groups[rel_key].append(rm)

    # ── Step 4: Deduplicate relationships ─────────────────────────────────────
    resolved_relationships: list[ResolvedRelationship] = []
    entity_id_to_entity = {e.canonical_id: e for e in resolved_entities}

    for (src_id, rel_type, tgt_id), mentions in rel_groups.items():
        src_entity = entity_id_to_entity.get(src_id)
        tgt_entity = entity_id_to_entity.get(tgt_id)
        if not src_entity or not tgt_entity:
            continue

        chunk_ids = list(dict.fromkeys(m.chunk_id for m in mentions))
        source_files = list(dict.fromkeys(m.source_file for m in mentions))
        avg_conf = sum(m.confidence for m in mentions) / len(mentions)
        supporting_texts = [m.supporting_text for m in mentions if m.supporting_text]

        resolved_relationships.append(ResolvedRelationship(
            rel_id=make_relationship_id(src_id, rel_type, tgt_id),
            source_id=src_id,
            source_name=src_entity.canonical_name,
            source_type=src_entity.entity_type,
            relationship_type=rel_type,
            target_id=tgt_id,
            target_name=tgt_entity.canonical_name,
            target_type=tgt_entity.entity_type,
            chunk_ids=chunk_ids,
            source_files=source_files,
            mention_count=len(mentions),
            avg_confidence=round(avg_conf, 4),
            supporting_texts=supporting_texts,
        ))

    resolved_relationships.sort(
        key=lambda r: (r.source_name, r.relationship_type.value, r.target_name)
    )

    if unmapped:
        logger.warning(
            "%d relationship mention(s) could not be mapped to canonical entities.",
            unmapped,
        )

    unique_names_before = len(mention_counts)
    unique_entities_after = len(resolved_entities)

    logger.info(
        "Resolution complete: %d names → %d entities (%d merged), %d relationships, %d for review",
        unique_names_before, unique_entities_after, merge_count,
        len(resolved_relationships), len(review_items),
    )

    return ResolutionResult(
        entities=resolved_entities,
        relationships=resolved_relationships,
        review_items=review_items,
        raw_entity_mentions=len(entity_mentions),
        raw_relationship_mentions=len(relationship_mentions),
        unique_names_before=unique_names_before,
        unique_entities_after=unique_entities_after,
        merge_count=merge_count,
        review_count=len(review_items),
    )
