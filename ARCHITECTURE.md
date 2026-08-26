# Architecture

Deep-dive into the design decisions behind each phase of the Enterprise KG-RAG system.

---

## Corpus

**13 synthetic Markdown documents** about the fictional company "TechNova Corporation":

```
corpus/
  company_overview.md        competitor_analysis.md
  compliance_and_security.md customer_success.md
  engineering_practices.md   financial_performance.md
  hr_and_culture.md          partnerships.md
  product_roadmap.md         research_and_innovation.md
  team_structure.md          technology_infrastructure.md
  technova_stellar_acquisition.md
```

**Why synthetic?** Real enterprise corpora contain PII and trade secrets. The synthetic corpus covers the same structural patterns — org charts, acquisitions, product specs, compliance certifications, financial metrics — without any data-handling concerns.

**27 chunks** produced by the Phase 1 ingestion pipeline. Each chunk is ~500 tokens with 100-token overlap.

---

## Phase 1 — Ingestion and chunking

**File:** `src/ingestion/`

Token-based sliding-window chunking using `tiktoken` (cl100k_base, same tokenizer Claude uses). Chunks have metadata:

```python
{
  "chunk_id": "uuid4",
  "document_id": "uuid4",
  "source_file": "corpus/team_structure.md",
  "section": "Platform Team",       # extracted from nearest heading
  "chunk_index": 3,
  "content": "...",
  "token_count": 487,
}
```

**Why token-based, not sentence-based?** Token counts are what the LLM context window cares about. Sentence boundaries produce chunks of wildly variable size. Token-based chunking with overlap guarantees every chunk fits in the generation context and that long sentences spanning a boundary are covered by both adjacent chunks.

---

## Phase 2 — Entity and relationship extraction

**File:** `src/extraction/`

Uses **Claude tool-use** (forced structured output) to extract:

- **7 entity types:** Company, Person, Team, Technology, Product, Location, Regulation
- **12 relationship types:** LEADS, MEMBER_OF, ACQUIRED, USES, DEVELOPS, PARTNERS_WITH, COMPETES_WITH, COMPLIES_WITH, LOCATED_IN, REPORTS_TO, FOUNDED_BY, INVESTS_IN

The extraction prompt forces a specific JSON schema via `tool_choice={"type":"tool","name":"extract_entities"}`. This is more reliable than asking the LLM to output JSON in the text — tool-use bypasses the LLM's tendency to add commentary around structured data.

**Why Claude for extraction?** The alternative is a fine-tuned NER model (SpaCy, Flair). Claude zero-shot outperforms them on domain-specific entities like product names and team names without any training data.

---

## Phase 3 — Entity resolution

**File:** `src/resolution/`

The same entity appears across documents with different spellings:
- "TechNova Corporation" / "TechNova Corp" / "TechNova" / "the Company"
- "StellarDB" / "Stellar DB" / "Stellar Database"

Resolution pipeline:

1. **Normalization** — lowercase, strip punctuation, collapse whitespace
2. **Exact deduplication** — normalized form → canonical name
3. **Fuzzy matching** — `rapidfuzz.fuzz.token_sort_ratio ≥ 85` → same entity
4. **Union-Find clustering** — merge all aliases into one canonical group
5. **Output** — `resolved_entities.json`: each unique entity with all its aliases

**Why Union-Find?** Fuzzy matching produces pairwise equivalences. Union-Find converts these into clusters efficiently in O(n α(n)) time. The alternative — building an explicit graph and running connected components — is correct but heavier.

---

## Phase 4 — Knowledge graph

**File:** `src/graph/`

Neo4j with parameterized `MERGE` statements. The schema:

```cypher
// Entities
(:Company {id, name, aliases})
(:Person  {id, name, title})
(:Team    {id, name})
(:Technology {id, name})

// Relationships
(p:Person)-[:LEADS]->(t:Team)
(c1:Company)-[:ACQUIRED {year}]->(c2:Company)
(t:Team)-[:DEVELOPS]->(tech:Technology)
```

**Security: query allowlist.** The graph loader only executes queries from a hardcoded list of templates. LLM-generated Cypher is never executed directly — this prevents prompt injection from escalating into database writes or schema changes.

**Idempotency:** Every write uses `MERGE` (upsert). Running the loader twice produces the same graph — no duplicate nodes. This is essential for the reload-on-corpus-change workflow.

---

## Phase 5 — Vector store

**File:** `src/vector/`

