#!/usr/bin/env python3
"""
CLI entry point for the document ingestion pipeline.

Usage:
    python scripts/ingest.py
    python scripts/ingest.py --corpus-dir corpus/ --output-dir output/
    python scripts/ingest.py --force        # Re-ingest even if unchanged
    python scripts/ingest.py --verbose      # Show debug logs
"""
import logging
import sys
from pathlib import Path

# Add project root to path so `src` is importable without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.ingestion.pipeline import run_ingestion

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    corpus_dir: Path = typer.Option(
        Path("corpus"),
        "--corpus-dir",
        help="Directory containing source documents.",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        help="Directory for chunk JSON output.",
        show_default=True,
    ),
    chunk_size: int = typer.Option(
        500,
        "--chunk-size",
        help="Target chunk size in tokens.",
        show_default=True,
    ),
    chunk_overlap: int = typer.Option(
        100,
        "--chunk-overlap",
        help="Token overlap between adjacent chunks.",
        show_default=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest documents that were already processed.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable DEBUG-level logging.",
    ),
) -> None:
    """Ingest documents from the corpus and produce chunked JSON output."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-30s  %(levelname)-8s  %(message)s",
    )

    stats = run_ingestion(
        corpus_dir=corpus_dir,
        output_dir=output_dir,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        force=force,
    )

    if stats["documents_processed"] == 0:
        raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
