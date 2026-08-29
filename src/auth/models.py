"""SQLAlchemy ORM models — users and their per-user corpus state."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.auth.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)
    google_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserCorpus(Base):
    """Persists per-user chunks + entity index in the DB.

    This is the source of truth on serverless deployments where the filesystem
    is ephemeral.  On local dev the same table lives in SQLite.
    """

    __tablename__ = "user_corpus"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    chunks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entity_index: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
