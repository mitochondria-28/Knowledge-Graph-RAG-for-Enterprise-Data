"""
Resolution pipeline orchestrator.

Loads extraction output → runs resolution → writes JSON output.

Handles two modes:
  REAL MODE  — reads output/extractions.json (produced by Phase 2)
  FIXTURE MODE — reads a provided fixture file (for development/testing)
"""

import json
import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config import settings
from src.extraction.schemas import EntityType, RelationshipType
from src.resolution.models import (
    EntityMention,
    RelationshipMention,
    ResolutionResult,
)
from src.resolution.resolver import resolve

logger = logging.getLogger(__name__)
console = Console()


# ── Load mentions from extraction output ──────────────────────────────────────

def _load_mentions(
    extractions_path: Path,
) -> tuple[list[EntityMention], list[RelationshipMention]]:
    """Parse extraction records into flat mention lists."""
    if not extractions_path.exists():
        raise FileNotFoundError(
            f"Extractions file not found: {extractions_path}\n"
            "Run `python scripts/extract.py` first to generate extraction output.\n"
            "Or use `--extractions-file tests/fixtures/sample_extractions.json` "
            "to run on the provided fixture."
        )

    records = json.loads(extractions_path.read_text(encoding="utf-8"))
    entity_mentions: list[EntityMention] = []
    relationship_mentions: list[RelationshipMention] = []

    for record in records:
        chunk_id = record["chunk_id"]
        source_file = record["source_file"]
        extraction = record["extraction"]

        for entity in extraction.get("entities", []):
            entity_mentions.append(EntityMention(
                name=entity["name"],
                entity_type=EntityType(entity["entity_type"]),
                chunk_id=chunk_id,
                source_file=source_file,
                confidence=entity["confidence"],
                description=entity.get("description"),
            ))

        for rel in extraction.get("relationships", []):
            relationship_mentions.append(RelationshipMention(
                source_name=rel["source_entity"],
                source_type=EntityType(rel["source_type"]),
                relationship_type=RelationshipType(rel["relationship_type"]),
                target_name=rel["target_entity"],
                target_type=EntityType(rel["target_type"]),
                chunk_id=chunk_id,
                source_file=source_file,
                confidence=rel["confidence"],
                supporting_text=rel.get("supporting_text"),
            ))

    return entity_mentions, relationship_mentions


# ── Print helpers ─────────────────────────────────────────────────────────────

def _print_entities(result: ResolutionResult) -> None:
    table = Table(
        title="[bold]Resolved Entities[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Canonical Name", style="white", max_width=35)
    table.add_column("Type", style="dim")
    table.add_column("Aliases", style="yellow", max_width=40)
    table.add_column("Mentions", justify="right", style="green")

    for entity in result.entities:
        aliases_str = ", ".join(entity.aliases) if entity.aliases else "—"
        table.add_row(
            entity.canonical_name,
            entity.entity_type.value,
            aliases_str[:39],
            str(entity.mention_count),
        )

    console.print()
    console.print(table)


def _print_summary(result: ResolutionResult) -> None:
    console.print(
        f"\n  [bold]Entity mentions  :[/bold] {result.raw_entity_mentions:>4}  →  "
        f"[bold green]{result.unique_entities_after}[/bold green] canonical entities "
        f"([yellow]{result.merge_count} merged[/yellow])"
    )
    console.print(
        f"  [bold]Relationships    :[/bold] {result.raw_relationship_mentions:>4}  →  "
        f"[bold green]{len(result.relationships)}[/bold green] deduplicated"
    )
    if result.review_items:
        console.print(
            f"  [bold yellow]⚠ Review queue   :[/bold yellow] "
            f"{result.review_count} pair(s) need human review "
            f"→ output/resolution_review.json"
        )
    console.print()


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_resolution(
    extractions_file: Path | None = None,
    output_dir: Path | None = None,
    auto_merge_threshold: float = 0.95,
    review_threshold: float = 0.82,
) -> ResolutionResult:
    """
    Run entity resolution over extraction output.

    Args:
        extractions_file:      Path to extractions JSON.
                               Defaults to output/extractions.json.
        output_dir:            Where to write resolved output.
        auto_merge_threshold:  Similarity ≥ this → auto-merge.
        review_threshold:      Similarity ≥ this (but < auto) → flag for review.

    Returns:
        ResolutionResult.
    """
    output_dir = output_dir or settings.output_dir
    extractions_file = extractions_file or (output_dir / "extractions.json")

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Entity Resolution ━━━[/bold cyan]")
    console.print(f"  Input   : [yellow]{extractions_file}[/yellow]")
    console.print(f"  Thresholds: auto-merge ≥ [green]{auto_merge_threshold}[/green], "
                  f"review ≥ [yellow]{review_threshold}[/yellow]")

    # Load
    entity_mentions, relationship_mentions = _load_mentions(extractions_file)
    console.print(
        f"\n  Loaded [bold]{len(entity_mentions)}[/bold] entity mentions, "
        f"[bold]{len(relationship_mentions)}[/bold] relationship mentions "
        f"from {extractions_file.name}"
    )

    # Resolve
    result = resolve(
        entity_mentions=entity_mentions,
        relationship_mentions=relationship_mentions,
        auto_merge_threshold=auto_merge_threshold,
        review_threshold=review_threshold,
    )

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    entities_path = output_dir / "resolved_entities.json"
    entities_path.write_text(
        json.dumps([e.to_dict() for e in result.entities], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    rels_path = output_dir / "resolved_relationships.json"
    rels_path.write_text(
        json.dumps([r.to_dict() for r in result.relationships], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if result.review_items:
        review_path = output_dir / "resolution_review.json"
        review_path.write_text(
            json.dumps(
                [item.model_dump() for item in result.review_items],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Display
    _print_entities(result)
    _print_summary(result)

    console.print(f"  [bold green]✓ Done.[/bold green]")
    console.print(f"    → {entities_path}")
    console.print(f"    → {rels_path}\n")

    return result
