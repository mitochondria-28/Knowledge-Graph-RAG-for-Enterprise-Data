"""
Answer generator — Phase 8.

WHY FUNCTION CALLING FOR ANSWER GENERATION:

Free-text LLM output is hard to parse reliably. If the LLM returns the answer
and citations as prose, we have to regex-parse chunk IDs and quotes — fragile
and untestable. Function calling forces the model to return a typed JSON object
that we can validate with a schema. It also makes citation extraction deterministic.

WHY mode="ANY" with allowed_function_names=["provide_answer"]:

Setting mode="ANY" forces Gemini to call exactly the named function. Without
this, the model might describe the answer in prose and skip the function call
when it feels confident. We always want the structured output.

CONTEXT FORMATTING:

Each chunk is presented with a clearly labelled header:

  [CHUNK abc123 | corpus/companies/technova_overview.md | section: Overview]
  <content>

The model is instructed to cite chunk_ids from these headers. The separator
between chunks is '---' so the model can visually distinguish boundaries.

SECURITY:

  - The model receives chunk content as read-only context; it cannot modify chunks
  - We never execute any code from the model's output
  - citation chunk_ids are validated downstream by CitationValidator
  - If the model invents a chunk_id, CitationValidator will flag it as invalid
"""

import logging
import time

from google import genai
from google.genai import types
from google.api_core import exceptions as gexceptions

from src.answer.models import Citation, RawAnswer

logger = logging.getLogger(__name__)

# ── Default model ─────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-2.5-flash"

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Your job is to answer questions using ONLY the context chunks provided below.

Rules you must follow:
1. Base every statement on information in the provided chunks — never use background knowledge
2. Cite EVERY factual claim using the chunk_id from the [CHUNK ...] header
3. The quote field must be a short, verbatim phrase (10–60 words) copied exactly from that chunk
4. If the context does not contain enough information to answer fully, say so explicitly
5. Use the provide_answer function to return your structured response — no free-text output

Context chunk format:
  [CHUNK {chunk_id} | {source_file} | section: {section}]
  {content}
  ---
