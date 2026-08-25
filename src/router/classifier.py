"""
Rule-based question router.

RULE PRIORITY (highest to lowest):

  R1  Multi-hop pattern + entities detected
      → GRAPH (highest confidence: clear structural question)

  R2  Multi-hop pattern but NO entities detected
      → HYBRID (graph might still help via keyword seed; vector as fallback)

  R3  Person query ("who") + relational verb
      → GRAPH 1-hop (typical: "who leads X?", "who manages Y?")

  R4  Relational verb + entity detected (no multi-hop)
      → GRAPH 1-hop ("what does Platform Team maintain?")

  R5  Definition pattern ("what is X?")
      → VECTOR (semantic similarity wins; no relationship traversal needed)

  R6  Temporal pattern ("when did X acquire Y?")
      → VECTOR (fact retrieval; the date is in one chunk)

  R7  Multiple entities (≥3) detected, no clear hop pattern
      → HYBRID (answer may span multiple documents and relationships)

  R8  Acquisition language + entities
      → GRAPH 2-hop (acquisition questions typically need two traversals:
        acquirer → acquired company → technology)

  R9  Single entity detected, no relational signal
      → VECTOR (straightforward entity lookup)

  R10 Default fallback
      → HYBRID (safe: run both retrievers, use whichever scores better)

WHY RULES OVER ML:

  An ML classifier would need labelled training data and would be opaque.
  These rules encode exactly what the Phase 6 evaluation showed:
    - Vector wins on simple_entity + factual (F1 ~0.65)
    - Graph wins on one_hop + two_hop + three_hop (F1 ~0.80+)
  Rules are auditable, fast, and easy to tune as evaluation data grows.

CONFIDENCE SCORES:

  Confidence reflects how clear the signal is, not the expected retrieval
  quality. High-confidence decisions are logged at DEBUG; low-confidence
  decisions (< 0.6) are logged at WARNING for monitoring.
"""

import logging

from src.router.models import RouteFeatures, RoutingDecision

logger = logging.getLogger(__name__)


def route(features: RouteFeatures) -> RoutingDecision:
    """
    Apply routing rules in priority order and return a RoutingDecision.

    This function is pure — no I/O, no side effects.
    It only reads from `features` and returns a decision.
    """
    entities = features.detected_entities
    has_entities = bool(entities)

    # ── R1: Multi-hop + entities ───────────────────────────────────────────
    if features.has_multi_hop_pattern and has_entities:
        hop = max(features.hop_depth, 2)
        return RoutingDecision(
            strategy="graph",
            detected_entities=entities,
            hop_depth=min(hop, 3),
            reason="multi-hop relative clause + known entities → graph traversal",
            confidence=0.90,
            features=features,
        )

    # ── R2: Multi-hop but no entities detected ─────────────────────────────
    if features.has_multi_hop_pattern and not has_entities:
        return RoutingDecision(
            strategy="hybrid",
            detected_entities=[],
            hop_depth=features.hop_depth,
            reason="multi-hop pattern without entity match → hybrid fallback",
            confidence=0.65,
            features=features,
        )

    # ── R3: Person query + relational verb ────────────────────────────────
    if features.is_person_query and features.has_relational_pattern:
        hop = max(features.hop_depth, 1)
        return RoutingDecision(
            strategy="graph",
            detected_entities=entities,
            hop_depth=hop,
            reason=(
                f"'who' + relational verb "
                f"({', '.join(features.relational_verbs_found[:2])}) → graph 1-hop"
            ),
            confidence=0.85,
            features=features,
        )

    # ── R4: Relational verb + entity ──────────────────────────────────────
    # Skip temporal questions ("When did X acquire Y?") — fact lookups where
    # the answer is a date in a single chunk; vector retrieval wins over graph.
    # Also skip definition questions ("What is X and how does it work?") — the
    # relational verb is incidental to the explanation intent.
    # And skip multi-entity (≥3) questions — let R7 route those to hybrid.
    if (
        features.has_relational_pattern
        and has_entities
        and not features.is_temporal
        and not features.is_definition
        and features.entity_count < 3
    ):
        return RoutingDecision(
            strategy="graph",
            detected_entities=entities,
            hop_depth=max(features.hop_depth, 1),
            reason=(
                f"relational verb ({', '.join(features.relational_verbs_found[:2])}) "
                f"+ entity '{entities[0]}' → graph 1-hop"
            ),
            confidence=0.80,
            features=features,
        )

    # ── R5: Definition pattern ─────────────────────────────────────────────
    if features.is_definition:
        return RoutingDecision(
            strategy="vector",
            detected_entities=entities,
            hop_depth=0,
            reason="definition pattern ('what is X') → semantic similarity",
            confidence=0.88,
            features=features,
        )

    # ── R6: Temporal / factual ─────────────────────────────────────────────
    if features.is_temporal:
        return RoutingDecision(
            strategy="vector",
            detected_entities=entities,
            hop_depth=0,
            reason="temporal question ('when did/was') → fact retrieval via vector",
            confidence=0.85,
            features=features,
        )

    # ── R7: Many entities, no clear structure ─────────────────────────────
    if features.entity_count >= 3:
        return RoutingDecision(
            strategy="hybrid",
            detected_entities=entities,
            hop_depth=1,
            reason=f"{features.entity_count} entities detected → hybrid for coverage",
            confidence=0.70,
            features=features,
        )

    # ── R8: Acquisition language + entities ───────────────────────────────
    if features.has_acquisition_language and has_entities:
        return RoutingDecision(
            strategy="graph",
            detected_entities=entities,
            hop_depth=2,
            reason="acquisition language + entities → graph 2-hop",
            confidence=0.78,
            features=features,
        )

    # ── R9: Single entity, no relational signal ───────────────────────────
    if features.entity_count == 1 and not features.has_relational_pattern:
        return RoutingDecision(
            strategy="vector",
            detected_entities=entities,
            hop_depth=0,
            reason=f"single entity '{entities[0]}', no relational signal → vector",
            confidence=0.75,
            features=features,
        )

    # ── R10: Default fallback ──────────────────────────────────────────────
    return RoutingDecision(
        strategy="hybrid",
        detected_entities=entities,
        hop_depth=max(features.hop_depth, 1),
        reason="no dominant signal → hybrid (safe default)",
        confidence=0.55,
        features=features,
    )
