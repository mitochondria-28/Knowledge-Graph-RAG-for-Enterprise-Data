"""
Evaluation pipeline orchestrator.

MODES:

  keyword-only (default, no databases needed):
    Runs only the KeywordRetriever. Shows what simple token matching achieves
    and validates the evaluation framework without any infrastructure.

  full (requires PostgreSQL + Neo4j + embeddings):
    Runs keyword + vector + graph retrievers and produces a three-way
    comparison table.

OUTPUT:
    output/eval_results.json   — full per-question scores for all retrievers
    Rich table printed to stdout with macro averages and per-type breakdown
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.config import settings
from src.evaluation.harness import EvaluationHarness, build_source_index
from src.evaluation.keyword_retriever import KeywordRetriever
from src.evaluation.models import EvalReport

logger = logging.getLogger(__name__)
console = Console()

_TYPE_ORDER = ["simple_entity", "factual", "one_hop", "two_hop", "three_hop", "multi_entity"]


def _print_comparison(reports: list[EvalReport]) -> None:
    k = reports[0].k if reports else 5

    # ── Per-question detail ────────────────────────────────────────────────
    detail = Table(
        title=f"[bold]Per-question scores (k={k})[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    detail.add_column("QID", style="dim", width=4)
    detail.add_column("Type", style="dim", width=14)
    for r in reports:
        detail.add_column(f"{r.retriever}\nF1@{k}", justify="right", width=10)

    all_qids = sorted({s.qid for r in reports for s in r.scores})
    for qid in all_qids:
        row = [qid]
        qtype = ""
        for r in reports:
            score = next((s for s in r.scores if s.qid == qid), None)
            if score:
                qtype = score.question_type
                row.append(f"{score.f1_at_k:.2f}")
            else:
                row.append("—")
        row.insert(1, qtype)
        detail.add_row(*row)
    console.print()
    console.print(detail)

    # ── Macro summary ──────────────────────────────────────────────────────
    summary = Table(
        title="[bold]Overall macro averages[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    summary.add_column("Retriever", style="white")
    summary.add_column(f"P@{k}", justify="right")
    summary.add_column(f"R@{k}", justify="right")
    summary.add_column(f"F1@{k}", justify="right")
    summary.add_column("MRR", justify="right")

    for r in reports:
        summary.add_row(
            r.retriever,
            f"{r.macro_precision:.3f}",
            f"{r.macro_recall:.3f}",
            f"{r.macro_f1:.3f}",
            f"{r.macro_mrr:.3f}",
        )
    console.print()
    console.print(summary)

    # ── Per-type breakdown ────────────────────────────────────────────────
    type_table = Table(
        title=f"[bold]F1@{k} by question type[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    type_table.add_column("Type", style="white", width=15)
    type_table.add_column("n", justify="right", width=4)
    for r in reports:
        type_table.add_column(r.retriever, justify="right", width=10)

    all_types = sorted(
        {qt for r in reports for qt in r.by_type},
        key=lambda t: _TYPE_ORDER.index(t) if t in _TYPE_ORDER else 99,
    )
    for qtype in all_types:
        n = max(
            (int(r.by_type[qtype]["count"]) for r in reports if qtype in r.by_type),
            default=0,
        )
        row = [qtype, str(n)]
        for r in reports:
            f1 = r.by_type.get(qtype, {}).get("f1", 0.0)
            row.append(f"{f1:.3f}")
        type_table.add_row(*row)
    console.print()
    console.print(type_table)
    console.print()


def run_evaluation(
    chunks_file: Path | None = None,
    output_dir: Path | None = None,
    k: int = 5,
    include_vector: bool = False,
    include_graph: bool = False,
    hop_depth: int = 2,
) -> list[EvalReport]:
    """
    Run retrieval evaluation over the 20 gold-standard questions.

    Args:
        chunks_file:    Path to all_chunks.json.
        output_dir:     Where to write eval_results.json.
        k:              Number of results per query.
        include_vector: Also run VectorRetriever (needs PostgreSQL + embeddings).
        include_graph:  Also run GraphRetriever (needs Neo4j + entities).
        hop_depth:      Hops for graph retrieval (1, 2, or 3).

    Returns:
        List of EvalReport, one per retriever.
    """
    from tests.evaluation.questions import QUESTIONS

    output_dir = output_dir or settings.output_dir
    chunks_file = chunks_file or (output_dir / "all_chunks.json")

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Retrieval Evaluation (Phase 6) ━━━[/bold cyan]")
    console.print(f"  Questions   : {len(QUESTIONS)}")
    console.print(f"  k           : {k}")
    console.print(f"  Chunks file : [yellow]{chunks_file}[/yellow]")

    # Load chunks and build source index
    import json as _json
    chunks = _json.loads(chunks_file.read_text(encoding="utf-8"))
    source_index = build_source_index(chunks)
    console.print(f"  Chunks      : {len(chunks)} from {len(source_index)} source files")

    # Assemble retriever list
    retrievers = [KeywordRetriever(chunks)]

    if include_vector:
        console.print("\n  [yellow]Setting up VectorRetriever…[/yellow]")
        try:
            from src.vector.connection import get_connection
            from src.vector.embedder import mock_embed_texts
            _conn_ctx = get_connection()
            _conn = _conn_ctx.__enter__()
            from src.evaluation.vector_retriever import VectorRetriever
            retrievers.append(VectorRetriever(_conn, mock_embed_texts))
            console.print("  [green]VectorRetriever ready[/green]")
        except Exception as exc:
            console.print(f"  [red]VectorRetriever unavailable:[/red] {exc}")
            console.print("  [dim]Run: docker compose up -d postgres && "
                          "python scripts/embed_chunks.py --mock-embeddings[/dim]")

    if include_graph:
        console.print("\n  [yellow]Setting up GraphRetriever…[/yellow]")
        try:
            from src.graph.connection import Neo4jConnection
            from src.evaluation.graph_retriever import GraphRetriever
            _neo4j_ctx = Neo4jConnection()
            _driver = _neo4j_ctx.__enter__()
            retrievers.append(GraphRetriever(_driver, hop_depth=hop_depth))
            console.print(f"  [green]GraphRetriever ready ({hop_depth}-hop)[/green]")
        except Exception as exc:
            console.print(f"  [red]GraphRetriever unavailable:[/red] {exc}")
            console.print("  [dim]Run: docker compose up -d neo4j && "
                          "python scripts/load_graph.py[/dim]")

    active = ", ".join(f"[bold]{r.name}[/bold]" for r in retrievers)
    console.print(f"\n  Active retrievers: {active}")

    # Run harness
    harness = EvaluationHarness(retrievers, source_index, k=k)
    reports = harness.run(QUESTIONS)

    # Print results
    _print_comparison(reports)

    # Write JSON output
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "eval_results.json"
    out_data = {
        "k": k,
        "question_count": len(QUESTIONS),
        "reports": [
            {
                "retriever": r.retriever,
                "macro_precision": r.macro_precision,
                "macro_recall": r.macro_recall,
                "macro_f1": r.macro_f1,
                "macro_mrr": r.macro_mrr,
                "by_type": r.by_type,
                "scores": [
                    {
                        "qid": s.qid,
                        "question": s.question,
                        "question_type": s.question_type,
                        "precision_at_k": s.precision_at_k,
                        "recall_at_k": s.recall_at_k,
                        "f1_at_k": s.f1_at_k,
                        "mrr": s.mrr,
                        "relevant_count": s.relevant_count,
                        "retrieved_count": s.retrieved_count,
                    }
                    for s in r.scores
                ],
            }
            for r in reports
        ],
    }
    out_path.write_text(
        _json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    console.print(f"  Results written to [yellow]{out_path}[/yellow]")

    return reports
