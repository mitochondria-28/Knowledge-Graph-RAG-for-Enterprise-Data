"""
Vector embedding pipeline orchestrator.

MODES:
  1. Real embeddings  — requires OPENAI_API_KEY; calls the embeddings API
  2. Mock embeddings  — random unit vectors; no API key; for dev / CI
  3. Dry run          — estimates cost, no API calls, no DB writes

IDEMPOTENCY:

  Already-embedded chunks are skipped by default. The pipeline fetches the
  set of chunk_ids that have embedded_at IS NOT NULL and skips those.
  Use --force to re-embed everything (e.g. after upgrading the embedding model).

PROGRESS TRACKING:

  Embedding is the slow step (API call per batch). Progress is shown via
  Rich's track() so the user sees batches completing in real time.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.progress import track
from rich.table import Table

from src.config import settings
from src.vector.connection import get_connection
from src.vector.embedder import (
    DEFAULT_MODEL,
    CostEstimate,
    embed_texts,
    estimate_cost,
    mock_embed_texts,
)
from src.vector.schema import create_schema, drop_chunks_table, get_embedded_chunk_ids
from src.vector.store import count_chunks, upsert_chunks

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class EmbedResult:
    chunks_total: int = 0
    chunks_skipped: int = 0
    chunks_embedded: int = 0
    model: str = DEFAULT_MODEL
    cost_estimate: CostEstimate | None = None
    elapsed_seconds: float = 0.0
    dry_run: bool = False
    mock: bool = False


def _load_chunks(chunks_file: Path) -> list[dict]:
    if not chunks_file.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_file}\n"
            "Run `python scripts/ingest.py` first to generate chunk output."
        )
    return json.loads(chunks_file.read_text(encoding="utf-8"))


def run_embedding(
    chunks_file: Path | None = None,
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
    batch_size: int = 256,
    sample: int = 0,
    force: bool = False,
    dry_run: bool = False,
    mock_embeddings: bool = False,
) -> EmbedResult:
    """
    Embed document chunks and store them in pgvector.

    Args:
        chunks_file:       Path to all_chunks.json from Phase 1.
        output_dir:        Fallback directory for default paths.
        model:             OpenAI embedding model name.
        batch_size:        Chunks per API call (max 256).
        sample:            If > 0, only embed this many chunks (for testing).
        force:             Re-embed all chunks, including already-embedded ones.
        dry_run:           Estimate cost; do not call API or write to DB.
        mock_embeddings:   Use random unit vectors instead of real embeddings.

    Returns:
        EmbedResult with counts, cost estimate, and timing.
    """
    output_dir = output_dir or settings.output_dir
    chunks_file = chunks_file or (output_dir / "all_chunks.json")

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Vector Embedder (Phase 5) ━━━[/bold cyan]")
    console.print(f"  Chunks file : [yellow]{chunks_file}[/yellow]")
    console.print(f"  Model       : [yellow]{model}[/yellow]")
    if mock_embeddings:
        console.print("  [yellow]MOCK MODE — random unit vectors (no API key needed)[/yellow]")
    if dry_run:
        console.print("  [yellow]DRY RUN — will not write to database[/yellow]")

    all_chunks = _load_chunks(chunks_file)
    console.print(f"\n  Loaded [bold]{len(all_chunks)}[/bold] chunks from {chunks_file.name}")

    result = EmbedResult(chunks_total=len(all_chunks), model=model,
                         dry_run=dry_run, mock=mock_embeddings)

    # Apply sample limit
    if sample > 0:
        all_chunks = all_chunks[:sample]
        console.print(f"  Sample limit: [yellow]{sample}[/yellow] chunks")

    # Determine which chunks need embedding
    chunks_to_embed = all_chunks
    if not force and not dry_run:
        with get_connection() as conn:
            already_done = get_embedded_chunk_ids(conn)
        chunks_to_embed = [c for c in all_chunks if c["chunk_id"] not in already_done]
        result.chunks_skipped = len(all_chunks) - len(chunks_to_embed)
        if result.chunks_skipped:
            console.print(
                f"  Skipping [green]{result.chunks_skipped}[/green] already-embedded chunks "
                f"(use [yellow]--force[/yellow] to re-embed)"
            )

    if not chunks_to_embed:
        console.print("\n  [green]All chunks already embedded — nothing to do.[/green]")
        return result

    # Cost estimate (always shown, even in real mode)
    cost = estimate_cost(chunks_to_embed, model)
    result.cost_estimate = cost
    console.print(f"\n  Embedding estimate: [bold]{cost}[/bold]")

    if dry_run:
        result.chunks_embedded = len(chunks_to_embed)
        return result

    # Set up database schema
    with get_connection() as conn:
        if force:
            console.print("  [yellow]--force: dropping and recreating chunks table…[/yellow]")
            drop_chunks_table(conn)
        create_schema(conn)

    # Build the embedding source
    if mock_embeddings:
        _embed_fn = lambda texts: mock_embed_texts(texts, seed=42)
        console.print(f"\n  Generating [bold]{len(chunks_to_embed)}[/bold] mock embeddings…")
    else:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai not installed. Run: pip install openai>=1.40"
            ) from exc

        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Either:\n"
                "  1. Add it to .env\n"
                "  2. Use --mock-embeddings for development without an API key"
            )

        client = OpenAI(api_key=settings.openai_api_key)
        _embed_fn = lambda texts: embed_texts(client, texts, model=model, batch_size=batch_size)
        console.print(f"\n  Embedding [bold]{len(chunks_to_embed)}[/bold] chunks via OpenAI…")

    # Embed in batches with progress bar
    start = time.perf_counter()
    all_embeddings: list[list[float]] = []

    batches = [
        chunks_to_embed[i : i + batch_size]
        for i in range(0, len(chunks_to_embed), batch_size)
    ]

    for batch in track(batches, description="  Embedding", console=console):
        texts = [c["content"] for c in batch]
        batch_embeddings = _embed_fn(texts)
        all_embeddings.extend(batch_embeddings)

    # Store in pgvector
    with get_connection() as conn:
        upserted = upsert_chunks(conn, chunks_to_embed, all_embeddings, model)
        counts = count_chunks(conn)

    elapsed = time.perf_counter() - start
    result.chunks_embedded = upserted
    result.elapsed_seconds = elapsed

    # Summary
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Chunks embedded", str(upserted))
    table.add_row("Total in DB", str(counts["total"]))
    table.add_row("All embedded", str(counts["embedded"]))
    table.add_row("Elapsed", f"{elapsed:.1f}s")

    console.print()
    console.print(table)
    console.print(f"\n  [bold green]✓ Done[/bold green]")

    return result
