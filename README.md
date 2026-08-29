# Enterprise Knowledge Graph RAG

A production-quality Retrieval-Augmented Generation system that combines **vector similarity search** with **multi-hop knowledge graph traversal** to answer complex enterprise questions — with every citation verified against its source document.

Built phase-by-phase as a portfolio project demonstrating the full engineering stack: ingestion → knowledge graph → hybrid retrieval → LLM generation → citation validation → FastAPI backend → observability → testing → React UI → per-user authentication → **Vercel production deployment**.

> **Live demo → [https://enterprise-kg-rag.vercel.app](https://enterprise-kg-rag.vercel.app)**
> Register a free account, upload any `.pdf`, `.md`, or `.txt` file, and ask questions about it. Your documents are private and isolated from every other user.

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

## Quick start (local dev)

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
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — minimum required for local dev:
```

```env
# Auth (required)
JWT_SECRET_KEY=any-random-string-for-local-dev

# LLM (optional — MockAnswerGenerator used if absent)
GEMINI_API_KEY=AIza...

# Google OAuth (optional — enables Sign in with Google button)
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

### 3. Start the API server

```bash
python scripts/serve.py --reload     # FastAPI on http://localhost:8000
# Interactive API docs: http://localhost:8000/docs
```

### 4. Start the UI

```bash
cd ui && npm install && npm run dev
# Open http://localhost:5173
```

Register an account (or sign in with Google), upload your documents, and start asking questions.

### 5. Ingest the demo corpus (optional)

```bash
python scripts/ingest.py        # chunks 13 sample docs → output/all_chunks.json
```

> Documents uploaded through the UI are ingested automatically per-user — no CLI step needed.

---

## Deploy to Vercel

The project is pre-configured for Vercel: `vercel.json` routes API paths to a Python serverless function (`api/index.py`) and the React frontend is served as a static build.

### What you need

| Requirement | Free option |
|-------------|-------------|
| PostgreSQL database | [Neon](https://neon.tech) free tier |
| Google Gemini API key | [Google AI Studio](https://aistudio.google.com) |
| Google OAuth client | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| Vercel account | [vercel.com](https://vercel.com) |

### 1. Fork / clone and install the Vercel CLI

```bash
npm i -g vercel
vercel login
```

### 2. Link the project

```bash
vercel link
```

### 3. Set environment variables in the Vercel dashboard

Go to **Project → Settings → Environment Variables** and add:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (Neon) | `postgresql://user:pass@host/db?sslmode=require` |
| `JWT_SECRET_KEY` | Random secret for JWT signing | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | Gemini API key for real LLM answers | `AIza...` |
| `TEMP_DIR` | Writable temp dir for uploads | `/tmp` |

> **Note:** `VITE_GOOGLE_CLIENT_ID` is already embedded in the frontend bundle (`ui/src/main.jsx`). Update that constant if you rotate your OAuth credential.

### 4. Add your Vercel domain to Google OAuth

In **Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs**:
- Add `https://your-project.vercel.app` to **Authorised JavaScript origins**

### 5. Deploy

```bash
vercel deploy --prod
```

Or push any commit to `main` — Vercel auto-deploys from GitHub.

### Architecture on Vercel

```
Browser
  │
  ├─ /auth/* /ask /documents/* /health /ready
  │   └─► Python serverless function  (api/index.py → FastAPI)
  │        └─► PostgreSQL (Neon)  — users + per-user chunks
  │
  └─ /* (everything else)
      └─► Static React build  (ui/dist/index.html)
```

**Persistence on serverless:** after each document upload, chunks and the document list are persisted to the `user_corpus` PostgreSQL table so they survive cold starts. The pipeline is rebuilt from the DB on the first request after a cold start.

---

## Authentication & per-user knowledge bases

Every account gets a completely private, isolated knowledge base. No user can see or query another user's documents.

### How it works

| What | Local dev | Production (Vercel) |
|------|-----------|---------------------|
| User accounts | SQLite (`auth.db`) | PostgreSQL (`DATABASE_URL`) |
| Passwords | bcrypt-hashed — never stored in plaintext | same |
| Sessions | JWT Bearer tokens (7-day expiry, HS256) | same |
| Google login | ID token verified via Google's tokeninfo endpoint | same |
| User documents | `corpus/users/{user_id}/` | `/tmp/corpus/users/{user_id}/` |
| User chunks | `output/users/{user_id}/` (files + DB) | `user_corpus` table (DB only) |
| User pipeline | `app.state.user_pipelines[user_id]` — lazy-built, memory-cached | rebuilt from DB on cold start |

### Auth endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Create account — returns JWT + user |
| `POST` | `/auth/login` | Email + password — returns JWT + user |
| `POST` | `/auth/google` | Google ID token — returns JWT + user |
| `GET` | `/auth/me` | Returns the current user's profile |

All data endpoints (`/ask`, `/documents/upload`, `/documents`) require `Authorization: Bearer <token>` and operate exclusively on the authenticated user's data.

### Register (email/password)

```bash
curl -X POST https://enterprise-kg-rag.vercel.app/auth/register \
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

### Isolation guarantee

```
User A uploads report.pdf  →  stored in user_corpus (DB) under uid-A
User A asks a question      →  answers only from uid-A's chunks
User B asks the same        →  400 "Your knowledge base is empty"
                               (until B uploads their own documents)
```

---

## API reference

All data endpoints require: `Authorization: Bearer <your_token>`

Base URL (production): `https://enterprise-kg-rag.vercel.app`

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
curl -X POST https://enterprise-kg-rag.vercel.app/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@my_report.pdf" \
  -F "doc_type=project"   # general | company | project | technology | people
```

```json
{
  "filename": "my_report.pdf",
  "doc_type": "project",
  "stats": { "documents_processed": 1, "chunks_created": 4 }
}
```

Supported formats: `.md`, `.txt`, `.pdf` · Max size: 10 MB

### `GET /documents`

List documents uploaded by the current user only.

```json
[
  {
    "filename": "q3_strategy.pdf",
    "doc_type": "project",
    "uploaded_at": "2026-08-29T13:53:27",
    "size_bytes": 204800
  }
]
```

### Other endpoints

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/health` | No | Liveness probe — always `{"status":"ok"}` |
| `GET` | `/ready` | No | 200 + chunk count when pipeline is loaded |
| `GET` | `/metrics` | No | Prometheus text exposition |
| `GET` | `/docs` | No | Swagger UI |

---

## Running the full stack with databases (local)

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
├── api/
│   └── index.py              # Vercel Python serverless entry point (ASGI)
├── corpus/
│   ├── companies/            # Sample TechNova Markdown documents
│   ├── projects/
│   ├── technologies/
│   ├── people/
│   └── users/                # Per-user uploads (auto-created, git-ignored)
├── output/
│   ├── all_chunks.json       # Global sample corpus chunks (committed)
│   ├── benchmark_report.json
│   └── users/                # Per-user chunk output (git-ignored)
├── scripts/                  # CLI entry points
│   ├── ingest.py
│   ├── extract.py
│   ├── resolve.py
│   ├── load_graph.py
│   ├── embed_chunks.py
│   ├── ask.py
│   ├── serve.py
│   └── benchmark.py
├── src/
│   ├── auth/                 # Phase 16 — authentication & isolation
│   │   ├── database.py       # SQLite (local) or PostgreSQL (production) engine
│   │   ├── models.py         # User + UserCorpus ORM models
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
│   │       ├── documents.py  # POST /documents/upload, GET /documents
│   │       ├── health.py     # GET /health, /ready
│   │       └── metrics.py    # GET /metrics
│   ├── benchmark/            # Phase 10
│   ├── observability/        # Phase 11
│   └── config.py
├── tests/
│   ├── unit/
│   │   ├── test_auth_service.py   # bcrypt, JWT, user CRUD
│   │   └── ...
│   └── api/
│       ├── test_auth.py           # register, login, Google, /me, protected routes
│       ├── test_ask_endpoint.py   # pipeline tests (auth-aware)
│       └── ...
├── ui/
│   ├── .env.production        # Vite build-time env (Google Client ID — public)
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
├── vercel.json                # Vercel routing: API → Python fn, UI → static build
├── requirements.txt           # Python runtime deps (mirrors pyproject.toml)
├── pyproject.toml
├── .env.example               # All configurable env vars with descriptions
└── docker-compose.yml         # Neo4j + PostgreSQL for local full-stack dev
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
| 17 | Vercel deployment | Python serverless + static React, PostgreSQL persistence |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Hosting | Vercel (Python serverless + static frontend) |
| LLM | Google Gemini (gemini-2.5-flash) |
| Embeddings | OpenAI text-embedding-3-small |
| Knowledge graph | Neo4j 5.20 |
| Vector store | PostgreSQL 16 + pgvector |
| API | FastAPI + Uvicorn |
| Auth | python-jose (JWT) + passlib/bcrypt + SQLAlchemy |
| Database | SQLite (local dev) / PostgreSQL via `DATABASE_URL` (production) |
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
- Passwords are **bcrypt-hashed** — plaintext is never stored or logged
- JWTs are signed with `JWT_SECRET_KEY` — set a strong random value in production (`secrets.token_hex(32)`)
- Every data endpoint is **auth-guarded** — unauthenticated requests return 401 before any pipeline code runs
- User corpora are **isolated by UUID** — no path traversal can cross user boundaries
- `auth.db`, `corpus/users/`, and `output/users/` are **git-ignored** — user data is never accidentally committed
- The Google OAuth client ID is public by design and scoped to **Authorised JavaScript origins** in Google Cloud Console

---

## License

MIT
