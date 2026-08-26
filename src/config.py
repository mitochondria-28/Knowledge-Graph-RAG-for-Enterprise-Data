from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Paths ────────────────────────────────────────────────────
    corpus_dir: Path = Path("corpus")
    output_dir: Path = Path("output")

    # ── Chunking ─────────────────────────────────────────────────
    chunk_size: int = 500        # target chunk size in tokens
    chunk_overlap: int = 100     # token overlap between consecutive chunks

    # ── LLM ──────────────────────────────────────────────────────
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # ── Neo4j (Phase 4+) ─────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ── PostgreSQL (Phase 5+) ────────────────────────────────────
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/kg_rag"

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = "INFO"


settings = Settings()
