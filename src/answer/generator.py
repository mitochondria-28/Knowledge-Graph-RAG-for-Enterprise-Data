"""
Answer generator — Phase 8.

WHY TOOL-USE (FUNCTION CALLING) FOR ANSWER GENERATION:

Free-text LLM output is hard to parse reliably. If Claude returns the answer
and citations as prose, we have to regex-parse chunk IDs and quotes — fragile
and untestable. Tool-use forces Claude to return a typed JSON object that we
can validate with a schema. It also makes citation extraction deterministic.

WHY tool_choice={"type": "tool", "name": "provide_answer"}:

Setting tool_choice forces Claude to call exactly the named tool. Without
this, Claude might describe the answer in prose and skip the tool call when
it feels confident. We always want the structured output.

CONTEXT FORMATTING:

Each chunk is presented with a clearly labelled header:

  [CHUNK abc123 | corpus/companies/technova_overview.md | section: Overview]
  <content>

Claude is instructed to cite chunk_ids from these headers. The separator
between chunks is '---' so Claude can visually distinguish boundaries.

SECURITY:

  - Claude receives chunk content as read-only context; it cannot modify chunks
  - We never execute any code from Claude's output
  - citation chunk_ids are validated downstream by CitationValidator
  - If Claude invents a chunk_id, CitationValidator will flag it as invalid
"""

import logging
import time

from src.answer.models import Citation, RawAnswer

logger = logging.getLogger(__name__)

# ── Default model ─────────────────────────────────────────────────────────────
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are an enterprise knowledge assistant. Your job is to answer questions using ONLY the context chunks provided below.

Rules you must follow:
1. Base every statement on information in the provided chunks — never use background knowledge
2. Cite EVERY factual claim using the chunk_id from the [CHUNK ...] header
3. The quote field must be a short, verbatim phrase (10–60 words) copied exactly from that chunk
4. If the context does not contain enough information to answer fully, say so explicitly
5. Use the provide_answer tool to return your structured response — no free-text output

Context chunk format:
  [CHUNK {chunk_id} | {source_file} | section: {section}]
  {content}
  ---
"""

# ── Tool definition ───────────────────────────────────────────────────────────
_ANSWER_TOOL: dict = {
    "name": "provide_answer",
    "description": (
        "Return a structured answer with citations from the retrieved context chunks. "
        "Every factual claim must have a matching citation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": (
                    "Complete answer to the question based only on the provided chunks. "
                    "Use plain prose; do not include chunk IDs inline."
                ),
            },
            "citations": {
                "type": "array",
                "description": "One entry per factual claim. May share the same chunk_id across multiple claims.",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {
                            "type": "string",
                            "description": "The chunk_id value from the [CHUNK ...] header that supports this claim.",
                        },
                        "quote": {
                            "type": "string",
                            "description": (
                                "Short verbatim phrase (10–60 words) copied exactly from the chunk. "
                                "This will be verified against chunk content — paraphrase will fail validation."
                            ),
                        },
                    },
                    "required": ["chunk_id", "quote"],
                },
            },
            "answer_confidence": {
                "type": "number",
                "description": (
                    "How fully the provided chunks support the answer (0.0 = not at all, 1.0 = fully). "
                    "Lower this when the context is incomplete or ambiguous."
                ),
            },
        },
        "required": ["answer", "citations", "answer_confidence"],
    },
}


# ── Context formatter ─────────────────────────────────────────────────────────

def format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into the labelled context string sent to Claude.

    Each chunk gets a header line:
      [CHUNK {chunk_id} | {source_file} | section: {section}]

    Claude is instructed to cite chunk_ids from these headers.
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
    Calls Claude with tool-use to produce a structured answer + citations.

    Args:
        client:  anthropic.Anthropic instance (must be authenticated).
        model:   Claude model ID. Haiku is the default (fast + cheap).
        max_tokens: Max tokens for the tool-use response.
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
        Raises ValueError if Claude does not return a provide_answer tool call.
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
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM_PROMPT,
            tools=[_ANSWER_TOOL],
            tool_choice={"type": "tool", "name": "provide_answer"},
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        tool_block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == "provide_answer"),
            None,
        )
        if tool_block is None:
            raise ValueError(
                "Claude did not return a provide_answer tool call. "
                f"Response content types: {[b.type for b in response.content]}"
            )

        payload = tool_block.input
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
