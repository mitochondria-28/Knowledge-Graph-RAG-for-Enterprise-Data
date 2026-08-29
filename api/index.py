"""Vercel Python serverless entry point — re-exports the FastAPI ASGI app."""

import sys
from pathlib import Path

# Make project root importable from inside api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.app import app  # noqa: E402, F401  — Vercel detects ASGI via 'app'
