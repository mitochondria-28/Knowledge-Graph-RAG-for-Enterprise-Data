# Enterprise Knowledge Graph RAG

A production-quality Retrieval-Augmented Generation system that combines **vector similarity search** with **multi-hop knowledge graph traversal** to answer complex enterprise questions — with every citation verified against its source document.

Built phase-by-phase as a portfolio project demonstrating the full engineering stack: ingestion → knowledge graph → hybrid retrieval → LLM generation → citation validation → FastAPI backend → observability → testing → React UI → **per-user authentication and isolated knowledge bases**.

---

## How it works

```
Question
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Auth Guard  (JWT Bearer token — per-user corpus)       │
└──────────────┬──────────────────────────────────────────┘
               │ authenticated user
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
│  Retrieval  (user's private corpus only)                │
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
            opentelemetry-sdk opentelemetry-api hypothesis pytest-cov \
            "python-jose[cryptography]" "passlib[bcrypt]" sqlalchemy python-multipart
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys
```

`.env.example`:
```
GEMINI_API_KEY=AIza...                  # optional — mock generator used if absent
NEO4J_PASSWORD=                         # optional — needed for graph retrieval
POSTGRES_PASSWORD=                      # optional — needed for vector retrieval
LOG_LEVEL=INFO

# Auth — generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=change-me-in-production

# Google OAuth (optional — leave blank to disable Google login)
# Create credentials at https://console.cloud.google.com/apis/credentials
# Add http://localhost:5173 to Authorized JavaScript origins
VITE_GOOGLE_CLIENT_ID=
```

### 3. Start the API server

```bash
python scripts/serve.py --reload     # FastAPI on http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 4. Start the UI

```bash
cd ui && npm install && npm run dev
# Open http://localhost:5173
```

Register an account (or sign in with Google), upload your documents, and start asking questions — no CLI setup needed.

### 5. Ingest the corpus (optional CLI)

```bash
python scripts/ingest.py        # chunks 13 sample docs → output/all_chunks.json
```

> Documents uploaded through the browser UI are automatically ingested per-user and are immediately queryable — no CLI step needed.

---

## Authentication & per-user knowledge bases

Every account gets a completely private, isolated knowledge base. No user can see or query another user's documents.

### How it works

| What | Where |
|------|-------|
| User accounts | SQLite (`auth.db`) via SQLAlchemy |
| Passwords | bcrypt-hashed — never stored in plaintext |
| Sessions | JWT Bearer tokens (7-day expiry, HS256) |
| Google login | ID token verified against Google's tokeninfo endpoint |
| User documents | `corpus/users/{user_id}/` |
| User chunks | `output/users/{user_id}/` |
| User pipeline | `app.state.user_pipelines[user_id]` — lazy-built, memory-cached |

### Auth endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Create account — returns JWT + user |
| `POST` | `/auth/login` | Email + password — returns JWT + user |
| `POST` | `/auth/google` | Google ID token — returns JWT + user |
| `GET` | `/auth/me` | Returns the current user's profile |

All other data endpoints (`/ask`, `/documents/upload`, `/documents`) require an `Authorization: Bearer <token>` header and operate exclusively on the authenticated user's data.

### Register (email/password)

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@company.com","password":"SecurePass1!","name":"Your Name"}'
```

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "user": {
    "id": "f9589d18-...",
    "email": "you@company.com",
    "name": "Your Name",
    "avatar_url": null
  }
}
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@company.com","password":"SecurePass1!"}'
```

### Google login (UI)

Set `VITE_GOOGLE_CLIENT_ID` in `.env` with your OAuth 2.0 Web client ID from [Google Cloud Console](https://console.cloud.google.com/apis/credentials). Add `http://localhost:5173` to **Authorized JavaScript origins**. The login and register pages both show a **Sign in with Google** button automatically when the ID is set.

### Isolation guarantee

```
User A uploads report.pdf  →  corpus/users/uid-A/general/report.pdf
User A asks a question      →  answers only from uid-A's chunks
User B asks the same        →  400 "Your knowledge base is empty"
                               (until B uploads their own documents)
```

---

## API reference

All data endpoints require the header: `Authorization: Bearer <your_token>`

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
      "source_file": "corpus/users/uid/people/team_overview.md",
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

Returns `400` with a clear message if the user has not uploaded any documents yet.

### `POST /documents/upload`

Upload a document into the authenticated user's private corpus. The pipeline is rebuilt immediately — no server restart needed.

```bash
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@my_report.pdf" \
  -F "doc_type=project"   # general | company | project | technology | people
```

