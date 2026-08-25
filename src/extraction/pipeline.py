"""
Extraction pipeline orchestrator.

Runs entity & relationship extraction over all document chunks, with:
  - Cost estimation before the run (--dry-run mode)
  - Chunk-level caching (skip already-extracted chunks)
  - Per-chunk cache writes (survive interruptions)
  - Rich progress display
  - Summary report
"""

import json
import logging
from pathlib import Path

import anthropic
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from src.config import settings
from src.extraction.cache import ExtractionCache
from src.extraction.extractor import DEFAULT_MODEL, ExtractionError, estimate_cost, extract_chunk
from src.extraction.schemas import ExtractionRunStats

logger = logging.getLogger(__name__)
console = Console()

# Approximate output tokens per chunk (for dry-run cost estimation)
_EST_OUTPUT_TOKENS_PER_CHUNK = 400


def _load_chunks(chunks_file: Path) -> list[dict]:
    if not chunks_file.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_file}\n"
            "Run `python scripts/ingest.py` first."
        )
    return json.loads(chunks_file.read_text(encoding="utf-8"))


def _print_dry_run(chunks: list[dict], model: str) -> None:
    """Print cost estimate without making any API calls."""
    total_input_tokens = sum(c["token_count"] for c in chunks)
    # System prompt is ~600 tokens, user message wrapper ~50 tokens
    total_input_with_overhead = total_input_tokens + len(chunks) * 650
    total_output_tokens = len(chunks) * _EST_OUTPUT_TOKENS_PER_CHUNK
    cost = estimate_cost(total_input_with_overhead, total_output_tokens, model)

    console.print("\n[bold yellow]DRY RUN — no API calls will be made[/bold yellow]")
    console.print(f"\n  Chunks to extract  : [bold]{len(chunks)}[/bold]")
    console.print(f"  Chunk tokens       : [yellow]{total_input_tokens:,}[/yellow]")
    console.print(f"  Overhead (per call): ~650 tokens (system prompt + wrapper)")
    console.print(f"  Est. input tokens  : [yellow]{total_input_with_overhead:,}[/yellow]")
    console.print(f"  Est. output tokens : [yellow]{total_output_tokens:,}[/yellow]")
    console.print(f"  Model              : {model}")
    console.print(f"  [bold]Estimated cost     : ${cost:.4f} USD[/bold]\n")


