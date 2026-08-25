"""
Claude API wrapper for entity & relationship extraction.

KEY DESIGN DECISIONS:

1. Tool use (not raw JSON prompting).
   We force Claude to call our extraction tool via tool_choice="tool". This
   guarantees structured JSON output matching our schema — no markdown code
   fences, no prose wrapping, no "Here is the extraction:" preamble.

2. Retry with corrective feedback.
   On validation failure we send the error list back to Claude in the retry
   message. Telling Claude what went wrong ("relationship references entity
   'Stellar Systems' which is not in your entities list") gets significantly
   better correction than a blind retry.

3. Separate concerns.
   This module ONLY handles the API call and retry loop. Validation logic
   lives in validator.py. Caching lives in cache.py. This makes each piece
   independently testable.

4. Token tracking.
   Every API response includes usage metadata. We capture input_tokens and
   output_tokens for cost estimation and the benchmark report in Phase 12.
"""

import logging
import time
from datetime import datetime, timezone

import anthropic
from pydantic import ValidationError

from src.extraction.prompts import EXTRACTION_TOOL, SYSTEM_PROMPT
from src.extraction.schemas import (
    ChunkExtractionResult,
    ExtractionRecord,
)
from src.extraction.validator import ValidationResult, deduplicate_entities, validate_extraction

logger = logging.getLogger(__name__)

# Claude model used for extraction.
# claude-haiku-4-5-20251001: fast and cheap — appropriate for well-defined extraction tasks.
# Switch to claude-sonnet-4-6 if extraction quality is insufficient.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Pricing as of mid-2025 (USD per million tokens)
_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00},
}

MAX_RETRIES = 3
_RETRY_DELAYS_SECONDS = [1, 2, 4]


class ExtractionError(Exception):
    """Raised when a chunk cannot be extracted after all retries."""


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Return estimated USD cost for a single API call."""
    pricing = _PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"])


def extract_chunk(
    chunk_id: str,
    document_id: str,
    source_file: str,
    doc_hash: str,
    section: str,
    content: str,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
) -> ExtractionRecord:
    """
    Extract entities and relationships from a single chunk.

    Raises ExtractionError if all retries are exhausted.
    """
    total_input_tokens = 0
    total_output_tokens = 0
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        # Build the user message. On retries, include the previous error.
        user_content = _build_user_message(content, last_error, attempt)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_entities_and_relationships"},
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.AuthenticationError:
            raise  # don't retry — the key is wrong
        except anthropic.RateLimitError as exc:
            wait = _RETRY_DELAYS_SECONDS[attempt - 1] * 10
            logger.warning("Rate limit on attempt %d/%d. Waiting %ds.", attempt, MAX_RETRIES, wait)
            time.sleep(wait)
            continue
        except anthropic.APIError as exc:
            logger.warning("API error on attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
            continue

        # Track token usage across all attempts
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Extract tool call result from response
        tool_result = _parse_tool_response(response)
        if tool_result is None:
            last_error = "No tool call found in response."
            logger.warning("[%s] Attempt %d: %s", chunk_id[:8], attempt, last_error)
            time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
            continue

        # Parse into Pydantic model (catches enum violations, confidence range, etc.)
        try:
            extraction = ChunkExtractionResult.model_validate(tool_result)
        except ValidationError as exc:
            last_error = f"Schema validation failed: {exc.error_count()} error(s). {exc}"
            logger.warning("[%s] Attempt %d: %s", chunk_id[:8], attempt, last_error)
            time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
            continue

        # Deduplicate then validate cross-references
        extraction = deduplicate_entities(extraction)
        vr: ValidationResult = validate_extraction(extraction, chunk_id)

        if not vr.is_valid:
            last_error = "; ".join(vr.hard_errors)
            logger.warning(
                "[%s] Attempt %d: validation failed — %s",
                chunk_id[:8], attempt, last_error,
            )
            if attempt < MAX_RETRIES:
                time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
            continue

        # Success
        logger.info(
            "[%s] Extracted %d entities, %d relationships (attempt %d, %d+%d tokens)",
            chunk_id[:8],
            len(extraction.entities),
            len(extraction.relationships),
            attempt,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return ExtractionRecord(
            chunk_id=chunk_id,
            document_id=document_id,
            source_file=source_file,
            doc_hash=doc_hash,
            section=section,
            extraction=extraction,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            attempts=attempt,
            extracted_at=datetime.now(timezone.utc).isoformat(),
            model=model,
        )

    raise ExtractionError(
        f"Chunk {chunk_id[:8]} failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(content: str, last_error: str | None, attempt: int) -> str:
    if attempt == 1 or last_error is None:
        return f"Extract all entities and relationships from this document chunk:\n\n{content}"
    return (
        f"Your previous extraction had errors. Please fix them and try again.\n\n"
        f"ERRORS TO FIX:\n{last_error}\n\n"
        f"Remember: every entity referenced in a relationship MUST appear in the entities list.\n\n"
        f"Document chunk:\n\n{content}"
    )


def _parse_tool_response(response: anthropic.types.Message) -> dict | None:
    """Extract the tool input dict from a Claude response."""
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_entities_and_relationships":
            return block.input
    return None
