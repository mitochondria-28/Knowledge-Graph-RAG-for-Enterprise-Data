"""
Feature extraction for the question router.

This module is purely functional — no side effects, no I/O.
Input: question string + entity index.
Output: RouteFeatures dataclass.

WHY RULE-BASED FEATURE EXTRACTION (not LLM-based):

LLM-based intent classification would add ~500ms + API cost to every
retrieval. Rule-based extraction runs in <1ms, is deterministic, and
is fully testable. The patterns here encode the same knowledge an LLM
would use — we just write it explicitly.

ENTITY DETECTION STRATEGY:

We match canonical entity names (and aliases) against the lowercased
question. This is exact substring matching — no fuzzy match — because:
  1. False positives (routing to graph when vector would be better) cost more
     than false negatives (routing to vector when graph would be better),
     because vector is always a useful fallback.
  2. The canonical name list is a closed set from our ontology.
  3. Fuzzy matching would require a threshold and create subtle bugs.

HOP DEPTH ESTIMATION:

We count "that"/"which" relative clauses that follow relational verbs.
Each such clause indicates one additional graph hop:

  "Who leads the Platform Team?"
   → no relative clause after relational verb → 1-hop

  "Who leads the team that maintains StellarDB?"
   → one "that" after "maintains" → 2-hop

  "Who leads the team responsible for technology acquired from Stellar Systems?"
   → "responsible for" + "acquired from" pattern → 2-hop

  "Who leads the team that manages technology developed by a company TechNova acquired?"
   → two chained dependency patterns → 3-hop
"""

import re
from src.router.models import RouteFeatures

# ── Relational verbs that signal graph traversal ───────────────────────────

_RELATIONAL_VERBS: frozenset[str] = frozenset({
    # Org-chart relationships
    "leads", "lead", "led", "manage", "manages", "managed",
    "reports", "report", "reported",
    # Ownership / responsibility
    "owns", "own", "owned", "responsible",
    "maintains", "maintain", "maintained",
    "develops", "develop", "developed",
    "created", "creates", "create",
    "built", "build", "builds",
    # Employment
    "works", "work", "worked", "joined",
    # Acquisition / partnership
    "acquired", "acquire", "acquires",
    "partnered", "partners", "partner",
    # Technical dependencies
    "uses", "use", "used", "depends", "depend",
})

# ── Patterns for hop depth estimation ─────────────────────────────────────

# Pre-compile as a single pattern that matches any hop signal
_ANY_HOP = re.compile(
    r"\b(?:the\s+)?(?:\w+\s+){0,4}(?:that|which)\s+"
    r"(?:is\s+|are\s+|was\s+|were\s+)?"
    r"(?:leads?|manages?|maintains?|develops?|uses?|owns?|works?\s+for|acquired?|built?|created?|responsible)\b"
    r"|"
    r"\b(?:acquired?|developed?|maintained?|created?|built?|responsible)\s+(?:from|by|for)\b",
    re.IGNORECASE,
)

# ── Definition patterns ────────────────────────────────────────────────────

_DEFINITION_PATTERNS: list[re.Pattern] = [
    re.compile(r"^what\s+is\s+", re.IGNORECASE),
    re.compile(r"^what\s+are\s+", re.IGNORECASE),
    re.compile(r"^what\s+does\s+\w+\s+do\b", re.IGNORECASE),
    re.compile(r"^what\s+(?:is\s+the\s+)?(?:purpose|role|function)\s+of\b", re.IGNORECASE),
    re.compile(r"\bhow\s+does\s+\w+\s+work\b", re.IGNORECASE),
]

# ── Temporal patterns ──────────────────────────────────────────────────────

_TEMPORAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^when\s+(?:did|was|were|has|have)\b", re.IGNORECASE),
    re.compile(r"\b(?:date|year|month|founded|established|started|launched|completed)\b", re.IGNORECASE),
]

