"""Unit tests for auth service and JWT utilities."""

import pytest
from jose import JWTError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.database import Base
from src.auth.jwt_utils import create_access_token, decode_token
from src.auth.service import (
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    verify_password,
)


# ── In-memory SQLite for unit tests ──────────────────────────────────────────

@pytest.fixture
def db():
    from src.auth import models  # noqa: F401
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Password helpers ──────────────────────────────────────────────────────────

class TestPasswordHelpers:
    def test_hash_and_verify(self):
        h = hash_password("MySecret123!")
        assert verify_password("MySecret123!", h)

    def test_wrong_password_fails(self):
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_hash_is_bcrypt(self):
        h = hash_password("x")
        assert h.startswith("$2b$")


# ── User CRUD ─────────────────────────────────────────────────────────────────

class TestUserCRUD:
    def test_create_and_fetch_by_email(self, db):
        user = create_user(db, email="alice@corp.com", password="pass1234", name="Alice")
        assert user.id is not None
        found = get_user_by_email(db, "alice@corp.com")
        assert found is not None
        assert found.email == "alice@corp.com"

    def test_get_user_by_id(self, db):
        user = create_user(db, email="bob@corp.com", password="pass5678")
        found = get_user_by_id(db, user.id)
        assert found.email == "bob@corp.com"

    def test_unknown_email_returns_none(self, db):
        assert get_user_by_email(db, "nobody@example.com") is None

    def test_unknown_id_returns_none(self, db):
        assert get_user_by_id(db, "00000000-0000-0000-0000-000000000000") is None

    def test_authenticate_correct(self, db):
        create_user(db, email="carol@corp.com", password="GoodPass1!")
        user = authenticate_user(db, "carol@corp.com", "GoodPass1!")
        assert user is not None
        assert user.email == "carol@corp.com"

    def test_authenticate_wrong_password(self, db):
        create_user(db, email="dave@corp.com", password="GoodPass1!")
        assert authenticate_user(db, "dave@corp.com", "WrongPass!") is None

    def test_authenticate_unknown_user(self, db):
        assert authenticate_user(db, "ghost@corp.com", "AnyPass1!") is None

    def test_password_not_stored_in_plaintext(self, db):
        user = create_user(db, email="eve@corp.com", password="Pl@inText1")
        assert user.hashed_password != "Pl@inText1"


# ── JWT utils ─────────────────────────────────────────────────────────────────

class TestJWTUtils:
    def test_roundtrip(self):
        user_id = "test-user-id-123"
        token = create_access_token(user_id)
        assert decode_token(token) == user_id

    def test_invalid_token_raises(self):
        with pytest.raises(JWTError):
            decode_token("not.a.valid.jwt")

    def test_tampered_token_raises(self):
        token = create_access_token("some-user")
        tampered = token[:-4] + "xxxx"
        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_token_is_string(self):
        token = create_access_token("uid")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_different_users_get_different_tokens(self):
        t1 = create_access_token("user-a")
        t2 = create_access_token("user-b")
        assert t1 != t2
