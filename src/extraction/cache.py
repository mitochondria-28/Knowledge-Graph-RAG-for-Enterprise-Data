"""
Chunk-level extraction cache backed by a JSON file.

WHY CACHE BY CHUNK_ID:

In Phase 1 we established that chunk_id = UUID5(doc_hash:chunk_index).
This means:
  - Same document, unchanged content → same chunk_ids → cache hits → no API calls
  - Document edited → doc_hash changes → new chunk_ids → cache misses → re-extracted

This design makes extraction cost-safe to re-run. You can add more corpus
documents and only the NEW chunks are sent to Claude. Existing chunks are served
from the JSON cache on disk.

We write to disk after EACH chunk (not just at the end) so that an interruption
mid-run (network error, keyboard interrupt) doesn't lose already-extracted chunks.
"""

import json
import logging
from pathlib import Path

from src.extraction.schemas import ExtractionRecord

logger = logging.getLogger(__name__)


class ExtractionCache:
    """
    Persistent extraction cache backed by output/extraction_cache.json.

    The cache maps chunk_id → ExtractionRecord dict.
    """

    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load extraction cache from %s: %s", self._path, exc)
            return {}

    def get(self, chunk_id: str) -> ExtractionRecord | None:
        raw = self._data.get(chunk_id)
        if raw is None:
            return None
        try:
            return ExtractionRecord.model_validate(raw)
        except Exception as exc:
            logger.warning("Cache entry for %s is corrupt, ignoring: %s", chunk_id[:8], exc)
            return None

    def put(self, record: ExtractionRecord) -> None:
        self._data[record.chunk_id] = record.to_dict()
        self._flush()

    def _flush(self) -> None:
        """Write the full cache to disk atomically (write temp, rename)."""
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def cached_ids(self) -> set[str]:
        return set(self._data.keys())
