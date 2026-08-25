#!/usr/bin/env python3
"""
CLI entry point for entity resolution.

Usage:
    # Run on real extraction output:
    python scripts/resolve.py

    # Run on the sample fixture (no API key needed):
    python scripts/resolve.py --extractions-file tests/fixtures/sample_extractions.json

    # Adjust thresholds:
    python scripts/resolve.py --auto-merge-threshold 0.90 --review-threshold 0.75
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.resolution.pipeline import run_resolution

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    extractions_file: Path = typer.Option(
        Path("output/extractions.json"),
        "--extractions-file",
        help="Path to the extractions.json produced by Phase 2.",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        show_default=True,
    ),
    auto_merge_threshold: float = typer.Option(
        0.95,
        "--auto-merge-threshold",
        help="Similarity ≥ this → auto-merge two entity names.",
        show_default=True,
    ),
    review_threshold: float = typer.Option(
        0.82,
        "--review-threshold",
        help="Similarity ≥ this (but < auto) → flag for human review.",
        show_default=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Resolve entity names to canonical forms and deduplicate relationships."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-35s  %(levelname)-8s  %(message)s",
    )
    run_resolution(
        extractions_file=extractions_file,
        output_dir=output_dir,
        auto_merge_threshold=auto_merge_threshold,
        review_threshold=review_threshold,
    )


if __name__ == "__main__":
    app()