"""

# ── Tool definition (Gemini FunctionDeclaration) ──────────────────────────────
_ANSWER_TOOL_DECL = types.FunctionDeclaration(
    name="provide_answer",
    description=(
        "Return a structured answer with citations from the retrieved context chunks. "
        "Every factual claim must have a matching citation."
    ),
    parameters=types.Schema(
        type="object",
        properties={
            "answer": types.Schema(
                type="string",
                description=(
                    "Complete answer to the question based only on the provided chunks. "
                    "Use plain prose; do not include chunk IDs inline."
                ),
            ),
            "citations": types.Schema(
                type="array",
                description="One entry per factual claim. May share the same chunk_id across multiple claims.",
                items=types.Schema(
                    type="object",
                    properties={
                        "chunk_id": types.Schema(
                            type="string",
                            description="The chunk_id value from the [CHUNK ...] header that supports this claim.",
                        ),
                        "quote": types.Schema(
                            type="string",
                            description=(
                                "Short verbatim phrase (10–60 words) copied exactly from the chunk. "
                                "This will be verified against chunk content — paraphrase will fail validation."
                            ),
                        ),
                    },
                    required=["chunk_id", "quote"],
                ),
            ),
            "answer_confidence": types.Schema(
                type="number",
                description=(
                    "How fully the provided chunks support the answer (0.0 = not at all, 1.0 = fully). "
                    "Lower this when the context is incomplete or ambiguous."
                ),
            ),
        },
        required=["answer", "citations", "answer_confidence"],
    ),
)

_ANSWER_TOOL = types.Tool(function_declarations=[_ANSWER_TOOL_DECL])

_ANSWER_TOOL_CONFIG = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(
        mode="any",
        allowed_function_names=["provide_answer"],
    )
)


# ── Factory ───────────────────────────────────────────────────────────────────

def make_generator(api_key: str, model: str = DEFAULT_MODEL) -> "AnswerGenerator":
    """
    Create an AnswerGenerator backed by a configured Gemini client.

    The system instruction is baked into the GenerateContentConfig at call time.
    """
    client = genai.Client(api_key=api_key)
    return AnswerGenerator(client, model=model)


# ── Context formatter ─────────────────────────────────────────────────────────

def format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into the labelled context string sent to the model.

    Each chunk gets a header line:
      [CHUNK {chunk_id} | {source_file} | section: {section}]

    The model is instructed to cite chunk_ids from these headers.
    """
    parts: list[str] = []
    for chunk in chunks:
        header = (
            f"[CHUNK {chunk['chunk_id']} | "
            f"{chunk['source_file']} | "
            f"section: {chunk.get('section', 'unknown')}]"
        )
        parts.append(f"{header}\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


# ── Answer generator ──────────────────────────────────────────────────────────

class AnswerGenerator:
    """
    Calls Gemini with function calling to produce a structured answer + citations.

    Args:
        client:     google.genai.Client instance (configured with API key).
        model:      Gemini model ID string.
        max_tokens: Max output tokens for the generation.
    """

    def __init__(
        self,
        client,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def generate(
        self,
        question: str,
        chunks: list[dict],
        strategy: str = "unknown",
    ) -> RawAnswer:
        """
        Generate an answer for `question` given the retrieved `chunks`.

        Returns RawAnswer with answer_text and unvalidated citations.
        Raises ValueError if Gemini does not return a provide_answer function call.
        """
        if not chunks:
            logger.warning("No chunks provided — returning empty answer")
            return RawAnswer(
                question=question,
                answer_text="I could not find relevant information in the knowledge base to answer this question.",
                citations=[],
                model=self._model,
                latency_ms=0.0,
                retrieval_strategy=strategy,
                chunk_count=0,
            )

        context = format_context(chunks)
        user_message = f"Context chunks:\n\n{context}\n\n---\n\nQuestion: {question}"

        logger.debug(
            "Calling %s with %d chunks (%d chars context)",
            self._model, len(chunks), len(context),
        )

        t0 = time.perf_counter()
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                tools=[_ANSWER_TOOL],
                tool_config=_ANSWER_TOOL_CONFIG,
                max_output_tokens=self._max_tokens,
            ),
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        payload = None
        for part in response.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name == "provide_answer":
                payload = dict(fc.args)
                break

        if payload is None:
            raise ValueError(
                "Gemini did not return a provide_answer function call."
            )

        chunk_map = {c["chunk_id"]: c for c in chunks}

        citations: list[Citation] = []
        for raw in payload.get("citations", []):
            cid = raw.get("chunk_id", "")
            source = chunk_map.get(cid, {}).get("source_file", "unknown")
            citations.append(Citation(
                chunk_id=cid,
                source_file=source,
                quote=raw.get("quote", ""),
            ))

        logger.debug(
            "Generated answer in %.0fms — %d citations", latency_ms, len(citations)
        )

        return RawAnswer(
            question=question,
            answer_text=payload["answer"],
            citations=citations,
            model=self._model,
            latency_ms=latency_ms,
            retrieval_strategy=strategy,
            chunk_count=len(chunks),
            llm_confidence=float(payload.get("answer_confidence", 0.0)),
        )


# ── Mock generator (no API key needed) ───────────────────────────────────────

class MockAnswerGenerator:
    """
    Deterministic answer generator for development and testing.
    No API key or network access required.

    Returns a structured answer whose quote is taken verbatim from the
    top retrieved chunk, so CitationValidator will always mark it valid.
    """

    MODEL = "mock"

    def generate(
        self,
        question: str,
        chunks: list[dict],
        strategy: str = "mock",
    ) -> RawAnswer:
        if not chunks:
            return RawAnswer(
                question=question,
                answer_text="[Mock] No context retrieved for this question.",
                citations=[],
                model=self.MODEL,
                latency_ms=0.0,
                retrieval_strategy=strategy,
                chunk_count=0,
                llm_confidence=0.0,
            )

        top = chunks[0]
        # Use a real substring from the chunk so validation passes
        quote = top["content"][:80].strip().rstrip(",")

        return RawAnswer(
            question=question,
            answer_text=(
                f"[Mock] Based on {top['source_file']}: "
                f"{top['content'][:200].strip()}"
            ),
            citations=[
                Citation(
                    chunk_id=top["chunk_id"],
                    source_file=top["source_file"],
                    quote=quote,
                )
            ],
            model=self.MODEL,
            latency_ms=1.0,
            retrieval_strategy=strategy,
            chunk_count=len(chunks),
            llm_confidence=0.5,
        )
