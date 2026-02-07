from __future__ import annotations
import logging
from rich.logging import RichHandler

_LOGGER = None

def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("yt-content-analyzer")
    logger.setLevel(logging.INFO)
    handler = RichHandler(rich_tracebacks=True, markup=True)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    _LOGGER = logger
    return logger
