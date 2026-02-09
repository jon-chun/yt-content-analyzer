from __future__ import annotations
import json
import logging
import traceback as tb_mod
from datetime import datetime, timezone
from pathlib import Path
import csv
import re
from typing import Iterable, Mapping, Any


_logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict]:
    """Read all rows from a JSONL file. Returns [] if file doesn't exist.

    Skips lines that cannot be parsed as JSON, logging a warning.
    """
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    _logger.warning("Skipping bad JSON at %s:%d", path, line_no)
    return rows


def write_jsonl(
    path: Path, rows: Iterable[Mapping[str, Any]], *, mode: str = "a",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: list[str],
    *,
    mode: str = "a",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = mode == "w" or not path.exists()
    with path.open(mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def write_failure(
    failures_dir: Path, stage: str, video_id: str, error: BaseException,
) -> Path:
    """Write a failure record to failures/<stage>_<video_id>.json.

    Returns the path of the written file.
    """
    failures_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^\w\-]", "_", video_id)
    filename = f"{stage}_{safe_id}.json"
    path = failures_dir / filename
    record = {
        "stage": stage,
        "video_id": video_id,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": tb_mod.format_exception(type(error), error, error.__traceback__),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
