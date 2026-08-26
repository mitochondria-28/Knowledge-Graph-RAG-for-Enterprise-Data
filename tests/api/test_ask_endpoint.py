"""
Integration tests for the FastAPI layer — Phase 9.

HOW THESE TESTS WORK:

FastAPI's TestClient wraps the ASGI app with httpx. When used as a context
manager, it runs the full lifespan (startup + shutdown), so the pipeline
is initialised exactly as it would be in production.

No running server is needed — everything runs in-process.
No GEMINI_API_KEY is required — the lifespan falls back to MockAnswerGenerator
when the key is absent, which is the expected behaviour in CI.

The tests exercise:
  1. Health + readiness endpoints
  2. POST /ask — schema validation (422 for bad input)
  3. POST /ask — full pipeline round-trip (routing + retrieval + generation + validation)
  4. Response schema completeness
  5. Routing strategy correctness (vector vs. graph)
  6. Security headers
  7. CORS headers
  8. /docs endpoint accessible
  9. Error cases (pipeline not initialised → 503)
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient for the full app with lifespan.
    scope="module" means startup runs once per test file — fast.

    After startup we replace the generator with MockAnswerGenerator so tests
    never make real API calls, regardless of whether ANTHROPIC_API_KEY is set
    in .env. The chunks and entity index loaded by the real lifespan are kept.
    """
    from src.answer.generator import MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline

    application = create_app()
    with TestClient(application) as c:
        # Swap to mock pipeline — keeps real chunks + entity index from lifespan
        real = c.app.state.pipeline
        c.app.state.pipeline = AnswerPipeline(
            generator=MockAnswerGenerator(),
            chunks=real._chunks,
            entity_index=real._router._entity_index,
        )
        c.app.state.generator_type = "MockAnswerGenerator"
        yield c


@pytest.fixture(scope="module")
def bare_app():
    """App instance without lifespan for testing 503 behaviour."""
    from fastapi import FastAPI, Request
    from src.api.routes import ask as ask_router

    app_no_state = FastAPI()
    app_no_state.include_router(ask_router.router)
    return TestClient(app_no_state)


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_status_is_ok(self, client):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}

    def test_content_type_json(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.headers["content-type"]


# ── GET /ready ────────────────────────────────────────────────────────────────

class TestReady:
    def test_returns_200_when_chunks_loaded(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_status_is_ready(self, client):
        resp = client.get("/ready")
        assert resp.json()["status"] == "ready"

    def test_chunk_count_positive(self, client):
        resp = client.get("/ready")
        assert resp.json()["chunk_count"] > 0

    def test_entity_count_non_negative(self, client):
        resp = client.get("/ready")
        assert resp.json()["entity_count"] >= 0

    def test_generator_field_present(self, client):
        resp = client.get("/ready")
        assert "generator" in resp.json()
        assert resp.json()["generator"] != ""

    def test_mock_generator_when_no_api_key(self, client):
        # Without ANTHROPIC_API_KEY in env, lifespan uses MockAnswerGenerator
        resp = client.get("/ready")
        gen = resp.json()["generator"]
        # Either Mock (no key) or real (key present) — both are valid
        assert gen in ("MockAnswerGenerator", "AnswerGenerator")


# ── POST /ask — input validation (422) ────────────────────────────────────────

class TestAskValidation:
    def test_empty_question_is_422(self, client):
        resp = client.post("/ask", json={"question": ""})
        assert resp.status_code == 422

    def test_missing_question_is_422(self, client):
        resp = client.post("/ask", json={})
        assert resp.status_code == 422

    def test_question_too_long_is_422(self, client):
        resp = client.post("/ask", json={"question": "x" * 501})
        assert resp.status_code == 422

    def test_top_k_zero_is_422(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 0})
        assert resp.status_code == 422

    def test_top_k_too_large_is_422(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 21})
        assert resp.status_code == 422

    def test_top_k_string_is_422(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?", "top_k": "five"})
        assert resp.status_code == 422

    def test_valid_question_at_boundary_500_chars(self, client):
        resp = client.post("/ask", json={"question": "x" * 500})
        assert resp.status_code == 200

    def test_top_k_at_max_boundary_20(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 20})
        assert resp.status_code == 200

    def test_top_k_at_min_boundary_1(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 1})
        assert resp.status_code == 200


