from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    """Outcome of a ``run_all()`` invocation."""

    run_id: str
    output_dir: Path
    videos_processed: int = 0
    comments_collected: int = 0
    transcript_chunks: int = 0
    output_files: list[Path] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)


@dataclass
class PreflightResult:
    """Outcome of ``run_preflight()``."""

    ok: bool
    results: list[dict] = field(default_factory=list)
    report_path: Path | None = None