# ── Acquisition-specific language ──────────────────────────────────────────

_ACQUISITION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:acquired?|acquisitions?|merger|purchase|deal|bought)\b", re.IGNORECASE),
]


# ── Public API ─────────────────────────────────────────────────────────────

def extract_features(
    question: str,
    entity_index: dict[str, str],
) -> RouteFeatures:
    """
    Extract routing features from a question string.

    Args:
        question:     The natural-language question.
        entity_index: {canonical_name: entity_type} loaded from resolved_entities.json.
                      Also checked against aliases if the caller pre-expands them.

    Returns:
        RouteFeatures with all signals populated.
    """
    q_lower = question.lower().strip()
    tokens = q_lower.split()
    question_word = tokens[0].rstrip("?") if tokens else ""

    # ── Entity detection ───────────────────────────────────────────────────
    detected = [name for name in entity_index if name.lower() in q_lower]
    # Deduplicate: remove shorter names that are substrings of longer ones
    detected = _deduplicate_entities(detected)

    # ── Linguistic signals ─────────────────────────────────────────────────
    is_definition = any(p.search(question) for p in _DEFINITION_PATTERNS)
    is_temporal   = any(p.search(question) for p in _TEMPORAL_PATTERNS)
    is_person     = question_word == "who"

    # ── Relational verbs found ─────────────────────────────────────────────
    rel_verbs = [t.rstrip(".,?!") for t in tokens if t.rstrip(".,?!") in _RELATIONAL_VERBS]

    # ── Hop depth via relative-clause + acquisition patterns ───────────────
    hop_matches = _ANY_HOP.findall(question)
    relative_clause_count = len(hop_matches)

    # Also count standalone "that" / "which" following a relational verb
    # as a conservative additional signal
    that_count = len(re.findall(r"\bthat\b", q_lower))

    # Hop depth: start at 0; each structural signal adds 1
    hop_depth = 0
    if rel_verbs:
        hop_depth = 1            # at least one relational hop
    hop_depth += relative_clause_count
    # Cap at 3 (our max supported traversal depth)
    hop_depth = min(hop_depth, 3)

    # ── Composite signals ──────────────────────────────────────────────────
    has_relational  = bool(rel_verbs)
    has_multi_hop   = relative_clause_count >= 1 or (that_count >= 1 and hop_depth >= 2)
    has_acquisition = any(p.search(question) for p in _ACQUISITION_PATTERNS)

    return RouteFeatures(
        detected_entities=detected,
        entity_count=len(detected),
        question_word=question_word,
        is_definition=is_definition,
        is_temporal=is_temporal,
        is_person_query=is_person,
        relational_verbs_found=rel_verbs,
        relative_clause_count=relative_clause_count,
        hop_depth=hop_depth,
        has_relational_pattern=has_relational,
        has_multi_hop_pattern=has_multi_hop,
        has_acquisition_language=has_acquisition,
    )


def _deduplicate_entities(names: list[str]) -> list[str]:
    """
    Remove shorter entity names that are substrings of longer ones.
    Prevents "Stellar" matching when "Stellar Systems" is also present.
    """
    sorted_names = sorted(names, key=len, reverse=True)
    kept: list[str] = []
    for name in sorted_names:
        if not any(name.lower() in kept_name.lower() for kept_name in kept):
            kept.append(name)
    return kept


def build_entity_index(resolved_entities: list[dict]) -> dict[str, str]:
    """
    Build {canonical_name: entity_type} index for entity detection.
    Also includes aliases so variant names in questions are detected.

    Args:
        resolved_entities: list of ResolvedEntity dicts from resolved_entities.json.

    Returns:
        {name_or_alias: entity_type}
    """
    index: dict[str, str] = {}
    for entity in resolved_entities:
        etype = entity["entity_type"]
        index[entity["canonical_name"]] = etype
        for alias in entity.get("aliases", []):
            index[alias] = etype
    return index
