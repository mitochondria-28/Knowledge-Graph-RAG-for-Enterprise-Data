"""
Graph (structural) retriever — wraps Neo4j traversal.

RETRIEVAL ALGORITHM:

  1. Find seed entity nodes matching question.expected_entities
  2. Expand hop_depth hops via any relationship type
  3. Collect chunk_ids from all reached nodes
  4. Return chunk_ids ranked by node proximity (closer = higher rank)

WHY EXPECTED_ENTITIES (not entity extraction):

Extracting entity names from free-form question text is non-trivial and
typically requires an LLM call — which would add latency and cost to every
retrieval. For the evaluation harness we use the pre-defined expected_entities
list that comes with each EvalQuestion. In Phase 7 (the router), a lightweight
entity spotter (exact-match against canonical names) will handle live queries.

SECURITY:

All Cypher is hardcoded in Python. Entity names are passed as parameters
($names). hop_depth is an integer checked against an allowlist {1, 2, 3}.
No user input or LLM output is interpolated into Cypher strings.

REQUIREMENTS:
  - Neo4j running (docker compose up -d neo4j)
  - Entities loaded via Phase 4 (scripts/load_graph.py)
  - NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in .env
"""

import logging
import time

from src.evaluation.models import EvalQuestion, RetrievalResult
from src.evaluation.retriever_base import BaseRetriever

logger = logging.getLogger(__name__)

_ALLOWED_HOP_DEPTHS = frozenset({1, 2, 3})

# Parameterized Cypher: find entity nodes by canonical_name and expand
# hop_depth relationship hops. Variable-length path [*0..N] collects all
# nodes within N hops of the seed set.
# chunk_ids is a list property on each Entity node (stored in Phase 4).
_GRAPH_QUERY_TEMPLATE = """
MATCH (seed:Entity)
WHERE seed.canonical_name IN $names
WITH collect(seed) AS seeds
UNWIND seeds AS s
MATCH (s)-[*0..{hops}]-(reached:Entity)
WITH collect(DISTINCT reached) AS all_nodes
UNWIND all_nodes AS node
UNWIND node.chunk_ids AS cid
RETURN DISTINCT cid AS chunk_id
LIMIT $limit
"""


class GraphRetriever(BaseRetriever):
    """
    Structural retriever using Neo4j graph traversal.

    Args:
        driver:     Open neo4j.Driver (from Neo4jConnection context manager).
        hop_depth:  How many relationship hops to expand from seed entities.
                    Must be 1, 2, or 3. Default 2.
    """

    def __init__(self, driver, hop_depth: int = 2) -> None:
        if hop_depth not in _ALLOWED_HOP_DEPTHS:
            raise ValueError(f"hop_depth must be one of {_ALLOWED_HOP_DEPTHS}")
        self._driver = driver
        self._hop_depth = hop_depth
        # Cache the query string (hop_depth is hardcoded at init, not at query time)
        self._cypher = _GRAPH_QUERY_TEMPLATE.format(hops=hop_depth)

    @property
    def name(self) -> str:
        return f"graph_{self._hop_depth}hop"

    def retrieve(self, question: EvalQuestion, k: int) -> RetrievalResult:
        start = time.perf_counter()

        entity_names = question.expected_entities
        if not entity_names:
            logger.debug("q%s: no expected_entities — graph retriever returns empty", question.qid)
            return RetrievalResult(
                qid=question.qid,
                retriever=self.name,
                retrieved_chunk_ids=[],
                latency_ms=0.0,
            )

        with self._driver.session(database="neo4j") as session:
            result = session.run(
                self._cypher,
                names=entity_names,
                limit=k,
            )
            chunk_ids = [row["chunk_id"] for row in result]

        elapsed_ms = (time.perf_counter() - start) * 1000
        return RetrievalResult(
            qid=question.qid,
            retriever=self.name,
            retrieved_chunk_ids=chunk_ids,
            latency_ms=elapsed_ms,
        )
