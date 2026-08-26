#!/usr/bin/env python3
"""
Benchmark the full pipeline against the 20 evaluation questions — Phase 10.

Usage:
    # Mock mode (no API key needed, fast):
    python scripts/benchmark.py --mock

    # Real Claude (needs ANTHROPIC_API_KEY in .env):
    python scripts/benchmark.py

    # Subset of questions:
    python scripts/benchmark.py --mock --questions 5

    # Custom output path:
    python scripts/benchmark.py --mock --output output/my_run.json

Output:
    - Rich tables to terminal (latency breakdown, quality by type, per-question)
    - JSON report saved to --output path (default: output/benchmark_report.json)
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use MockAnswerGenerator (no API key, <5ms per question).",
    ),
    questions: int = typer.Option(
        0,
        "--questions",
        min=0,
        help="Number of questions to benchmark (0 = all 20).",
    ),
    output: Path = typer.Option(
        Path("output/benchmark_report.json"),
        "--output",
        help="Path to save the JSON report.",
    ),
    top_k: int = typer.Option(5, "--top-k", help="Chunks retrieved per question."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Benchmark the pipeline and produce a latency + quality report."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(name)s %(levelname)s %(message)s",
    )

    from src.answer.generator import MockAnswerGenerator
    from src.answer.pipeline import AnswerPipeline, load_chunks
    from src.benchmark.report import print_report, save_report
    from src.benchmark.runner import BenchmarkRunner
    from src.router.pipeline import load_entity_index
    from tests.evaluation.questions import QUESTIONS

    # ── Build pipeline ────────────────────────────────────────────────────────
    chunks = load_chunks()
    entity_index = load_entity_index()

    if mock:
        generator = MockAnswerGenerator()
        console.print("[dim]Generator: MockAnswerGenerator (no API calls)[/dim]")
    else:
        try:
            from src.answer.generator import make_generator
            from src.config import settings
            if not settings.gemini_api_key:
                console.print(
                    "[yellow]GEMINI_API_KEY not set — falling back to mock.[/yellow]"
                )
                generator = MockAnswerGenerator()
            else:
                generator = make_generator(api_key=settings.gemini_api_key)
                console.print(f"[dim]Generator: AnswerGenerator ({generator._model})[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not init real generator ({e}) — using mock.[/yellow]")
            generator = MockAnswerGenerator()

    pipeline = AnswerPipeline(
        generator=generator,
        chunks=chunks,
        entity_index=entity_index,
        top_k=top_k,
    )

    # ── Select questions ──────────────────────────────────────────────────────
    q_list = QUESTIONS if not questions else QUESTIONS[:questions]
    console.print(
        f"\n[bold cyan]Benchmarking[/bold cyan] {len(q_list)} questions "
        f"(top_k={top_k}) …\n"
    )

    # ── Run benchmark ─────────────────────────────────────────────────────────
    runner = BenchmarkRunner(pipeline)
    report = runner.run(q_list)

    # ── Print report ──────────────────────────────────────────────────────────
    print_report(report)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    save_report(report, output)
    console.print(f"  Report saved → [dim]{output}[/dim]\n")


if __name__ == "__main__":
    app()
