"""
Data models for the question router.

RoutingDecision carries everything downstream retrieval needs:
  - which strategy to run (vector / graph / hybrid)
  - which entities to use as graph seeds
  - why the decision was made (for logging and debugging)
  - estimated hop depth for graph traversal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Strategy = Literal["vector", "graph", "hybrid"]


@dataclass
class RouteFeatures:
    """
    Signals extracted from question text that drive the routing decision.
    Kept separate from RoutingDecision so each rule can inspect raw features.
    """
    # ── Entity signals ─────────────────────────────────────────────────────
    detected_entities: list[str] = field(default_factory=list)   # canonical names
    entity_count: int = 0

    # ── Linguistic signals ─────────────────────────────────────────────────
    question_word: str = ""          # "what", "who", "when", "how", "which"
    is_definition: bool = False      # "what is X" / "what does X do"
    is_temporal: bool = False        # "when did/was/were"
    is_person_query: bool = False    # question starts with "who"

    # ── Structural signals ─────────────────────────────────────────────────
    relational_verbs_found: list[str] = field(default_factory=list)
    relative_clause_count: int = 0   # number of "that"/"which" clauses
    hop_depth: int = 0               # estimated traversal depth

    # ── Composite signals ──────────────────────────────────────────────────
    has_relational_pattern: bool = False
    has_multi_hop_pattern: bool = False
    has_acquisition_language: bool = False


@dataclass
class RoutingDecision:
    """
    The router's output: what to retrieve and why.

    strategy:          Which retriever(s) to invoke.
    detected_entities: Canonical entity names to seed graph traversal.
    hop_depth:         Graph traversal depth (1–3). Ignored for vector.
    reason:            Human-readable explanation (for logs and the --explain flag).
    confidence:        0.0–1.0. High = clear signal. Low = ambiguous → hybrid fallback.
    features:          The raw RouteFeatures (for debugging and testing).
    """
    strategy: Strategy
    detected_entities: list[str] = field(default_factory=list)
    hop_depth: int = 2
    reason: str = ""
    confidence: float = 1.0
    features: RouteFeatures | None = None

    def __str__(self) -> str:
        entity_str = f"  entities={self.detected_entities}" if self.detected_entities else ""
        hop_str = f"  hops={self.hop_depth}" if self.strategy == "graph" else ""
        return (
            f"strategy={self.strategy!r}"
            f"{hop_str}"
            f"  confidence={self.confidence:.2f}"
            f"{entity_str}"
            f"  reason={self.reason!r}"
        )