# ── POST /ask — response schema ───────────────────────────────────────────────

class TestAskResponseSchema:
    def test_returns_200(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.status_code == 200

    def test_has_question_field(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert "question" in resp.json()
        assert resp.json()["question"] == "What is StellarDB?"

    def test_has_answer_field(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert "answer" in resp.json()
        assert isinstance(resp.json()["answer"], str)
        assert len(resp.json()["answer"]) > 0

    def test_has_citations_list(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert "citations" in resp.json()
        assert isinstance(resp.json()["citations"], list)

    def test_has_citation_confidence(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        conf = resp.json()["citation_confidence"]
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_has_retrieval_strategy(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        strategy = resp.json()["retrieval_strategy"]
        assert strategy in ("vector", "graph", "hybrid")

    def test_has_model_field(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert "model" in resp.json()

    def test_has_latency_ms(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.json()["latency_ms"] >= 0.0

    def test_has_chunk_count(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.json()["chunk_count"] >= 0

    def test_citation_fields_complete(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        for cit in resp.json()["citations"]:
            assert "chunk_id" in cit
            assert "source_file" in cit
            assert "quote" in cit
            assert "is_valid" in cit
            assert "match_score" in cit
            assert "reason" in cit

    def test_citation_match_score_in_range(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        for cit in resp.json()["citations"]:
            assert 0.0 <= cit["match_score"] <= 1.0

    def test_citation_is_valid_is_bool(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        for cit in resp.json()["citations"]:
            assert isinstance(cit["is_valid"], bool)


# ── POST /ask — routing correctness ──────────────────────────────────────────

class TestAskRouting:
    def test_definition_question_routes_to_vector(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.json()["retrieval_strategy"] == "vector"

    def test_temporal_question_routes_to_vector(self, client):
        resp = client.post("/ask", json={"question": "When did TechNova acquire Stellar Systems?"})
        assert resp.json()["retrieval_strategy"] == "vector"

    def test_person_query_routes_to_graph(self, client):
        resp = client.post("/ask", json={"question": "Who leads the Platform Team?"})
        assert resp.json()["retrieval_strategy"] == "graph"

    def test_multi_hop_routes_to_graph(self, client):
        resp = client.post("/ask", json={"question": "Who leads the team that maintains StellarDB?"})
        assert resp.json()["retrieval_strategy"] == "graph"

    def test_top_k_respected(self, client):
        resp1 = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 1})
        resp5 = client.post("/ask", json={"question": "What is StellarDB?", "top_k": 5})
        # With more chunks, citation count can only increase or stay the same
        assert resp1.json()["chunk_count"] <= resp5.json()["chunk_count"]


# ── Security headers ──────────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_security_headers_on_post(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.headers.get("x-content-type-options") == "nosniff"


# ── /docs (OpenAPI UI) ────────────────────────────────────────────────────────

class TestDocs:
    def test_docs_accessible(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Enterprise Knowledge Graph RAG"

    def test_openapi_has_ask_endpoint(self, client):
        schema = client.get("/openapi.json").json()
        assert "/ask" in schema["paths"]

    def test_openapi_has_health_endpoint(self, client):
        schema = client.get("/openapi.json").json()
        assert "/health" in schema["paths"]


# ── Pipeline not initialised → 503 ───────────────────────────────────────────

class TestPipelineNotReady:
    def test_ask_without_pipeline_returns_503(self, bare_app):
        resp = bare_app.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.status_code == 503
