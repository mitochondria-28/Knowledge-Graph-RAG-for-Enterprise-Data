"""
Graph loading pipeline.

Reads resolved entities and relationships from JSON,
connects to Neo4j, creates schema, and bulk-loads via MERGE.

DRY-RUN MODE:
  Loads the JSON and validates entity types and relationship types without
  touching Neo4j. Useful for verifying the data is well-formed before
  committing a slow bulk load.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config import settings
from src.graph.connection import Neo4jConnection
from src.graph.loader import load_entities, load_relationships
from src.graph.schema import create_schema, drop_all_entities_and_relationships

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class GraphLoadResult:
    entity_counts: dict[str, int] = field(default_factory=dict)
    rel_counts: dict[str, int] = field(default_factory=dict)
    total_entities: int = 0
    total_relationships: int = 0
    elapsed_seconds: float = 0.0
    dry_run: bool = False


def _load_json(path: Path, label: str) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{label} file not found: {path}\n"
            "Run `python scripts/resolve.py` first to generate resolution output.\n"
            "Or use `--extractions-file tests/fixtures/sample_extractions.json` "
            "followed by `python scripts/resolve.py` with that flag."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _print_summary(result: GraphLoadResult) -> None:
    # Entity table
    et = Table(
        title="[bold]Entities loaded into Neo4j[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    et.add_column("Entity Type", style="white")
    et.add_column("Nodes merged", justify="right", style="green")
    for etype, count in sorted(result.entity_counts.items()):
        et.add_row(etype, str(count))
    et.add_row("[bold]TOTAL[/bold]", f"[bold]{result.total_entities}[/bold]")
    console.print()
    console.print(et)

    # Relationship table
    rt = Table(
        title="[bold]Relationships loaded into Neo4j[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    rt.add_column("Relationship Type", style="white")
    rt.add_column("Edges merged", justify="right", style="green")
    for rtype, count in sorted(result.rel_counts.items()):
        rt.add_row(rtype, str(count))
    rt.add_row("[bold]TOTAL[/bold]", f"[bold]{result.total_relationships}[/bold]")
    console.print()
    console.print(rt)

    console.print(
        f"\n  [bold green]✓ Done[/bold green]  "
        f"({result.elapsed_seconds:.1f}s)"
        + (" [yellow][DRY RUN — nothing written][/yellow]" if result.dry_run else "")
    )


def run_graph_load(
    entities_file: Path | None = None,
    relationships_file: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 500,
) -> GraphLoadResult:
    """
    Load resolved entities and relationships into Neo4j.

    Args:
        entities_file:       Path to resolved_entities.json.
        relationships_file:  Path to resolved_relationships.json.
        output_dir:          Fallback directory if specific paths not given.
        force:               If True, delete all existing Entity nodes first.
        dry_run:             Validate data without touching Neo4j.
        batch_size:          Entities/relationships per UNWIND batch.

    Returns:
        GraphLoadResult with counts and timing.
    """
    output_dir = output_dir or settings.output_dir
    entities_file = entities_file or (output_dir / "resolved_entities.json")
    relationships_file = relationships_file or (output_dir / "resolved_relationships.json")

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Graph Loader (Phase 4) ━━━[/bold cyan]")
    console.print(f"  Entities    : [yellow]{entities_file}[/yellow]")
    console.print(f"  Rels        : [yellow]{relationships_file}[/yellow]")
    console.print(f"  Neo4j       : [yellow]{settings.neo4j_uri}[/yellow]")
    if dry_run:
        console.print("  [yellow]DRY RUN — will not write to Neo4j[/yellow]")

    # Load JSON
    entities = _load_json(entities_file, "Entities")
    relationships = _load_json(relationships_file, "Relationships")

    console.print(
        f"\n  Loaded [bold]{len(entities)}[/bold] entities, "
        f"[bold]{len(relationships)}[/bold] relationships from JSON"
    )

    result = GraphLoadResult(dry_run=dry_run)

    if dry_run:
        # Count by type without connecting to Neo4j
        from collections import Counter
        result.entity_counts = dict(Counter(e["entity_type"] for e in entities))
        result.rel_counts = dict(Counter(r["relationship_type"] for r in relationships))
        result.total_entities = len(entities)
        result.total_relationships = len(relationships)
        _print_summary(result)
        return result

    start = time.perf_counter()

    with Neo4jConnection() as driver:
        with driver.session(database="neo4j") as session:
            # Schema setup (idempotent)
            console.print("\n  Setting up schema (constraints + indexes)…")
            create_schema(session)

            # Optional clean slate
            if force:
                console.print("  [yellow]--force: deleting existing Entity nodes…[/yellow]")
                deleted = drop_all_entities_and_relationships(session)
                console.print(f"  Deleted [red]{deleted}[/red] nodes")

            # Load entities
            console.print(f"  Loading {len(entities)} entities (batch_size={batch_size})…")
            entity_counts = load_entities(session, entities, batch_size=batch_size)

            # Load relationships
            console.print(f"  Loading {len(relationships)} relationships…")
            rel_counts = load_relationships(session, relationships, batch_size=batch_size)

    elapsed = time.perf_counter() - start

    result.entity_counts = entity_counts
    result.rel_counts = rel_counts
    result.total_entities = sum(entity_counts.values())
    result.total_relationships = sum(rel_counts.values())
    result.elapsed_seconds = elapsed

    _print_summary(result)
    return result
