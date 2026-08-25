"""
Similarity computation and clustering for entity resolution.

WHY RAPIDFUZZ OVER PLAIN DIFFLIB:

Python's built-in `difflib.SequenceMatcher` computes simple edit-distance
similarity. It's accurate but misses important cases:

  "Stellar Systems" vs "Systems Stellar"  → difflib: 0.78 (bad)
                                          → token_sort_ratio: 1.00 (correct)

  "TechNova" vs "TechNova Corporation"    → difflib: 0.64 (too low)
                                          → token_set_ratio: 1.00 (correct)

rapidfuzz provides three metrics, each optimal for different name variation types:

  ratio            — character edit distance. Good for typos.
  token_sort_ratio — tokenize, sort, then compare. Handles word order variations.
  token_set_ratio  — compares the intersection vs the full sets. Handles subset
                     relationships (short name vs long name).

We take the MAX of all three so that any of these patterns triggers a match.

WHY UNION-FIND FOR CLUSTERING:

Given pairs A≈B and B≈C, we want {A, B, C} in one cluster even if A and C
were never directly compared (transitive merging). Union-Find (Disjoint Set
Union) handles this in nearly O(n) time with path compression.

Note: single-linkage clustering (which Union-Find implements) can produce
"chaining" where unrelated entities end up in the same cluster if they happen
to both be similar to a third entity. We mitigate this by using a high
auto-merge threshold (0.95) so only genuine matches are merged automatically.
Anything in 0.82–0.95 goes to the review queue.

EMBEDDING SIMILARITY NOTE:

String similarity works well when name variants share most tokens:
  "TechNova Corporation" and "TechNova Corp" share "TechNova" → high similarity.

It fails when names are conceptually identical but textually different:
  "Big Blue" and "IBM" → 0% token overlap → would not be merged.

For the TechNova corpus, all entities are referred to by consistent base names
so string similarity is sufficient. In a production system with cross-language
or acronym-heavy corpora, you would augment with embedding cosine similarity
(embed entity names + context, cluster by cosine similarity > threshold).
This will be introduced in Phase 5 as an enhancement.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from src.resolution.normalizer import normalize_for_comparison


@dataclass
class SimilarityPair:
    name_a: str
    name_b: str
    norm_a: str   # normalized form used for comparison
    norm_b: str
    score: float  # max of ratio, token_sort_ratio, token_set_ratio


def compute_similarity(name_a: str, name_b: str) -> SimilarityPair:
    """
    Compute multi-metric string similarity between two entity names.
    Returns the maximum score across three rapidfuzz metrics.
    """
    norm_a = normalize_for_comparison(name_a)
    norm_b = normalize_for_comparison(name_b)

    # Short-circuit: normalized forms are identical → perfect match
    if norm_a == norm_b:
        return SimilarityPair(name_a, name_b, norm_a, norm_b, 1.0)

    # Three complementary metrics
    scores = [
        fuzz.ratio(norm_a, norm_b) / 100,              # typos, minor edits
        fuzz.token_sort_ratio(norm_a, norm_b) / 100,   # word order variations
        fuzz.token_set_ratio(norm_a, norm_b) / 100,    # subset relationships
    ]
    return SimilarityPair(name_a, name_b, norm_a, norm_b, max(scores))


# ── Union-Find ────────────────────────────────────────────────────────────────

class UnionFind:
    """
    Disjoint Set Union with path compression and union-by-rank.
    Maps string keys (entity names) to cluster roots.
    """

    def __init__(self, elements: list[str]) -> None:
        self._parent: dict[str, str] = {e: e for e in elements}
        self._rank: dict[str, int] = {e: 0 for e in elements}

    def find(self, x: str) -> str:
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])  # path compression
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Union by rank
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def clusters(self) -> dict[str, list[str]]:
        """Return {root: [members]} for all clusters."""
        groups: dict[str, list[str]] = defaultdict(list)
        for element in self._parent:
            groups[self.find(element)].append(element)
        return dict(groups)


# ── Main clustering function ──────────────────────────────────────────────────

@dataclass
class ClusteringResult:
    clusters: list[list[str]]                  # groups of equivalent names
    review_pairs: list[SimilarityPair]         # pairs for human review
    all_pairs: list[SimilarityPair] = field(default_factory=list)  # for debugging


def cluster_names(
    names: list[str],
    auto_merge_threshold: float = 0.95,
    review_threshold: float = 0.82,
) -> ClusteringResult:
    """
    Cluster a list of entity names by string similarity.

    Names with similarity >= auto_merge_threshold are automatically merged
    into the same cluster. Pairs in [review_threshold, auto_merge_threshold)
    are returned as review_pairs for human inspection.

    Args:
        names:                  Unique entity names (all of the same entity type).
        auto_merge_threshold:   Minimum similarity to auto-merge two names.
        review_threshold:       Minimum similarity to flag a pair for review.

    Returns:
        ClusteringResult with clusters and review pairs.
    """
    if len(names) <= 1:
        return ClusteringResult(clusters=[[n] for n in names], review_pairs=[])

    uf = UnionFind(names)
    review_pairs: list[SimilarityPair] = []
    all_pairs: list[SimilarityPair] = []

    # Compute all pairwise similarities — O(n²) but n is small (< 200 entity names)
    for i, name_a in enumerate(names):
        for name_b in names[i + 1:]:
            pair = compute_similarity(name_a, name_b)
            all_pairs.append(pair)

            if pair.score >= auto_merge_threshold:
                uf.union(name_a, name_b)
            elif pair.score >= review_threshold:
                review_pairs.append(pair)

    clusters = list(uf.clusters().values())
    return ClusteringResult(
        clusters=clusters,
        review_pairs=review_pairs,
        all_pairs=all_pairs,
    )
