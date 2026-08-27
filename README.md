# Enterprise Knowledge Graph RAG

A production-quality Retrieval-Augmented Generation system that combines **vector similarity search** with **multi-hop knowledge graph traversal** to answer complex enterprise questions — with every citation verified against its source document.

Built phase-by-phase as a portfolio project demonstrating the full engineering stack: ingestion → knowledge graph → hybrid retrieval → LLM generation → citation validation → FastAPI backend → observability → testing → React UI.

---

## How it works

```
Question
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Question Router  (rule-based, ~1ms, no LLM)            │
│  R1 greeting → vector                                   │
│  R2 definition ("what is") → vector                     │
│  R3 3+ entities → hybrid                                │
│  R4 relational verb + entities → graph                  │
│  R5 multi-hop keyword → graph                           │
│  R6 temporal → vector   R7 comparison → hybrid          │
│  R8 single entity → vector                              │
│  R9 has entities → graph   R10 default → vector         │
└──────────────┬──────────────────────────────────────────┘
               │ strategy: vector / graph / hybrid
               ▼
┌─────────────────────────────────────────────────────────┐
│  Retrieval                                              │
│  vector  → pgvector cosine similarity (text-embed-3)    │
│  graph   → Neo4j 1–3 hop Cypher traversal               │
│  hybrid  → union of both, re-ranked                     │
│  (keyword fallback — no databases required)             │
└──────────────┬──────────────────────────────────────────┘
               │ ranked chunks
               ▼
┌─────────────────────────────────────────────────────────┐
│  Answer Generator  (Google Gemini gemini-2.5-flash)     │
│  Forced function calling → structured JSON output       │
│  { answer_text, citations: [{chunk_id, quote}] }        │
└──────────────┬──────────────────────────────────────────┘
               │ raw answer + citations
               ▼
┌─────────────────────────────────────────────────────────┐
│  Citation Validator                                     │
│  exact substring → VALID (score 1.0)                   │
│  rapidfuzz partial_ratio ≥ 0.80 → VALID (fuzzy)        │
│  otherwise → INVALID (hallucination detected)           │
│  citation_confidence = valid / total                    │
└──────────────┬──────────────────────────────────────────┘
               │ ValidatedAnswer
               ▼
           Response
```

---

## Quick start

### Prerequisites

- Python 3.11+
- Node 18+ (UI only)
- A Google Gemini API key (optional — falls back to `MockAnswerGenerator` without one)

### 1. Clone and install

```bash
git clone https://github.com/mitochondria-28/Knowledge-Graph-RAG-for-Enterprise-Data.git
cd Knowledge-Graph-RAG-for-Enterprise-Data

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install fastapi[standard] uvicorn httpx rapidfuzz prometheus-client \
            opentelemetry-sdk opentelemetry-api hypothesis pytest-cov
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — only GEMINI_API_KEY is needed for basic use
```

`.env.example`:
```
GEMINI_API_KEY=AIza...         # optional — mock generator used if absent
NEO4J_PASSWORD=                # optional — needed for graph retrieval
POSTGRES_PASSWORD=             # optional — needed for vector retrieval
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 3. Ingest the corpus

```bash
python scripts/ingest.py        # chunks 13 sample docs → output/all_chunks.json
```

> **Or skip this step** — once the API server and UI are running you can upload
> documents directly from the browser's **Documents** tab without touching the CLI.

### 4. Ask a question (CLI)

```bash
# No API key needed — uses MockAnswerGenerator
python scripts/ask.py "What is StellarDB?" --mock

# With real Gemini
python scripts/ask.py "Who leads the Platform Team?" --verbose
```

### 5. Start the API server

```bash
python scripts/serve.py         # FastAPI on http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 6. Start the UI

```bash
cd ui && npm install && npm run dev
# Open http://localhost:5173
```

---

## Running the full stack with databases

Start Neo4j and PostgreSQL with Docker Compose:

```bash
docker compose up -d
```

Then run the full pipeline to populate the graph and vector store:

```bash
python scripts/ingest.py        # Phase 1 — chunking
python scripts/extract.py       # Phase 2 — entity/relationship extraction
python scripts/resolve.py       # Phase 3 — entity resolution (Union-Find)
python scripts/load_graph.py    # Phase 4 — load into Neo4j
python scripts/embed_chunks.py  # Phase 5 — embed into pgvector
```

---

## Tests

```bash
# All 515 tests
pytest

# By category
pytest -m unit          # 448 fast isolated tests
pytest -m integration   # 29 full-pipeline tests (real stages, no DB needed)
pytest -m property      # 19 Hypothesis property-based tests
pytest -m api           # 43 FastAPI endpoint tests

# With coverage (60% threshold)
pytest --cov=src --cov-report=term-missing
```

