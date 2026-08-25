#!/usr/bin/env python3
"""
CLI entry point for chunk embedding (Phase 5).

Usage:
    # Dry run — estimate cost, no API calls:
    python scripts/embed_chunks.py --dry-run

    # Mock embeddings (random unit vectors, no API key needed):
    python scripts/embed_chunks.py --mock-embeddings

    # Embed a small sample first to verify the pipeline:
    python scripts/embed_chunks.py --sample 5 --mock-embeddings

    # Real embeddings (requires OPENAI_API_KEY in .env):
    python scripts/embed_chunks.py

    # Re-embed everything with a different model:
    python scripts/embed_chunks.py --force --model text-embedding-3-large

    # Verbose logging:
    python scripts/embed_chunks.py --mock-embeddings --verbose
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.vector.pipeline import run_embedding

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    chunks_file: Path = typer.Option(
        Path("output/all_chunks.json"),
        "--chunks-file",
        help="Path to all_chunks.json (Phase 1 output).",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        show_default=True,
    ),
    model: str = typer.Option(
        "text-embedding-3-small",
        "--model",
        help="OpenAI embedding model.",
        show_default=True,
    ),
    batch_size: int = typer.Option(
        256,
        "--batch-size",
        help="Chunks per API call.",
        show_default=True,
    ),
    sample: int = typer.Option(
        0,
        "--sample",
        help="Only embed this many chunks (0 = all).",
        show_default=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-embed all chunks, even already-embedded ones.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Estimate cost without calling the API or writing to DB.",
    ),
    mock_embeddings: bool = typer.Option(
        False,
        "--mock-embeddings",
        help="Use random unit vectors instead of real embeddings (no API key needed).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Embed document chunks and store them in pgvector."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-35s  %(levelname)-8s  %(message)s",
    )
    try:
        run_embedding(
            chunks_file=chunks_file,
            output_dir=output_dir,
            model=model,
            batch_size=batch_size,
            sample=sample,
            force=force,
            dry_run=dry_run,
            mock_embeddings=mock_embeddings,
        )
    except FileNotFoundError as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except RuntimeError as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
