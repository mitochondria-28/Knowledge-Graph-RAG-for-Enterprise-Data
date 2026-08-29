"""Database engine — SQLite for local dev, PostgreSQL on Vercel/production."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _build_engine():
    url = os.environ.get("DATABASE_URL", "")
    if url:
        # Neon/Heroku/Vercel sometimes emit postgres:// which SQLAlchemy 2 rejects
        url = url.replace("postgres://", "postgresql://", 1)
        return create_engine(url, pool_pre_ping=True)

    # SQLite: prefer project root, fall back to /tmp when filesystem is read-only
    # (e.g. Vercel serverless without DATABASE_URL set — ephemeral but writable)
    project_db = Path(__file__).resolve().parent.parent.parent / "auth.db"
    try:
        project_db.touch(exist_ok=True)
        db_path = project_db
    except (OSError, PermissionError):
        db_path = Path("/tmp/auth.db")

    return create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from src.auth import models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)
