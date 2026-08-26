"""
Benchmark report formatter — Phase 10.

Converts a BenchmarkReport into:
  1. Rich console tables (for terminal display)
  2. JSON file (for diff across runs / long-term tracking)

WHY JSON OUTPUT:

A structured JSON report lets you compare performance across code changes
by diffing the files:

    diff <(jq .latency.total output/benchmark_report_v1.json) \
         <(jq .latency.total output/benchmark_report_v2.json)

And it survives sessions — you can regenerate the Rich tables from the
saved JSON without re-running the pipeline.
"""

import dataclasses
import json
import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.benchmark.models import BenchmarkReport

logger = logging.getLogger(__name__)
console = Console()


# ── JSON serialisation ────────────────────────────────────────────────────────

def save_report(report: BenchmarkReport, path: Path) -> None:
    """Serialise BenchmarkReport to JSON. Overwrites if exists."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        raise TypeError(f"Not serialisable: {type(obj)}")

    path.write_text(
        json.dumps(dataclasses.asdict(report), indent=2, default=_default),
        encoding="utf-8",
    )
    logger.info("Report saved to %s", path)


# ── Rich console output ───────────────────────────────────────────────────────

def print_report(report: BenchmarkReport) -> None:
    """Render a full BenchmarkReport to the terminal using Rich."""
    _print_summary(report)
    _print_latency_table(report)
    _print_quality_table(report)
    _print_per_question_table(report)


def _print_summary(report: BenchmarkReport) -> None:
    routing_color = "green" if report.routing_accuracy >= 0.80 else "yellow"
    conf_color    = "green" if report.mean_citation_confidence >= 0.80 else "yellow"

    console.print()
    console.print("[bold cyan]═══ Benchmark Report ═══[/bold cyan]")
    console.print(f"  Run at      : [dim]{report.run_at}[/dim]")
    console.print(f"  Generator   : [dim]{report.generator}[/dim]")
    console.print(f"  Questions   : {report.question_count}")
    console.print(
        f"  Routing acc : [{routing_color}]"
        f"{report.routing_accuracy:.0%}[/{routing_color}]"
    )
    console.print(
        f"  Mean citation confidence: [{conf_color}]"
        f"{report.mean_citation_confidence:.0%}[/{conf_color}]"
    )
    console.print()


def _print_latency_table(report: BenchmarkReport) -> None:
    table = Table(
        title="[bold]Latency breakdown (ms)[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Stage",      width=12)
    table.add_column("Mean",       width=8,  justify="right")
    table.add_column("P50",        width=8,  justify="right")
    table.add_column("P95",        width=8,  justify="right")
    table.add_column("P99",        width=8,  justify="right")
    table.add_column("Min",        width=8,  justify="right")
    table.add_column("Max",        width=8,  justify="right")

    for stage, stats in report.latency.items():
        is_total = stage == "total"
        style = "bold" if is_total else ""
        table.add_row(
            Text(stage, style=style),
            Text(f"{stats.mean_ms:.1f}", style=style),
            Text(f"{stats.p50_ms:.1f}", style=style),
            Text(f"{stats.p95_ms:.1f}", style=style),
            Text(f"{stats.p99_ms:.1f}", style=style),
            Text(f"{stats.min_ms:.1f}", style=style),
            Text(f"{stats.max_ms:.1f}", style=style),
            end_section=is_total,
        )

    console.print(table)
    console.print()


def _print_quality_table(report: BenchmarkReport) -> None:
    table = Table(
        title="[bold]Quality by question type[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Type",          width=16)
    table.add_column("Routing acc",   width=13, justify="right")
    table.add_column("Cit. conf.",    width=12, justify="right")

    all_types = sorted(
        set(report.routing_by_type) | set(report.citation_by_type)
    )
    for qtype in all_types:
        racc = report.routing_by_type.get(qtype, float("nan"))
        cconf = report.citation_by_type.get(qtype, float("nan"))
        racc_color = "green" if racc >= 0.75 else "yellow" if racc >= 0.5 else "red"
        cconf_color = "green" if cconf >= 0.80 else "yellow"
        table.add_row(
            qtype,
            Text(f"{racc:.0%}", style=racc_color),
            Text(f"{cconf:.0%}", style=cconf_color),
        )

    console.print(table)
    console.print()


def _print_per_question_table(report: BenchmarkReport) -> None:
    table = Table(
        title="[bold]Per-question results[/bold]",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("QID",      width=5)
    table.add_column("Type",     width=14)
    table.add_column("Expected", width=9)
    table.add_column("Routed",   width=9)
    table.add_column("✓",        width=3, justify="center")
    table.add_column("Cit. conf",width=10, justify="right")
    table.add_column("Total ms", width=10, justify="right")

    for r in report.per_question:
        ok = "[green]✓[/green]" if r.correct_routing else "[red]✗[/red]"
        strategy_color = {
            "vector": "green", "graph": "yellow", "hybrid": "cyan"
        }.get(r.routed_strategy, "white")
        conf_color = "green" if r.citation_confidence >= 0.8 else "yellow"

        table.add_row(
            r.qid,
            r.question_type,
            r.expected_strategy,
            f"[{strategy_color}]{r.routed_strategy}[/]",
            ok,
            Text(f"{r.citation_confidence:.0%}", style=conf_color),
            f"{r.total_ms:.1f}",
        )

    console.print(table)
    console.print()
