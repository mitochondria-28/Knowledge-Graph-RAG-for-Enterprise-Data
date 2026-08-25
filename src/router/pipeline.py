"""
Router pipeline: loads entity index, routes questions, optionally compares
routing decisions against Phase 6 evaluation question types.

ENTITY INDEX:

Loaded from output/resolved_entities.json (Phase 3 output).
The index maps canonical_name + aliases → entity_type.
If the file is missing, routing still works but entity detection will find
nothing, pushing most questions toward vector/hybrid instead of graph.
"""

import json
import logging
from pathlib import Path

from src.config import settings
from src.router.classifier import route
from src.router.models import RoutingDecision
from src.router.signals import build_entity_index, extract_features

logger = logging.getLogger(__name__)


def load_entity_index(resolved_entities_file: Path | None = None) -> dict[str, str]:
    """
    Load the entity index from resolved_entities.json.
    Returns an empty dict if the file is missing (graceful degradation).
    """
    path = resolved_entities_file or (settings.output_dir / "resolved_entities.json")
    if not path.exists():
        logger.warning(
            "Entity index not found at %s — entity detection disabled. "
            "Run `python scripts/resolve.py` to generate it.",
            path,
        )
        return {}
    entities = json.loads(path.read_text(encoding="utf-8"))
    index = build_entity_index(entities)
    logger.debug("Loaded entity index: %d names/aliases from %d entities", len(index), len(entities))
    return index


class QuestionRouter:
    """
    Stateful router that holds the entity index and classifies questions.

    Usage:
        router = QuestionRouter()
        decision = router.route("Who leads the team that maintains StellarDB?")
        print(decision)
    """

    def __init__(self, entity_index: dict[str, str] | None = None) -> None:
        self._entity_index = entity_index if entity_index is not None else load_entity_index()

    @property
    def entity_count(self) -> int:
        return len(self._entity_index)

    def route(self, question: str) -> RoutingDecision:
        """
        Classify a question and return a RoutingDecision.

        Args:
            question: Natural-language question string.

        Returns:
            RoutingDecision with strategy, entities, hop_depth, reason.
        """
        features = extract_features(question, self._entity_index)
        decision = route(features)
        logger.debug("Route: %s", decision)
        return decision

    def route_batch(self, questions: list[str]) -> list[RoutingDecision]:
        """Route multiple questions. Each is independent."""
        return [self.route(q) for q in questions]
