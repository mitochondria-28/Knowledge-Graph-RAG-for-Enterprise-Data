#!/usr/bin/env python3
"""
CLI entry point for graph loading (Phase 4).

Usage:
    # Dry-run — validates data, prints what would be loaded (no Neo4j needed):
    python scripts/load_graph.py --dry-run

    # Load using Phase 3 fixture output:
    python scripts/load_graph.py \
        --entities-file output/resolved_entities.json \
        --rels-file output/resolved_relationships.json

    # Force re-load from scratch (wipe existing nodes first):
    python scripts/load_graph.py --force

    # Verbose logging:
    python scripts/load_graph.py --verbose
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

from src.graph.pipeline import run_graph_load

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    entities_file: Path = typer.Option(
        Path("output/resolved_entities.json"),
        "--entities-file",
        help="Path to resolved_entities.json (Phase 3 output).",
        show_default=True,
    ),
    rels_file: Path = typer.Option(
        Path("output/resolved_relationships.json"),
        "--rels-file",
        help="Path to resolved_relationships.json (Phase 3 output).",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        show_default=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete all existing Entity nodes before loading (full re-load).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate data without writing to Neo4j.",
    ),
    batch_size: int = typer.Option(
        500,
        "--batch-size",
        help="Entities / relationships per UNWIND batch.",
        show_default=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Load resolved entities and relationships into the Neo4j knowledge graph."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s  %(name)-35s  %(levelname)-8s  %(message)s",
    )
    try:
        run_graph_load(
            entities_file=entities_file,
            relationships_file=rels_file,
            output_dir=output_dir,
            force=force,
            dry_run=dry_run,
            batch_size=batch_size,
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
