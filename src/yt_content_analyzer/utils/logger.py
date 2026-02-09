from __future__ import annotations

import json
import logging
import traceback
import warnings
from datetime import datetime, timezone
from pathlib import Path

_STANDARD_LOG_ATTRS = frozenset({
    "name", "msg", "args", "created", "relativeCreated", "exc_info", "exc_text",
    "stack_info", "lineno", "funcName", "levelno", "levelname", "pathname",
    "filename", "module", "thread", "threadName", "process", "processName",
    "message", "msecs", "taskName",
})


class JsonLineFormatter(logging.Formatter):
    """Formats log records as one-JSON-object-per-line."""

    def format(self, record: logging.LogRecord) -> str:
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_LOG_ATTRS and not k.startswith("_")
        }
        obj: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "extra": extra,
        }
        if record.exc_info and record.exc_info[0] is not None:
            obj["traceback"] = traceback.format_exception(*record.exc_info)
        return json.dumps(obj, default=str)


def get_logger() -> logging.Logger:
    """Deprecated: use ``logging.getLogger(__name__)`` instead."""
    warnings.warn(
        "get_logger() is deprecated, use logging.getLogger(__name__) instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return logging.getLogger("yt_content_analyzer")


def setup_file_handler(logger: logging.Logger, log_dir: Path) -> None:
    """Add a JSON-lines file handler writing to *log_dir*/run.log at DEBUG level.

    Idempotent: checks for existing handler before adding.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run.log"

    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and h.baseFilename == str(log_path):
            return

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JsonLineFormatter())
    logger.addHandler(fh)


def configure_file_logging(log_dir: Path) -> None:
    """Backward-compatible shim — delegates to :func:`setup_file_handler`."""
    setup_file_handler(logging.getLogger("yt_content_analyzer"), log_dir)


def setup_cli_logging(*, verbosity: int = 0) -> None:
    """Attach a RichHandler to the ``yt_content_analyzer`` logger.

    Called from CLI entry-points only.

    *verbosity* mapping:
    - ``-1`` (quiet) → WARNING
    - ``0``          → INFO
    - ``1+`` (verbose) → DEBUG
    """
    from rich.logging import RichHandler

    level_map = {-1: logging.WARNING, 0: logging.INFO}
    level = level_map.get(verbosity, logging.DEBUG)

    logger = logging.getLogger("yt_content_analyzer")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate Rich handlers on repeated calls
    for h in logger.handlers:
        if isinstance(h, RichHandler):
            return

    handler = RichHandler(rich_tracebacks=True, markup=True)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
