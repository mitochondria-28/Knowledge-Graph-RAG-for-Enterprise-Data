"""
Structured logging — Phase 11.

WHY JSON LOGS:

Plain text logs are convenient for local dev but unqueryable at scale.
JSON logs can be shipped to Datadog, Loki, CloudWatch Logs Insights, etc.
and filtered with: jq '.[] | select(.level == "ERROR")'

DESIGN CHOICES:

- Uses stdlib logging (no new deps) with a custom Formatter that emits JSON
- Every record gets: timestamp (ISO-8601 UTC), level, logger name, message
- Exception tracebacks are inlined as "exc_info" string (keeps the record on one line)
- configure_logging() is idempotent — safe to call multiple times
- In test mode, LOG_FORMAT=text falls back to plain text for readable pytest output

USAGE:

    from src.observability.logging import configure_logging, get_logger

    configure_logging()                # once at process startup
    logger = get_logger(__name__)
    logger.info("Routed question", extra={"strategy": "graph", "hop_depth": 2})
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """
    Emit each log record as a single-line JSON object.

    Fields always present:
      ts        — ISO-8601 UTC timestamp
      level     — DEBUG / INFO / WARNING / ERROR / CRITICAL
      logger    — dotted module name
      msg       — formatted message string
      exc_info  — traceback string (only when an exception is attached)

    Extra fields passed via `extra={}` are merged in at the top level.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Merge any extra fields the caller passed
        _skip = {
            "args", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message",
            "module", "msecs", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "taskName",
            "thread", "threadName",
        }
        for key, val in record.__dict__.items():
            if key not in _skip:
                payload[key] = val

        # Inline exception traceback as a string (keeps record on one line)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """
    Configure the root logger once per process.

    Args:
        level: Override log level string (DEBUG/INFO/WARNING/ERROR).
               Falls back to LOG_LEVEL env var, then INFO.

    Format is controlled by LOG_FORMAT env var:
        json (default) — single-line JSON per record
        text           — stdlib default format (for local dev / pytest)
    """
    effective_level = (
        level
        or os.environ.get("LOG_LEVEL", "INFO")
    ).upper()

    fmt = os.environ.get("LOG_FORMAT", "json").lower()

    root = logging.getLogger()
    if root.handlers:
        # Already configured — update level only
        root.setLevel(effective_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
        )

    root.addHandler(handler)
    root.setLevel(effective_level)

    # Silence noisy third-party loggers
    for noisy in ("anthropic", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Thin wrapper so callers don't import logging directly."""
    return logging.getLogger(name)
