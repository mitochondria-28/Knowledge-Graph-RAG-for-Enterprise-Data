"""
Ingestion pipeline orchestrator.

Responsibilities:
  1. Load documents from the corpus directory.
  2. Skip documents that have already been ingested (by comparing doc_hash).
  3. Chunk new documents and persist output to disk as JSON.
  4. Print a human-readable summary table via Rich.

Why hash-based deduplication?
  Documents will be re-ingested frequently during development. Without
  deduplication, every re-run doubles the chunk count, creates duplicate
  embeddings, and adds duplicate graph nodes. The doc_hash acts as a
  content fingerprint: if the file hasn't changed, its hash hasn't changed,
  so we skip it. If the file was edited, the new hash causes re-ingestion.
  This is called *idempotent ingestion* — safe to run many times.

Why save to JSON in Phase 1?
  The databases (Neo4j, PostgreSQL) come in Phases 4 and 5. For now we
  persist chunks as JSON so you can inspect them immediately and verify
  the pipeline is correct before touching the databases.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import track
from rich.table import Table

from src.config import settings
from src.ingestion.chunker import DocumentChunk, chunk_document, make_document_id
from src.ingestion.loader import RawDocument, load_corpus

logger = logging.getLogger(__name__)
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_previous_hashes(output_dir: Path) -> set[str]:
    """Read doc_hashes from the previous ingestion run's documents index."""
    index_path = output_dir / "documents.json"
    if not index_path.exists():
        return set()
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return {d["doc_hash"] for d in data}
    except Exception as exc:
        logger.warning("Could not read previous document index: %s", exc)
        return set()


def _append_json_list(path: Path, new_items: list[dict]) -> None:
    """Append new_items to an existing JSON array on disk (or create it)."""
    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    path.write_text(
        json.dumps(existing + new_items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _save_doc_chunks(output_dir: Path, doc_id: str, chunks: list[DocumentChunk]) -> None:
    """Save all chunks for one document to output/chunks/<document_id>.json."""
    chunk_path = output_dir / "chunks" / f"{doc_id}.json"
    chunk_path.write_text(
        json.dumps([c.to_dict() for c in chunks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _print_summary(doc_records: list[dict], all_chunks: list[DocumentChunk]) -> None:
    table = Table(
        title="[bold]Ingestion Summary[/bold]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Document", style="white", max_width=45)
    table.add_column("Type", style="dim")
    table.add_column("Chunks", justify="right", style="green")
    table.add_column("Tokens", justify="right", style="yellow")

    for rec in doc_records:
        doc_chunks = [c for c in all_chunks if c.source_file == rec["source_file"]]
        total_tokens = sum(c.token_count for c in doc_chunks)
        table.add_row(
            rec["title"][:44],
            rec["doc_type"],
            str(rec["chunk_count"]),
            f"{total_tokens:,}",
        )

    total_chunks = sum(r["chunk_count"] for r in doc_records)
    total_tokens_all = sum(c.token_count for c in all_chunks)

    console.print()
    console.print(table)
    console.print(
        f"\n[bold green]✓ Done.[/bold green]  "
        f"{len(doc_records)} document(s) → "
        f"[bold]{total_chunks}[/bold] chunks  "
        f"([yellow]{total_tokens_all:,}[/yellow] tokens total)\n"
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_ingestion(
    corpus_dir: Path | None = None,
    output_dir: Path | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    force: bool = False,
) -> dict:
    """
    Run the full ingestion pipeline.

    Args:
        corpus_dir:   Source documents directory. Defaults to settings.corpus_dir.
        output_dir:   Where to write JSON output. Defaults to settings.output_dir.
        chunk_size:   Target chunk size in tokens.
        chunk_overlap: Token overlap between adjacent chunks.
        force:        If True, re-ingest documents that were already processed.

    Returns:
        Stats dict with keys: documents_processed, documents_skipped,
        chunks_created, avg_tokens_per_chunk.
    """
    corpus_dir = corpus_dir or settings.corpus_dir
    output_dir = output_dir or settings.output_dir
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks").mkdir(exist_ok=True)

    console.print("\n[bold cyan]━━━ Enterprise KG-RAG · Ingestion Pipeline ━━━[/bold cyan]")
    console.print(f"  Corpus  : [yellow]{corpus_dir.resolve()}[/yellow]")
    console.print(f"  Output  : [yellow]{output_dir.resolve()}[/yellow]")
    console.print(f"  Chunk   : [yellow]{chunk_size}[/yellow] tokens  "
                  f"Overlap: [yellow]{chunk_overlap}[/yellow] tokens")

    # ── 1. Load ──────────────────────────────────────────────────
    documents: list[RawDocument] = load_corpus(corpus_dir)
    if not documents:
        console.print("[red]No documents found. Exiting.[/red]")
        return {"documents_processed": 0, "chunks_created": 0}

    # ── 2. Deduplicate ───────────────────────────────────────────
    previous_hashes = set() if force else _load_previous_hashes(output_dir)
    new_docs = [d for d in documents if d.doc_hash not in previous_hashes]
    n_skipped = len(documents) - len(new_docs)

    if n_skipped:
        console.print(f"\n  [dim]Skipping {n_skipped} already-ingested document(s).[/dim]")
    if not new_docs:
        console.print("[green]  All documents up to date. Nothing to do.[/green]\n")
        return {"documents_processed": 0, "documents_skipped": n_skipped, "chunks_created": 0}

    console.print(f"\n  Processing [bold]{len(new_docs)}[/bold] new document(s)...\n")

    # ── 3. Chunk ─────────────────────────────────────────────────
    all_chunks: list[DocumentChunk] = []
    doc_records: list[dict] = []

    for doc in track(new_docs, description="  Chunking..."):
        chunks = chunk_document(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        doc_id = make_document_id(doc.file_path)

        all_chunks.extend(chunks)
        doc_records.append({
            "document_id": doc_id,
            "title": doc.title,
            "source_file": str(doc.file_path),
            "doc_type": doc.doc_type,
            "doc_hash": doc.doc_hash,
            "char_count": doc.char_count,
            "chunk_count": len(chunks),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        })

        if chunks:
            _save_doc_chunks(output_dir, doc_id, chunks)

    # ── 4. Persist indexes ───────────────────────────────────────
    _append_json_list(output_dir / "documents.json", doc_records)
    _append_json_list(
        output_dir / "all_chunks.json",
        [c.to_dict() for c in all_chunks],
    )

    # ── 5. Summary ───────────────────────────────────────────────
    _print_summary(doc_records, all_chunks)

    avg_tokens = (
        sum(c.token_count for c in all_chunks) // len(all_chunks)
        if all_chunks else 0
    )
    return {
        "documents_processed": len(new_docs),
        "documents_skipped": n_skipped,
        "chunks_created": len(all_chunks),
        "avg_tokens_per_chunk": avg_tokens,
    }
