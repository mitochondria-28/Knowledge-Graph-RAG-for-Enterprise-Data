#!/usr/bin/env python3
"""
CLI for testing the question router (Phase 7).

Usage:
    # Route a single question:
    python scripts/route_question.py "Who leads the team that maintains StellarDB?"

    # Route all 20 evaluation questions and show agreement with expected types:
    python scripts/route_question.py --eval

    # Use a specific entity index file:
    python scripts/route_question.py --entities-file output/resolved_entities.json \\
        "What is ApexML?"

    # Verbose (shows extracted features):
    python scripts/route_question.py --verbose "When did TechNova acquire Stellar Systems?"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)
console = Console()

# Expected strategy per question type (from Phase 6 evaluation analysis)
_EXPECTED_STRATEGY: dict[str, str] = {
    "simple_entity": "vector",
    "factual":       "vector",
    "one_hop":       "graph",
    "two_hop":       "graph",
    "three_hop":     "graph",
    "multi_entity":  "hybrid",
}


@app.command()
def main(
    question: str = typer.Argument(
        None,
        help="Question to route. Omit to use --eval mode.",
    ),
    entities_file: Path = typer.Option(
        Path("output/resolved_entities.json"),
        "--entities-file",
        help="Path to resolved_entities.json for entity detection.",
        show_default=True,
    ),
    eval_mode: bool = typer.Option(
        False,
        "--eval",
        help="Route all 20 evaluation questions and compare with expected strategies.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Route questions to the appropriate retrieval strategy."""
    import logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    from src.router.pipeline import QuestionRouter, load_entity_index

    entity_index = load_entity_index(entities_file)
    router = QuestionRouter(entity_index)

    console.print(
        f"\n[bold cyan]Question Router[/bold cyan]  "
        f"([dim]{router.entity_count} entities in index[/dim])\n"
    )

    if eval_mode:
        _run_eval_mode(router)
    elif question:
        _route_single(router, question, verbose)
    else:
        console.print("[red]Provide a question or use --eval[/red]")
        raise typer.Exit(1)


def _route_single(router, question: str, verbose: bool) -> None:
    from src.router.signals import extract_features
    decision = router.route(question)

    console.print(f"[bold]Question:[/bold] {question}")
    console.print(f"[bold]Strategy:[/bold] [{'green' if decision.strategy == 'vector' else 'yellow' if decision.strategy == 'graph' else 'cyan'}]{decision.strategy.upper()}[/]")
    console.print(f"[bold]Reason  :[/bold] {decision.reason}")
    console.print(f"[bold]Confidence:[/bold] {decision.confidence:.2f}")
    if decision.detected_entities:
        console.print(f"[bold]Entities :[/bold] {decision.detected_entities}")
    if decision.strategy == "graph":
        console.print(f"[bold]Hop depth:[/bold] {decision.hop_depth}")

    if verbose and decision.features:
        f = decision.features
        console.print(f"\n[dim]Features:[/dim]")
        console.print(f"  [dim]question_word      :[/dim] {f.question_word!r}")
        console.print(f"  [dim]is_definition      :[/dim] {f.is_definition}")
        console.print(f"  [dim]is_temporal        :[/dim] {f.is_temporal}")
        console.print(f"  [dim]is_person_query    :[/dim] {f.is_person_query}")
        console.print(f"  [dim]relational_verbs   :[/dim] {f.relational_verbs_found}")
        console.print(f"  [dim]relative_clauses   :[/dim] {f.relative_clause_count}")
        console.print(f"  [dim]hop_depth          :[/dim] {f.hop_depth}")
        console.print(f"  [dim]has_multi_hop      :[/dim] {f.has_multi_hop_pattern}")
        console.print(f"  [dim]has_acquisition    :[/dim] {f.has_acquisition_language}")


def _run_eval_mode(router) -> None:
    from tests.evaluation.questions import QUESTIONS

    table = Table(
        title="[bold]Router decisions vs. expected strategies[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("QID",      width=5)
    table.add_column("Type",     width=14)
    table.add_column("Expected", width=9)
    table.add_column("Routed",   width=9)
    table.add_column("Match",    width=6, justify="center")
    table.add_column("Confidence", width=10, justify="right")
    table.add_column("Entities detected", width=35)

    correct = 0
    total = len(QUESTIONS)

    for q in QUESTIONS:
        decision = router.route(q.question)
        expected = _EXPECTED_STRATEGY.get(q.question_type, "hybrid")
        match = decision.strategy == expected
        if match:
            correct += 1

        match_icon  = "[green]✓[/green]" if match else "[red]✗[/red]"
        routed_color = "green" if decision.strategy == "vector" else "yellow" if decision.strategy == "graph" else "cyan"

        table.add_row(
            q.qid,
            q.question_type,
            expected,
            f"[{routed_color}]{decision.strategy}[/]",
            match_icon,
            f"{decision.confidence:.2f}",
            ", ".join(decision.detected_entities[:3]) or "—",
        )

    console.print(table)
    acc = correct / total
    color = "green" if acc >= 0.75 else "yellow" if acc >= 0.55 else "red"
    console.print(
        f"\n  Routing accuracy: [{color}]{correct}/{total} = {acc:.0%}[/{color}]"
        f"  (expected ≥75% with entity index loaded)\n"
    )


if __name__ == "__main__":
    app()
