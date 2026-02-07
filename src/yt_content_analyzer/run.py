from __future__ import annotations
import os, json, time
from pathlib import Path
from dataclasses import asdict
from .config import Settings
from .preflight.checks import run_preflight
from .utils.logger import get_logger
from .state.checkpoint import CheckpointStore

def _new_run_id() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def run_all(cfg: Settings) -> None:
    logger = get_logger()
    run_id = _new_run_id()
    out_dir = Path("runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # preflight
    ok = run_preflight(cfg, output_dir=out_dir)
    if not ok:
        raise SystemExit(2)

    # manifest snapshot
    (out_dir / "logs").mkdir(exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(cfg.model_dump(), indent=2), encoding="utf-8")

    # state
    ckpt = CheckpointStore(out_dir / "state" / "checkpoint.json")
    ckpt.init_if_missing()

    logger.info("Run started", extra={"RUN_ID": run_id, "OUTPUT_DIR": str(out_dir)})

    # TODO: implement discover -> collect comments+transcripts -> enrich -> report
    logger.warning("Pipeline not yet implemented in this scaffold. See docs/tech-spec.md for full implementation details.")