`text-embedding-3-small` (OpenAI, 1536 dimensions) stored in PostgreSQL 16 with the `pgvector` extension. Each chunk row:

```sql
CREATE TABLE chunks (
  chunk_id   UUID PRIMARY KEY,
  source_file TEXT,
  section    TEXT,
  content    TEXT,
  embedding  vector(1536)
);

CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 10);
```

**Why pgvector over Pinecone/Weaviate?** No additional service to run. PostgreSQL is already present for relational data. pgvector's cosine similarity is competitive with dedicated vector databases at corpora under 1M chunks. It also lets you JOIN vector results with relational metadata in a single query.

---

## Phase 6 — Retrieval evaluation

**File:** `src/evaluation/`

20 hand-labeled evaluation questions across 6 types:

| Type | Count | Expected strategy |
|------|-------|------------------|
| simple_entity | 4 | vector |
| factual | 3 | vector |
| one_hop | 4 | graph |
| two_hop | 3 | graph |
| three_hop | 2 | graph |
| multi_entity | 4 | hybrid |

Metrics computed per question and aggregated:
- **Precision@k** — fraction of retrieved chunks that are relevant
- **Recall@k** — fraction of relevant chunks that were retrieved
- **F1@k** — harmonic mean of P@k and R@k
- **MRR** — Mean Reciprocal Rank of first relevant chunk

---

## Phase 7 — Question router

**File:** `src/router/`

The router classifies a question → `{strategy, hop_depth, confidence}` in **~1ms** using 10 ordered rules with no LLM calls.

```
R1  Greeting/meta    → vector  (confidence 1.0)
R2  Definition       → vector  ("what is", "define", "explain")
R3  3+ entities      → hybrid
R4  Relational verb + entities (not temporal, not definition) → graph
R5  Multi-hop keyword → graph  ("path", "chain", "through", "via")
R6  Temporal         → vector  ("when", "date", year patterns)
R7  Comparison       → hybrid  ("compare", "difference", "versus")
R8  Single entity    → vector  (one known entity, no relational signal)
R9  Has entities     → graph
R10 Default          → vector
```

**Signal extraction** (`src/router/signals.py`) detects:
- Entity matches against the entity index (7 types × all aliases)
- Linguistic patterns compiled as `re.compile()` objects (done once at startup)
- Temporal expressions: year patterns, "when", "date", "founded in"
- Relational verbs: "leads", "manages", "acquired", "reports to"
- Definition markers: "what is", "define", "what are"
- Acquisition patterns: `acquired?|acquisitions?|merger|purchase`

**Why rule-based instead of an LLM classifier?** An LLM classifier adds ~500ms and requires an API call for every question — including simple factual lookups that are definitively "vector". Rule-based routing costs 1ms, is 100% auditable, and achieves 85% accuracy on the evaluation set. The 15% misroutes are mostly edge cases where any strategy would retrieve roughly the same chunks.

**R4 refinement (from test failures):** "When did TechNova acquire Stellar Systems?" has a relational verb ("acquire") and entities, so a naive rule fires R4 → graph. But temporal questions should always go to vector (the acquisition date is a fact in a document, not a graph edge). The fix: R4 guards on `not features.is_temporal` before firing. Similarly `not features.is_definition` and `features.entity_count < 3` prevent R4 from stealing definition and multi-entity questions.

---

## Phase 8 — Answer generation + citation validation

**File:** `src/answer/`

### Generation

Claude is called with `tool_choice={"type":"tool","name":"provide_answer"}`, which forces it to populate a specific schema:

```json
{
  "answer_text": "...",
  "citations": [
    {"chunk_id": "abc", "source_file": "corpus/x.md", "quote": "verbatim phrase"}
  ],
  "confidence": 0.9
}
```

Forcing tool-use prevents the LLM from wrapping JSON in markdown code blocks or adding commentary. The `confidence` field is discarded — we compute `citation_confidence` ourselves from validation results, not from the LLM's self-assessment.

### Citation validation

Three-step algorithm per citation:

1. **chunk_id lookup** — if the cited chunk wasn't in the retrieved set, it's a hallucinated reference (INVALID)
2. **Exact substring** — `quote.lower() in content.lower()` → VALID, score 1.0
3. **Fuzzy partial ratio** — `rapidfuzz.fuzz.partial_ratio(quote, content) / 100 ≥ 0.80` → VALID, score = ratio

**Why `partial_ratio` over `ratio`?** `ratio` compares two strings of equal length. A 30-character quote against a 500-token chunk will always score low even if the phrase appears verbatim. `partial_ratio` slides a window of the shorter string over the longer one and takes the best match — which is exactly the semantic we want: "does this phrase appear anywhere in the chunk?"

