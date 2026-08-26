#!/usr/bin/env python3
"""
Start the FastAPI server — Phase 9.

Usage:
    python scripts/serve.py              # default: localhost:8000
    python scripts/serve.py --port 9000
    python scripts/serve.py --reload     # auto-reload on code change (dev only)
    python scripts/serve.py --workers 4  # multiple workers (prod; disables --reload)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
import uvicorn

app = typer.Typer(add_completion=False)


@app.command()
def main(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8000, help="Port to listen on."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file change (dev only)."),
    workers: int = typer.Option(1, help="Number of uvicorn worker processes."),
    log_level: str = typer.Option("info", help="Log level: debug/info/warning/error."),
) -> None:
    """Start the Enterprise KG-RAG FastAPI server."""
    if reload and workers > 1:
        typer.echo("--reload is incompatible with --workers > 1; ignoring --workers", err=True)
        workers = 1

    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
    )


if __name__ == "__main__":
    app()
