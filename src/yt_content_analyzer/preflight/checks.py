from __future__ import annotations
from pathlib import Path
from typing import Optional
import json
from ..config import Settings
from ..utils.logger import get_logger

def run_preflight(cfg: Settings, output_dir: Optional[Path]) -> bool:
    """Run multi-level preflight checks. Writes a markdown report under reports/ when output_dir is provided."""
    logger = get_logger()
    results = []

    def record(level: int, name: str, ok: bool, detail: str = "") -> None:
        results.append({"LEVEL": level, "NAME": name, "OK": ok, "DETAIL": detail})

    # LEVEL 0: config invariants
    ok0 = True
    if cfg.VIDEO_URL and cfg.SEARCH_TERMS:
        ok0 = False
        record(0, "Mutually exclusive inputs", False, "Provide VIDEO_URL or SEARCH_TERMS, not both.")
    if (cfg.SEARCH_TERMS or []) and cfg.MAX_VIDEOS_PER_TERM > 10:
        ok0 = False
        record(0, "MAX_VIDEOS_PER_TERM cap", False, "Must be <= 10.")
    if cfg.MAX_TOTAL_VIDEOS > 500:
        ok0 = False
        record(0, "MAX_TOTAL_VIDEOS cap", False, "Must be <= 500.")
    record(0, "Config invariants", ok0, "Basic caps and invariants checked.")

    # Placeholder for LEVEL 1-5 checks (Playwright availability, endpoint probes, etc.)
    record(1, "Local environment readiness", True, "Scaffold: implement Playwright/browser checks.")
    record(2, "Endpoint reachability", True, "Scaffold: implement translation/embeddings reachability checks.")
    record(3, "Probe calls", True, "Scaffold: implement schema probe calls for APIs.")
    record(4, "Transcript provider probe", True, "Scaffold: implement provider readiness checks.")
    record(5, "Rate limit sanity", True, "Scaffold: implement preset sanity checks.")

    ok = all(r["OK"] for r in results if r["LEVEL"] in (0,))
    # Persist report
    if output_dir:
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        md = ["# Preflight Report", ""]
        for r in results:
            status = "PASS" if r["OK"] else "FAIL"
            md.append(f"- L{r['LEVEL']} [{status}] **{r['NAME']}** — {r['DETAIL']}")
        (reports_dir / f"preflight_{output_dir.name}.md").write_text("\n".join(md)+"\n", encoding="utf-8")
        (reports_dir / f"preflight_{output_dir.name}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    if not ok:
        logger.error("Preflight failed. See reports/preflight_*.md for details.")
    else:
        logger.info("Preflight passed (L0 strict).")
    return ok
