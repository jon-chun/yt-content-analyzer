from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..models import PreflightResult

logger = logging.getLogger(__name__)


def run_preflight(cfg: Settings, output_dir: Optional[Path]) -> PreflightResult:
    """Run multi-level preflight checks.

    Writes a markdown report under reports/ when *output_dir* is provided.
    Returns a :class:`PreflightResult` whose ``.ok`` attribute indicates pass/fail.
    """
    results: list[dict] = []

    def record(level: int, name: str, ok: bool, detail: str = "") -> None:
        results.append({"LEVEL": level, "NAME": name, "OK": ok, "DETAIL": detail})

    # LEVEL 0: config invariants
    ok0 = True
    input_modes = sum([
        bool(cfg.VIDEO_URL),
        bool(cfg.SEARCH_TERMS),
        bool(cfg.YT_SUBSCRIPTIONS),
    ])
    if input_modes > 1:
        ok0 = False
        record(
            0, "Mutually exclusive inputs", False,
            "Provide exactly one of VIDEO_URL, SEARCH_TERMS, or YT_SUBSCRIPTIONS.",
        )
    if cfg.YT_SUBSCRIPTIONS:
        total_sub_videos = sum(
            entry.get("MAX_SUB_VIDEOS", cfg.MAX_SUB_VIDEOS)
            for entry in cfg.YT_SUBSCRIPTIONS
        )
        if total_sub_videos > cfg.MAX_TOTAL_VIDEOS:
            ok0 = False
            record(
                0, "Subscription video cap", False,
                f"Total subscription videos ({total_sub_videos}) exceeds "
                f"MAX_TOTAL_VIDEOS ({cfg.MAX_TOTAL_VIDEOS}).",
            )
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
    report_path: Path | None = None
    if output_dir:
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        md = ["# Preflight Report", ""]
        for r in results:
            status = "PASS" if r["OK"] else "FAIL"
            md.append(f"- L{r['LEVEL']} [{status}] **{r['NAME']}** — {r['DETAIL']}")
        report_path = reports_dir / f"preflight_{output_dir.name}.md"
        report_path.write_text("\n".join(md) + "\n", encoding="utf-8")
        (reports_dir / f"preflight_{output_dir.name}.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )

    if not ok:
        logger.error("Preflight failed. See reports/preflight_*.md for details.")
    else:
        logger.info("Preflight passed (L0 strict).")

    return PreflightResult(ok=ok, results=results, report_path=report_path)