---

## Benchmarking

```bash
# Mock mode (no API key, <5ms per question)
python scripts/benchmark.py --mock

# Real Gemini (requires GEMINI_API_KEY)
python scripts/benchmark.py --questions 20
```

Results on 20 evaluation questions (mock mode, keyword retrieval):

| Metric | Value |
|--------|-------|
| Routing accuracy | 85% (17/20) |
| Citation confidence | 100% (mock verbatim quotes) |
| Total latency p50 | ~0.9ms (keyword retrieval; real Gemini adds ~800ms–1500ms) |

---

## API reference

### `POST /ask`

```json
// Request
{ "question": "Who leads the Platform Team?", "top_k": 5 }

// Response
{
  "question": "Who leads the Platform Team?",
  "answer": "The Platform Team is led by ...",
  "citations": [
    {
      "chunk_id": "abc123",
      "source_file": "corpus/team_overview.md",
      "quote": "The Platform Team is led by ...",
      "is_valid": true,
      "match_score": 1.0,
      "reason": "exact match"
    }
  ],
  "citation_confidence": 1.0,
  "retrieval_strategy": "graph",
  "model": "gemini-2.5-flash",
  "latency_ms": 842.3,
  "chunk_count": 5
}
```

### `POST /documents/upload`

Upload a document and ingest it into the corpus without restarting the server.
The pipeline's chunk list is hot-reloaded in memory, so the new content is
immediately queryable.

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@my_report.pdf" \
  -F "doc_type=project"   # general | company | project | technology | people
```

```json
// Response
{
  "filename": "my_report.pdf",
  "doc_type": "project",
  "stats": {
    "documents_processed": 1,
    "documents_skipped": 0,
    "chunks_created": 4,
    "avg_tokens_per_chunk": 312
  }
}
```

Supported formats: `.md`, `.txt`, `.pdf` · Max size: 10 MB · Re-uploading an
unchanged file is a no-op (hash-based deduplication).

### `GET /documents`

List every ingested document with its type, chunk count, and ingestion timestamp.

```json
[
  {
    "document_id": "abc123",
    "title": "Orion Platform",
    "source_file": "corpus/uploads/technologies/orion_platform.md",
    "doc_type": "technology",
    "chunk_count": 3,
    "ingested_at": "2026-08-27T03:08:38+00:00"
  }
]
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Always 200 — liveness probe |
| `GET` | `/ready` | 200 if pipeline loaded, 503 otherwise |
| `GET` | `/metrics` | Prometheus text exposition |
| `GET` | `/docs` | Swagger UI (auto-generated) |

---

## Observability

Every request emits three signals:

**Structured JSON logs** (stdout):
```json
{"ts": "2026-08-25T12:00:00Z", "level": "INFO", "logger": "src.answer.pipeline",
 "msg": "Routed question", "stage": "route", "strategy": "graph",
 "hop_depth": 1, "duration_ms": 0.12}
```

**Prometheus metrics** (`GET /metrics`):
```
kg_rag_requests_total{status_code="200",strategy="graph"} 42
kg_rag_pipeline_stage_duration_seconds_bucket{stage="generate",le="1.0"} 38
kg_rag_citation_confidence_sum 41.0
```

**OpenTelemetry spans** (in-memory by default):
```
ask (root)
  ├── route    [strategy=graph, hop_depth=1, confidence=0.85]
  ├── retrieve [chunk_count=5]
  ├── generate [model=gemini-2.5-flash, citation_count=2]
  └── validate [valid_citations=2, invalid_citations=0]
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` to export to Jaeger.

---

## Project structure

