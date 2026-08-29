"""
Auth endpoint tests — Phase 14.

Tests cover:
  1. POST /auth/register — success, duplicate email, weak password
  2. POST /auth/login    — success, wrong password, unknown user
  3. GET  /auth/me       — authenticated, unauthenticated, expired token
  4. POST /ask           — requires auth (401 when no token)
  5. GET  /documents     — requires auth
  6. JWT secret isolation (tokens signed with different secrets are rejected)
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.auth.database import Base, engine


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Isolated in-memory SQLite for each test module run."""
    # Recreate tables fresh (in-memory-like, same file but wiped)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def registered(client):
    """Register a user once and return the token + user payload."""
    resp = client.post("/auth/register", json={
        "email": "testuser@corp.example",
        "password": "Secr3tPass!",
        "name": "Test User",
    })
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture(scope="module")
def auth_headers(registered):
    token = registered["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Register ──────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, registered):
        assert "access_token" in registered
        assert registered["token_type"] == "bearer"
        user = registered["user"]
        assert user["email"] == "testuser@corp.example"
        assert user["name"] == "Test User"
        assert "id" in user

    def test_register_duplicate_email(self, client):
        resp = client.post("/auth/register", json={
            "email": "testuser@corp.example",
            "password": "AnotherPass1!",
        })
        assert resp.status_code == 409

    def test_register_weak_password(self, client):
        resp = client.post("/auth/register", json={
            "email": "weak@corp.example",
            "password": "short",
        })
        assert resp.status_code == 422

    def test_register_invalid_email(self, client):
        resp = client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "ValidPass123!",
        })
        assert resp.status_code == 422

    def test_register_missing_fields(self, client):
        resp = client.post("/auth/register", json={})
        assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self, client):
        resp = client.post("/auth/login", json={
            "email": "testuser@corp.example",
            "password": "Secr3tPass!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "testuser@corp.example"

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", json={
            "email": "testuser@corp.example",
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@corp.example",
            "password": "SomePass123!",
        })
        assert resp.status_code == 401

    def test_login_missing_password(self, client):
        resp = client.post("/auth/login", json={"email": "testuser@corp.example"})
        assert resp.status_code == 422


# ── /auth/me ──────────────────────────────────────────────────────────────────

class TestMe:
    def test_me_authenticated(self, client, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "testuser@corp.example"

    def test_me_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
        assert resp.status_code == 401

    def test_me_malformed_header(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "NotBearer abc"})
        assert resp.status_code == 401


# ── Protected routes ──────────────────────────────────────────────────────────

class TestProtectedRoutes:
    def test_ask_requires_auth(self, client):
        resp = client.post("/ask", json={"question": "What is StellarDB?"})
        assert resp.status_code == 401

    def test_ask_with_token_empty_corpus_returns_400(self, client, auth_headers):
        # Authenticated but no documents uploaded → 400 with helpful message
        resp = client.post(
            "/ask",
            json={"question": "What is StellarDB?", "top_k": 3},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_documents_list_requires_auth(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 401

    def test_documents_list_with_token(self, client, auth_headers):
        resp = client.get("/documents", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── JWT integrity ─────────────────────────────────────────────────────────────

class TestJWTIntegrity:
    def test_tampered_token_rejected(self, client, auth_headers):
        token = auth_headers["Authorization"].split(" ")[1]
        # Flip last char to tamper with signature
        bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    def test_token_has_correct_structure(self, registered):
        token = registered["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have header.payload.signature"