**Why 0.80 threshold?** Empirically: it accepts minor punctuation and whitespace differences (e.g., em-dash vs. space-dash, smart quotes vs. straight quotes) while firmly rejecting paraphrased or fabricated content.

---

## Phase 9 — FastAPI backend

**File:** `src/api/`

### Startup pattern

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    chunks = load_chunks()           # read output/all_chunks.json once
    entity_index = load_entity_index()
    pipeline = AnswerPipeline(...)
    app.state.pipeline = pipeline    # attached to app, not to the request
    yield
```

Resources are loaded **once at startup** and attached to `app.state`. Each request reads `request.app.state.pipeline` — no per-request initialization cost.

### Error taxonomy

| Status | Trigger | Meaning |
|--------|---------|---------|
| 200 | Normal | Answer with validated citations |
| 422 | Pydantic validation fail | question empty, top_k out of range |
| 503 | Pipeline not yet in `app.state` | Server still starting up |
| 500 | Unhandled pipeline exception | Bug in generation/validation |

### Why sync route handler?

`pipeline.ask()` is synchronous CPU work + one synchronous HTTP call to Anthropic. FastAPI runs sync handlers in a thread pool automatically. Making the handler `async` would be wrong — it would block the event loop during the Claude HTTP call.

---

## Phase 10 — Benchmarking

**File:** `src/benchmark/`

The benchmark runner calls **each pipeline stage directly** with independent `time.perf_counter()` clocks rather than calling `pipeline.ask()` end-to-end. This is the only correct way to get per-stage latency breakdowns — wrapping `pipeline.ask()` in a timer gives you a single total figure.

```python
t0 = time.perf_counter()
decision = pipeline._router.route(q.question)
routing_ms = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
retrieved = pipeline._retriever_fn(q.question, pipeline._chunks, pipeline._top_k)
retrieval_ms = (time.perf_counter() - t0) * 1000
# ... etc.
```

Percentile calculation uses **linear interpolation** matching `numpy.percentile(data, p, interpolation='linear')` — implemented from scratch so there's no numpy dependency in the benchmark module.

**Floating-point rounding note:** Each stage timing is rounded to 3 decimal places independently before storage. The sum of 4 rounded values differs from the rounded total by up to 0.004ms. Tests use `pytest.approx(expected, abs=0.005)` to handle this.

---

## Phase 11 — Observability

**File:** `src/observability/`

### Structured logging

`_JsonFormatter` emits one JSON line per record with fields: `ts`, `level`, `logger`, `msg`, plus any `extra={}` fields the caller passes. Exception tracebacks are inlined as a string (keeps each log entry on one line for log aggregators).

`configure_logging()` is idempotent — safe to call multiple times. The second call only updates the log level; it does not add a second handler. This prevents duplicate log output in tests that call `create_app()` multiple times.

### Prometheus metrics

7 metrics in the `kg_rag_` namespace:

| Name | Type | Labels |
|------|------|--------|
| `kg_rag_requests_total` | Counter | status_code, strategy |
| `kg_rag_request_errors_total` | Counter | error_type |
| `kg_rag_pipeline_stage_duration_seconds` | Histogram | stage |
| `kg_rag_pipeline_total_duration_seconds` | Histogram | — |
| `kg_rag_citation_confidence` | Histogram | — |
| `kg_rag_corpus_chunks` | Gauge | — |
| `kg_rag_corpus_entities` | Gauge | — |

### OpenTelemetry tracing

`configure_tracing()` uses an `InMemorySpanExporter` by default — no external service needed. Tests call `get_in_memory_spans()` to assert span names and attributes.

**Critical implementation detail:** `get_tracer()` calls `_provider.get_tracer(name)` directly, **not** `trace.get_tracer(name)`. The OTel global `TracerProvider` cannot be safely overridden once set — doing so via `trace.set_tracer_provider(ProxyTracerProvider())` causes infinite recursion because `ProxyTracerProvider.get_tracer()` delegates to `_TRACER_PROVIDER`, which is still the `ProxyTracerProvider`. By keeping the provider in a module-level variable and bypassing the global API, `reset_tracing()` works cleanly in tests.

---

## Phase 12 — Testing strategy

**File:** `tests/`

### Test taxonomy

```
tests/unit/        — 448 tests: one class/function in isolation, no I/O
tests/integration/ — 29 tests:  real stages composed, no DB or API key
tests/api/         — 43 tests:  FastAPI TestClient, HTTP semantics
```

### Property-based tests (Hypothesis)

Rather than specific examples, Hypothesis generates hundreds of random inputs and verifies invariants:

- **Router:** `strategy ∈ {vector, graph, hybrid}` for any non-empty string
- **Router:** `confidence ∈ [0, 1]` for any input
- **Retriever:** `len(result) ≤ top_k` for any (question, top_k) pair
- **Validator:** `match_score ∈ [0, 1]` for any (quote, content) pair
- **Validator:** exact substring always validates
- **Pipeline:** `ask()` never raises for any non-empty string

All property tests use `deadline=None` — Hypothesis has a 200ms default deadline that triggers on the first run due to Python import latency, producing spurious `FlakyFailure` errors.

### Integration test corpus fallback

If `output/all_chunks.json` is absent (e.g., CI without the ingest step), the integration test fixture builds a 10-chunk synthetic corpus in memory. This makes the integration tests infrastructure-independent.

---

## Phase 13 — React UI

**File:** `ui/`

### Component hierarchy

```
App
├── header: ReadyIndicator (green/amber dot)
├── QuestionForm (text input + top_k slider)
├── [example pills] (hidden after first answer)
├── [ErrorBanner]
├── [LoadingSkeleton] (animate-pulse while fetching)
└── history: AnswerCard[]
    ├── question / answer text
    ├── MetaBadges (strategy pill, latency, citation %, model)
    └── CitationList (collapsible, per-citation valid/invalid badge)
