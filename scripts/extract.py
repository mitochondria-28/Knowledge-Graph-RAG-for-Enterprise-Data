#!/usr/bin/env python3
"""
CLI entry point for the entity & relationship extraction pipeline.

Usage:
    # Estimate cost first (no API calls):
    python scripts/extract.py --dry-run

    # Extract a sample of 3 chunks to verify quality before full run:
    python scripts/extract.py --sample 3

    # Full extraction:
    python scripts/extract.py

    # Re-extract everything (ignore cache):
    python scripts/extract.py --force

    # Use a different model:
    python scripts/extract.py --model claude-sonnet-4-6
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.extraction.extractor import DEFAULT_MODEL
from src.extraction.pipeline import run_extraction

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    chunks_file: Path = typer.Option(
        Path("output/all_chunks.json"),
        "--chunks-file",
        help="Path to the all_chunks.json produced by the ingestion pipeline.",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        show_default=True,
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        help="Claude model ID to use for extraction.",
        show_default=True,
    ),
    sample: int = typer.Option(
        0,
        "--sample",
        help="Only extract this many chunks (0 = all). Use to test quality before full run.",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Estimate cost and print plan — no API calls.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-extract even if chunk is already in cache.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable DEBUG logging.",
    ),
) -> None:
    """Extract entities and relationships from document chunks using Claude."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-35s  %(levelname)-8s  %(message)s",
    )

    run_extraction(
        chunks_file=chunks_file,
        output_dir=output_dir,
        model=model,
        sample=sample or None,
        dry_run=dry_run,
        force=force,
    )


if __name__ == "__main__":
    app()