```
enterprise-kg-rag/
├── corpus/                   # Source documents
│   ├── companies/            # 13 sample TechNova Markdown documents
│   ├── projects/
│   ├── technologies/
│   ├── people/
│   └── uploads/              # Files uploaded through the UI (auto-created)
├── output/                   # Pipeline artifacts (chunks, embeddings, benchmark)
│   ├── all_chunks.json       # Chunks from ingestion (sample + uploads)
│   └── benchmark_report.json # Latest benchmark run
├── scripts/                  # CLI entry points for each phase
│   ├── ingest.py             # Phase 1 — chunking
│   ├── extract.py            # Phase 2 — entity extraction (Gemini)
│   ├── resolve.py            # Phase 3 — entity resolution
│   ├── load_graph.py         # Phase 4 — Neo4j loader
│   ├── embed_chunks.py       # Phase 5 — pgvector embedder
│   ├── ask.py                # Phase 8 — CLI Q&A
│   ├── serve.py              # Phase 9 — FastAPI server
│   └── benchmark.py          # Phase 10 — benchmarking
├── src/
│   ├── ingestion/            # Phase 1 — document loading and chunking
│   ├── extraction/           # Phase 2 — NER and relationship extraction
│   ├── resolution/           # Phase 3 — entity deduplication (Union-Find)
│   ├── graph/                # Phase 4 — Neo4j graph schema and loader
│   ├── vector/               # Phase 5 — pgvector embedding store
│   ├── evaluation/           # Phase 6 — retrieval evaluation (P@k, MRR, F1)
│   ├── router/               # Phase 7 — rule-based question classifier
│   ├── answer/               # Phase 8 — generation + citation validation
│   ├── api/                  # Phase 9 — FastAPI app, routes, schemas
│   │   └── routes/
│   │       ├── ask.py        # POST /ask
│   │       ├── documents.py  # POST /documents/upload, GET /documents
│   │       ├── health.py     # GET /health, /ready
│   │       └── metrics.py    # GET /metrics
│   ├── benchmark/            # Phase 10 — latency and quality benchmarking
│   ├── observability/        # Phase 11 — logging, Prometheus, OpenTelemetry
│   └── config.py             # Pydantic settings
├── tests/
│   ├── unit/                 # 448 isolated unit tests
│   ├── integration/          # 29 full-pipeline tests
│   └── api/                  # 43 FastAPI endpoint tests
├── ui/                       # Phase 13 — React + Vite + Tailwind frontend
│   └── src/
│       ├── api/client.js
│       └── components/
│           ├── QuestionForm.jsx
│           ├── AnswerCard.jsx
│           ├── CitationList.jsx
│           ├── MetaBadges.jsx
│           ├── DocumentUpload.jsx  # Phase 15 — drag-and-drop upload panel
│           └── DocumentList.jsx    # Phase 15 — ingested document browser
├── docker-compose.yml        # Neo4j + PostgreSQL
└── pyproject.toml            # Dependencies, pytest config, coverage
```

---

## Phase-by-phase build log

| Phase | What was built | Key technique |
|-------|---------------|---------------|
| 1 | Document ingestion + chunking | Token-based sliding window (tiktoken) |
| 2 | Entity & relationship extraction | Gemini function calling (forced structured output) |
| 3 | Entity resolution | Union-Find clustering + fuzzy deduplication |
| 4 | Knowledge graph | Neo4j with MERGE idempotency + query allowlist |
| 5 | Vector store | pgvector + text-embedding-3-small |
| 6 | Retrieval evaluation | Precision@k, Recall@k, F1@k, MRR |
| 7 | Question router | 10 ordered rules, ~1ms, zero LLM calls, 85% accuracy |
| 8 | Answer generation + validation | Gemini function calling + rapidfuzz citation verifier |
| 9 | FastAPI backend | Lifespan startup, Pydantic validation, 503/422/500 |
| 10 | Benchmarking | Per-stage timing, p50/p95/p99, citation confidence |
| 11 | Observability | JSON logs, Prometheus metrics, OpenTelemetry spans |
| 12 | Comprehensive testing | Integration tests, Hypothesis property-based, coverage |
| 13 | React UI | Vite + Tailwind, dark mode, citation panel, routing badges |
| 14 | Documentation | README, ARCHITECTURE.md |
| 15 | Dynamic document upload | REST upload API + drag-and-drop UI, hot-reload without restart |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini (gemini-2.5-flash) |
| Embeddings | OpenAI text-embedding-3-small |
| Knowledge graph | Neo4j 5.20 |
| Vector store | PostgreSQL 16 + pgvector |
| API | FastAPI + Uvicorn |
| UI | React 19 + Vite 6 + Tailwind CSS v4 |
| Fuzzy matching | rapidfuzz |
| Metrics | prometheus-client |
| Tracing | OpenTelemetry SDK |
| Testing | pytest + Hypothesis |
| Config | pydantic-settings |

---

## Security notes

- All Cypher queries use **parameterized statements** from an **allowlist** — no raw LLM-generated queries are executed
- Citations are **validated against source text** before being returned — hallucinations are flagged, not silently passed through
- API keys are loaded from environment variables, never hardcoded
- The FastAPI layer validates every request with **Pydantic** — invalid inputs return 422 automatically
- CORS is restricted to `localhost:3000` and `localhost:5173` in development

---

## License

MIT