```

### Routing strategy pill colors

| Strategy | Color | Rationale |
|----------|-------|-----------|
| vector | Sky blue | Fast, semantic |
| graph | Amber | Structural, traversal |
| hybrid | Violet | Combined |

### Vite proxy

In development, Vite proxies `/ask`, `/health`, `/ready` → `http://localhost:8000`. No CORS configuration needed during development, and the UI and API can be deployed to different origins in production by setting `VITE_API_URL`.

---

## Data flow — end to end

```
User types question
       │
       ▼  POST /ask {question, top_k}
FastAPI route (src/api/routes/ask.py)
       │  Pydantic validates: question 1–500 chars, top_k 1–20
       │
       ▼
AnswerPipeline.ask(question, top_k)       [src/answer/pipeline.py]
       │
       ├─ OTel span "ask" opened
       │
       ├─→ QuestionRouter.route(question)  [src/router/]
       │      signals: entity detection, linguistic patterns (~1ms)
       │      returns: RoutingDecision(strategy, hop_depth, confidence)
       │      OTel span "route" + Prometheus histogram stage=route
       │
       ├─→ retriever_fn(question, chunks, top_k)
       │      keyword: token overlap, no DB
       │      vector:  pgvector cosine similarity
       │      graph:   Neo4j 1–3 hop Cypher
       │      OTel span "retrieve" + histogram stage=retrieve
       │
       ├─→ AnswerGenerator.generate(question, chunks, strategy)
       │      Claude tool-use, forces provide_answer schema
       │      returns: RawAnswer(answer_text, citations, model, latency_ms)
       │      OTel span "generate" + histogram stage=generate
       │
       └─→ CitationValidator.validate(raw_answer, retrieved)
              for each citation:
                chunk_id in chunk_map?  → INVALID if not
                exact substring match?  → VALID score=1.0
                partial_ratio ≥ 0.80?  → VALID score=ratio
                else                   → INVALID
              returns: ValidatedAnswer(citation_confidence, ...)
              OTel span "validate" + histogram stage=validate
              Prometheus: citation_confidence histogram, requests_total counter
       │
       ▼
AskResponse serialized → JSON → client
       │
       ▼
React renders AnswerCard with MetaBadges + CitationList
```

---

## Failure modes and mitigations

| Failure | Mitigation |
|---------|-----------|
| No API key | `MockAnswerGenerator` — deterministic verbatim quotes, always validates |
| No Neo4j | Keyword retrieval fallback — no DB, token overlap |
| No pgvector | Keyword retrieval fallback |
| LLM hallucinated chunk_id | `CitationValidator` catches → `is_valid=False` |
| LLM paraphrased quote | `CitationValidator` fuzzy check → INVALID if score < 0.80 |
| Pipeline not yet loaded at startup | FastAPI returns 503; `/ready` probe confirms |
| Invalid request body | Pydantic returns 422 automatically |
| Slow LLM response | Timeouts configured in Anthropic client; retry handled by client SDK |
