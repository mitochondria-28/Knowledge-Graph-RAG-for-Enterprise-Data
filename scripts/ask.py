#!/usr/bin/env python3
"""
End-to-end Q&A CLI — Phase 8.

Usage examples:

    # Mock mode (no API key, no databases required):
    python scripts/ask.py "Who leads the Platform Team?"
    python scripts/ask.py --mock "Who leads the team that maintains StellarDB?"

    # With real Claude API key (set ANTHROPIC_API_KEY in .env):
    python scripts/ask.py "What technology did TechNova acquire from Stellar Systems?"

    # Control retrieval depth:
    python scripts/ask.py --top-k 8 "What projects use StellarDB?"

    # Verbose (shows routing features, all retrieved chunks):
    python scripts/ask.py --verbose "Who leads the Platform Team?"

Output always shows:
  - Routing decision (strategy, hop_depth, confidence, detected entities)
  - Number of chunks retrieved
  - The answer
  - Each citation with ✓/✗ validation status and match score
  - Overall citation confidence
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    question: str = typer.Argument(..., help="Question to answer."),
    mock: bool = typer.Option(
        False, "--mock", help="Use mock generator (no API key needed)."
    ),
    top_k: int = typer.Option(5, "--top-k", help="Number of chunks to retrieve."),
    model: str = typer.Option(
        "claude-haiku-4-5-20251001",
        "--model",
        help="Claude model for generation (ignored with --mock).",
    ),
    chunks_file: Path = typer.Option(
        Path("output/all_chunks.json"),
        "--chunks-file",
        help="Path to all_chunks.json",
    ),
    entities_file: Path = typer.Option(
        Path("output/resolved_entities.json"),
        "--entities-file",
        help="Path to resolved_entities.json for entity detection.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Answer a question using the knowledge graph RAG pipeline."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(name)s %(levelname)s %(message)s",
    )

    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.router.pipeline import load_entity_index

    # ── Resolve generator ─────────────────────────────────────────────────────
    generator = _resolve_generator(mock, model)
    if generator is None:
        raise typer.Exit(1)

    # ── Build pipeline ────────────────────────────────────────────────────────
    chunks = load_chunks(chunks_file)
    entity_index = load_entity_index(entities_file)
    pipeline = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
        top_k=top_k,
    )

    # ── Run ───────────────────────────────────────────────────────────────────
    console.print()
    console.print(f"[bold cyan]Question:[/bold cyan] {question}\n")

    # Show routing decision first
    decision = pipeline._router.route(question)
    _print_routing(decision, verbose)

    # Full pipeline answer
    validated = pipeline.ask(question)

    # Print answer
    _print_answer(validated, verbose)


def _resolve_generator(mock: bool, model: str):
    from src.answer.generator import MockAnswerGenerator

    if mock:
        console.print("[dim]Mode: mock (no API call)[/dim]\n")
        return MockAnswerGenerator()

    # Try real API
    try:
        import anthropic
        from src.config import settings

        if not settings.anthropic_api_key:
            console.print(
                "[yellow]Warning:[/yellow] ANTHROPIC_API_KEY not set. "
                "Falling back to mock mode. Use --mock to suppress this warning.\n"
            )
            return MockAnswerGenerator()

        from src.answer.generator import AnswerGenerator
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        console.print(f"[dim]Mode: real Claude ({model})[/dim]\n")
        return AnswerGenerator(client, model=model)

    except Exception as e:
        console.print(f"[red]Could not initialise Anthropic client: {e}[/red]")
        console.print("[dim]Falling back to mock mode.[/dim]\n")
        return MockAnswerGenerator()


def _print_routing(decision, verbose: bool) -> None:
    strategy_color = {
        "vector": "green",
        "graph": "yellow",
        "hybrid": "cyan",
    }.get(decision.strategy, "white")

    console.print(
        f"[bold]Routing:[/bold] "
        f"[{strategy_color}]{decision.strategy.upper()}[/{strategy_color}] "
        f"| hop_depth={decision.hop_depth} "
        f"| confidence={decision.confidence:.2f}"
    )
    console.print(f"[dim]Reason: {decision.reason}[/dim]")
    if decision.detected_entities:
        console.print(f"[dim]Entities: {', '.join(decision.detected_entities)}[/dim]")
    console.print()


def _print_answer(validated, verbose: bool) -> None:
    # ── Answer panel ──────────────────────────────────────────────────────────
    console.print(Panel(
        validated.answer_text,
        title=f"[bold]Answer[/bold] [dim]({validated.model})[/dim]",
        border_style="green" if validated.citation_confidence >= 0.8 else "yellow",
        padding=(1, 2),
    ))

    # ── Citations table ───────────────────────────────────────────────────────
    if validated.validation_results:
        table = Table(
            title=f"Citations — confidence {validated.citation_confidence:.0%} "
                  f"({validated.valid_count}/{len(validated.validation_results)} valid)",
            show_header=True,
            header_style="bold cyan",
            show_lines=True,
        )
        table.add_column("", width=3, justify="center")
        table.add_column("Source", width=40)
        table.add_column("Quote", width=55)
        table.add_column("Score", width=7, justify="right")
        table.add_column("Reason", width=22)

        for r in validated.validation_results:
            icon = "[green]✓[/green]" if r.is_valid else "[red]✗[/red]"
            score_str = f"{r.match_score:.0%}"
            source = Path(r.source_file).name if r.source_file != "UNKNOWN" else "[red]UNKNOWN[/red]"
            quote_short = (r.quote[:52] + "…") if len(r.quote) > 52 else r.quote
            table.add_row(icon, source, f"[dim]{quote_short}[/dim]", score_str, r.reason)

        console.print(table)
    else:
        console.print("[dim]No citations were produced.[/dim]")

    # ── Summary line ──────────────────────────────────────────────────────────
    conf = validated.citation_confidence
    color = "green" if conf >= 0.8 else "yellow" if conf >= 0.5 else "red"
    console.print(
        f"\n  Retrieval strategy: [bold]{validated.retrieval_strategy.upper()}[/bold]  "
        f"| Chunks used: {validated.chunk_count}  "
        f"| Citation confidence: [{color}]{conf:.0%}[/{color}]  "
        f"| Latency: {validated.latency_ms:.0f}ms\n"
    )


if __name__ == "__main__":
    app()