```json
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

Supported formats: `.md`, `.txt`, `.pdf` · Max size: 10 MB · Re-uploading an unchanged file is a no-op (hash-based deduplication).

### `GET /documents`

List documents uploaded by the current user only.

```json
[
  {
    "document_id": "abc123",
    "title": "Q3 Strategy Report",
    "source_file": "corpus/users/uid/projects/q3_strategy.pdf",
    "doc_type": "project",
    "chunk_count": 4,
    "ingested_at": "2026-08-29T13:53:27+00:00"
  }
]
```

### Other endpoints

| Method | Path | Auth required | Description |
|--------|------|:---:|-------------|
| `GET` | `/health` | No | Liveness probe — always 200 |
| `GET` | `/ready` | No | 200 if pipeline loaded, 503 otherwise |
| `GET` | `/metrics` | No | Prometheus text exposition |
| `GET` | `/docs` | No | Swagger UI (auto-generated) |

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
# All tests
pytest

# By category
pytest -m unit          # fast isolated unit tests
pytest -m integration   # full-pipeline tests (real stages, no DB needed)
pytest -m property      # Hypothesis property-based tests
pytest -m api           # FastAPI endpoint tests (includes auth)

# Auth tests specifically
pytest tests/api/test_auth.py           # 19 endpoint integration tests
pytest tests/unit/test_auth_service.py  # 16 unit tests (bcrypt, JWT, CRUD)

# With coverage
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

## Observability

Every request emits three signals:

**Structured JSON logs** (stdout):
```json
{"ts": "2026-08-29T12:00:00Z", "level": "INFO", "logger": "src.answer.pipeline",
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
├── corpus/
│   ├── companies/            # Sample TechNova Markdown documents
│   ├── projects/
│   ├── technologies/
│   ├── people/
│   └── users/                # Per-user uploads (auto-created, git-ignored)
│       └── {user_id}/
│           ├── general/
│           ├── company/
│           └── ...
├── output/
│   ├── all_chunks.json       # Global sample corpus chunks
│   ├── benchmark_report.json
│   └── users/                # Per-user chunk output (git-ignored)
│       └── {user_id}/
│           ├── all_chunks.json
│           └── documents.json
├── scripts/                  # CLI entry points
│   ├── ingest.py             # Phase 1 — chunking
│   ├── extract.py            # Phase 2 — entity extraction
│   ├── resolve.py            # Phase 3 — entity resolution
│   ├── load_graph.py         # Phase 4 — Neo4j loader
│   ├── embed_chunks.py       # Phase 5 — pgvector embedder
│   ├── ask.py                # Phase 8 — CLI Q&A
│   ├── serve.py              # Phase 9 — FastAPI server
│   └── benchmark.py          # Phase 10 — benchmarking
├── src/
│   ├── auth/                 # Phase 16 — authentication & isolation
│   │   ├── database.py       # SQLite connection (auth.db)
│   │   ├── models.py         # User ORM model
│   │   ├── schemas.py        # Pydantic request/response schemas
│   │   ├── service.py        # User CRUD + bcrypt helpers
│   │   ├── jwt_utils.py      # JWT create / decode
│   │   ├── dependencies.py   # get_current_user FastAPI dependency
│   │   └── router.py         # /auth/* endpoints
│   ├── ingestion/            # Phase 1
│   ├── extraction/           # Phase 2
│   ├── resolution/           # Phase 3
│   ├── graph/                # Phase 4
│   ├── vector/               # Phase 5
│   ├── evaluation/           # Phase 6
│   ├── router/               # Phase 7
│   ├── answer/               # Phase 8
│   ├── api/                  # Phase 9
│   │   └── routes/
│   │       ├── ask.py        # POST /ask  (auth-guarded, per-user pipeline)
│   │       ├── documents.py  # POST /documents/upload, GET /documents (auth-guarded)
│   │       ├── health.py     # GET /health, /ready
│   │       └── metrics.py    # GET /metrics
│   ├── benchmark/            # Phase 10
│   ├── observability/        # Phase 11
│   └── config.py
├── tests/
│   ├── unit/
│   │   ├── test_auth_service.py   # bcrypt, JWT, user CRUD
│   │   └── ...
│   ├── integration/
│   └── api/
│       ├── test_auth.py           # register, login, Google, /me, protected routes
│       ├── test_ask_endpoint.py   # pipeline tests (auth-aware)
│       └── ...
├── ui/
│   └── src/
│       ├── context/
│       │   └── AuthContext.jsx    # JWT storage, auto-restore on page load
│       ├── pages/
│       │   ├── LoginPage.jsx      # Email/password + Google login
│       │   └── RegisterPage.jsx   # Registration + Google login
│       ├── api/client.js          # Auth-aware fetch wrapper
│       ├── App.jsx                # Route guard, empty-corpus state
│       ├── main.jsx               # BrowserRouter + GoogleOAuthProvider + AuthProvider
│       └── components/
│           ├── QuestionForm.jsx
│           ├── AnswerCard.jsx
│           ├── CitationList.jsx
│           ├── MetaBadges.jsx
│           ├── DocumentUpload.jsx
│           └── DocumentList.jsx
├── auth.db                   # SQLite user store (git-ignored)
├── docker-compose.yml        # Neo4j + PostgreSQL
└── pyproject.toml
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
| 16 | Auth & per-user isolation | JWT + bcrypt + Google OAuth, isolated corpus per account |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini (gemini-2.5-flash) |
| Embeddings | OpenAI text-embedding-3-small |
| Knowledge graph | Neo4j 5.20 |
| Vector store | PostgreSQL 16 + pgvector |
| API | FastAPI + Uvicorn |
| Auth | python-jose (JWT) + passlib/bcrypt + SQLAlchemy + SQLite |
| UI | React 19 + Vite 8 + Tailwind CSS v4 + React Router v7 |
| Google OAuth | @react-oauth/google (frontend) + Google tokeninfo (backend) |
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
- Passwords are **bcrypt-hashed** — plaintext is never stored or logged
- JWTs are signed with a configurable `JWT_SECRET_KEY` — set a strong random value in production
- Every data endpoint is **auth-guarded** — unauthenticated requests return 401 before any pipeline code runs
- User corpora are **filesystem-isolated** by UUID — no path traversal can cross user boundaries
- The FastAPI layer validates every request with **Pydantic** — invalid inputs return 422 automatically
- CORS is restricted to `localhost:3000` and `localhost:5173` in development
- `auth.db`, `corpus/users/`, and `output/users/` are **git-ignored** — user data is never accidentally committed

---

## License

MIT
