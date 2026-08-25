#!/usr/bin/env python3
"""
CLI entry point for retrieval evaluation (Phase 6).

Usage:
    # Keyword baseline only (no databases needed):
    python scripts/evaluate_retrieval.py

    # Add vector retrieval (requires PostgreSQL + embeddings):
    python scripts/evaluate_retrieval.py --vector

    # Add graph retrieval (requires Neo4j + entities):
    python scripts/evaluate_retrieval.py --graph

    # Full three-way comparison:
    python scripts/evaluate_retrieval.py --vector --graph

    # Change k and hop depth:
    python scripts/evaluate_retrieval.py --vector --graph --k 10 --hop-depth 3

    # Verbose (shows per-question debug logs):
    python scripts/evaluate_retrieval.py --verbose
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.evaluation.pipeline import run_evaluation

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
    k: int = typer.Option(
        5,
        "--k",
        help="Number of chunks to retrieve per question.",
        show_default=True,
    ),
    vector: bool = typer.Option(
        False,
        "--vector",
        help="Include VectorRetriever (requires PostgreSQL + chunk embeddings).",
    ),
    graph: bool = typer.Option(
        False,
        "--graph",
        help="Include GraphRetriever (requires Neo4j + loaded entities).",
    ),
    hop_depth: int = typer.Option(
        2,
        "--hop-depth",
        help="Graph traversal depth (1, 2, or 3).",
        show_default=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Evaluate retrieval quality across keyword, vector, and graph retrievers."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
    )
    try:
        run_evaluation(
            chunks_file=chunks_file,
            output_dir=output_dir,
            k=k,
            include_vector=vector,
            include_graph=graph,
            hop_depth=hop_depth,
        )
    except FileNotFoundError as exc:
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
