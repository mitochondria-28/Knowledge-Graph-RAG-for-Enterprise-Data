"""
Gemini API wrapper for entity & relationship extraction.

KEY DESIGN DECISIONS:

1. Function calling (not raw JSON prompting).
   We force Gemini to call our extraction function via mode="ANY". This
   guarantees structured JSON output matching our schema — no markdown code
   fences, no prose wrapping, no "Here is the extraction:" preamble.

2. Retry with corrective feedback.
   On validation failure we send the error list back in the retry message.
   Telling the model what went wrong ("relationship references entity
   'Stellar Systems' which is not in your entities list") gets significantly
   better correction than a blind retry.

3. Separate concerns.
   This module ONLY handles the API call and retry loop. Validation logic
   lives in validator.py. Caching lives in cache.py. This makes each piece
   independently testable.

4. Token tracking.
   Every API response includes usage metadata. We capture prompt_token_count
   and candidates_token_count for cost estimation and the benchmark report.
"""

import logging
import time
from datetime import datetime, timezone

from google import genai
from google.genai import types
from google.api_core import exceptions as gexceptions
from pydantic import ValidationError

from src.extraction.prompts import EXTRACTION_TOOL, SYSTEM_PROMPT
from src.extraction.schemas import (
    ChunkExtractionResult,
    ExtractionRecord,
)
from src.extraction.validator import ValidationResult, deduplicate_entities, validate_extraction

logger = logging.getLogger(__name__)

# Gemini model used for extraction.
# gemini-2.5-flash: fast, free tier — appropriate for well-defined extraction tasks.
# Switch to gemini-2.5-pro if extraction quality is insufficient.
DEFAULT_MODEL = "gemini-2.5-flash"

# Pricing as of 2026 (USD per million tokens) — gemini-2.5-flash has a free tier
_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash":      {"input": 0.0,  "output": 0.0},
    "gemini-2.5-flash-lite": {"input": 0.0,  "output": 0.0},
    "gemini-2.5-pro":        {"input": 1.25, "output": 10.00},
}

MAX_RETRIES = 3
_RETRY_DELAYS_SECONDS = [1, 2, 4]


class ExtractionError(Exception):
    """Raised when a chunk cannot be extracted after all retries."""


def make_extractor_client(api_key: str, model: str = DEFAULT_MODEL):
    """
    Factory: create a configured Gemini Client for extraction.

    Returns a genai.Client; the model name is stored separately and passed
    per-call to allow the same client to be reused across model variants.
    """
    return genai.Client(api_key=api_key)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Return estimated USD cost for a single API call."""
    pricing = _PRICING.get(model, {"input": 3.50, "output": 10.50})
    return (input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"])


def _build_extraction_tool() -> types.Tool:
    """Convert the EXTRACTION_TOOL dict (Gemini parameters format) into a types.Tool."""
    params_dict = EXTRACTION_TOOL["parameters"]

    def _dict_to_schema(d: dict) -> types.Schema:
        kwargs: dict = {}
        if "type" in d:
            kwargs["type"] = d["type"]
        if "description" in d:
            kwargs["description"] = d["description"]
        if "properties" in d:
            kwargs["properties"] = {k: _dict_to_schema(v) for k, v in d["properties"].items()}
        if "items" in d:
            kwargs["items"] = _dict_to_schema(d["items"])
        if "required" in d:
            kwargs["required"] = d["required"]
        if "enum" in d:
            kwargs["enum"] = [str(e) for e in d["enum"]]
        if "minimum" in d:
            kwargs["minimum"] = d["minimum"]
        if "maximum" in d:
            kwargs["maximum"] = d["maximum"]
        return types.Schema(**kwargs)

    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=EXTRACTION_TOOL["name"],
            description=EXTRACTION_TOOL["description"],
            parameters=_dict_to_schema(params_dict),
        )
    ])


# Build once at import time
_EXTRACTION_GEMINI_TOOL = _build_extraction_tool()

_EXTRACTION_TOOL_CONFIG = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(
        mode="any",
        allowed_function_names=["extract_entities_and_relationships"],
    )
)


def extract_chunk(
    chunk_id: str,
    document_id: str,
    source_file: str,
    doc_hash: str,
    section: str,
    content: str,
    client,
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
            response = client.models.generate_content(
                model=model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[_EXTRACTION_GEMINI_TOOL],
                    tool_config=_EXTRACTION_TOOL_CONFIG,
                    max_output_tokens=2048,
                ),
            )
        except gexceptions.Unauthenticated:
            raise  # don't retry — the key is wrong
        except gexceptions.ResourceExhausted as exc:
            wait = _RETRY_DELAYS_SECONDS[attempt - 1] * 10
            logger.warning("Rate limit on attempt %d/%d. Waiting %ds.", attempt, MAX_RETRIES, wait)
            time.sleep(wait)
            continue
        except gexceptions.GoogleAPIError as exc:
            logger.warning("API error on attempt %d/%d: %s", attempt, MAX_RETRIES, exc)
            time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])
            continue

        # Track token usage across all attempts
        total_input_tokens += response.usage_metadata.prompt_token_count
        total_output_tokens += response.usage_metadata.candidates_token_count

        # Extract function call result from response
        tool_result = _parse_tool_response(response)
        if tool_result is None:
            last_error = "No function call found in response."
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
            response.usage_metadata.prompt_token_count,
            response.usage_metadata.candidates_token_count,
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


def _parse_tool_response(response) -> dict | None:
    """Extract the function call input dict from a Gemini response."""
    for part in response.parts:
        fc = getattr(part, "function_call", None)
        if fc and fc.name == "extract_entities_and_relationships":
            return dict(fc.args)
    return None