def _print_summary(stats: ExtractionRunStats) -> None:
    table = Table(title="[bold]Extraction Summary[/bold]", show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Chunks processed", str(stats.chunks_processed))
    table.add_row("Chunks from cache", str(stats.chunks_cached))
    table.add_row("Chunks failed", f"[red]{stats.chunks_failed}[/red]" if stats.chunks_failed else "0")
    table.add_row("Total entities", f"[green]{stats.total_entities}[/green]")
    table.add_row("Total relationships", f"[green]{stats.total_relationships}[/green]")
    table.add_row("Input tokens used", f"{stats.total_input_tokens:,}")
    table.add_row("Output tokens used", f"{stats.total_output_tokens:,}")
    table.add_row("Estimated cost", f"[yellow]${stats.estimated_cost_usd:.4f} USD[/yellow]")
    console.print()
    console.print(table)


def run_extraction(
    chunks_file: Path | None = None,
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
    sample: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> ExtractionRunStats:
    """
    Run entity & relationship extraction over all chunks.

    Args:
        chunks_file: Path to all_chunks.json. Defaults to output/all_chunks.json.
        output_dir:  Where to write results. Defaults to settings.output_dir.
        model:       Claude model ID to use.
        sample:      If set, only process this many chunks (for testing).
        dry_run:     Estimate cost only — no API calls.
        force:       Re-extract even if chunk is already in cache.

    Returns:
        ExtractionRunStats with counts and cost.
    """
    output_dir = output_dir or settings.output_dir
    chunks_file = chunks_file or (output_dir / "all_chunks.json")

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Extraction Pipeline ━━━[/bold cyan]")
    console.print(f"  Chunks  : [yellow]{chunks_file}[/yellow]")
    console.print(f"  Model   : [yellow]{model}[/yellow]")

    all_chunks = _load_chunks(chunks_file)

    if sample:
        all_chunks = all_chunks[:sample]
        console.print(f"  [dim]Sample mode: processing first {sample} chunk(s)[/dim]")

    # Determine which chunks need extraction
    cache = ExtractionCache(output_dir / "extraction_cache.json")
    if force:
        to_extract = all_chunks
    else:
        cached_ids = cache.cached_ids
        to_extract = [c for c in all_chunks if c["chunk_id"] not in cached_ids]
        n_cached = len(all_chunks) - len(to_extract)
        if n_cached:
            console.print(f"  [dim]Skipping {n_cached} already-extracted chunk(s) (cached)[/dim]")

    if dry_run:
        _print_dry_run(to_extract, model)
        return ExtractionRunStats(chunks_cached=len(all_chunks) - len(to_extract))

    if not to_extract:
        console.print("\n  [green]All chunks already extracted. Nothing to do.[/green]\n")
        n_cached = len(all_chunks)
        # Still count entities/relationships from cache for stats
        stats = ExtractionRunStats(chunks_cached=n_cached)
        for chunk in all_chunks:
            rec = cache.get(chunk["chunk_id"])
            if rec:
                stats.total_entities += len(rec.extraction.entities)
                stats.total_relationships += len(rec.extraction.relationships)
        _print_summary(stats)
        return stats

    if not settings.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set. Create a .env file from .env.example.[/red]")
        raise SystemExit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    stats = ExtractionRunStats(chunks_cached=len(all_chunks) - len(to_extract))
    failed_chunks: list[str] = []

    console.print(f"\n  Extracting [bold]{len(to_extract)}[/bold] chunk(s)...\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  Extracting...", total=len(to_extract))

        for chunk in to_extract:
            progress.update(task, description=f"  [{chunk['doc_type']:10}] {chunk['source_file'].split('/')[-1][:30]}")
            try:
                record = extract_chunk(
                    chunk_id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    source_file=chunk["source_file"],
                    doc_hash=chunk["doc_hash"],
                    section=chunk["section"],
                    content=chunk["content"],
                    client=client,
                    model=model,
                )
                cache.put(record)  # write to disk immediately
                stats.chunks_processed += 1
                stats.total_entities += len(record.extraction.entities)
                stats.total_relationships += len(record.extraction.relationships)
                stats.total_input_tokens += record.input_tokens
                stats.total_output_tokens += record.output_tokens
                stats.estimated_cost_usd += estimate_cost(
                    record.input_tokens, record.output_tokens, model
                )
            except ExtractionError as exc:
                logger.error("Failed to extract chunk %s: %s", chunk["chunk_id"][:8], exc)
                failed_chunks.append(chunk["chunk_id"])
                stats.chunks_failed += 1
            finally:
                progress.advance(task)

    # Also count entities/relationships from cached chunks
    for chunk in all_chunks:
        if chunk["chunk_id"] in cache.cached_ids and chunk["chunk_id"] not in [c["chunk_id"] for c in to_extract]:
            rec = cache.get(chunk["chunk_id"])
            if rec:
                stats.total_entities += len(rec.extraction.entities)
                stats.total_relationships += len(rec.extraction.relationships)

    # Write combined output file
    all_records = []
    for chunk in all_chunks:
        rec = cache.get(chunk["chunk_id"])
        if rec:
            all_records.append(rec.to_dict())

    extractions_path = output_dir / "extractions.json"
    extractions_path.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"\n  Results saved → [yellow]{extractions_path}[/yellow]")

    if failed_chunks:
        console.print(f"\n  [red]⚠ {len(failed_chunks)} chunk(s) failed extraction:[/red]")
        for cid in failed_chunks:
            console.print(f"    {cid[:12]}...")

    _print_summary(stats)
    return stats
