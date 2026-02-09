from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def resolve_search_videos(
    term: str,
    max_videos: int,
    cfg: Any,
) -> list[dict[str, str]]:
    """Search YouTube for videos matching *term* using yt-dlp ``ytsearch``.

    Uses ``extract_flat`` mode so no actual downloads happen.

    Returns a list of dicts: ``{"VIDEO_URL": ..., "VIDEO_ID": ..., "TITLE": ..., "SEARCH_TERM": term}``.
    """
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "yt-dlp is required for search-term discovery. "
            "Install with: pip install yt-content-analyzer[scrape]"
        )

    search_url = f"ytsearch{max_videos}:{term}"
    logger.info("Searching YouTube for %r (max %d videos)", term, max_videos)

    max_retries = getattr(cfg, "MAX_RETRY_SCRAPE", 3)
    backoff_base = getattr(cfg, "BACKOFF_BASE_SECONDS", 2.0)
    backoff_max = getattr(cfg, "BACKOFF_MAX_SECONDS", 60.0)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    info: dict | None = None
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=False)
            break
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                jitter = random.uniform(0, delay * 0.25)
                logger.warning(
                    "yt-dlp search attempt %d/%d failed for %r: %s — retrying in %.1fs",
                    attempt, max_retries, term, exc, delay + jitter,
                )
                time.sleep(delay + jitter)
            else:
                logger.error(
                    "yt-dlp exhausted %d retries for search %r: %s",
                    max_retries, term, exc,
                )
                raise

    if last_err and not info:
        raise last_err  # type: ignore[union-attr]

    entries = info.get("entries", []) if info else []  # type: ignore[union-attr]
    results: list[dict[str, str]] = []
    for entry in entries:
        if not entry:
            continue
        vid_id = entry.get("id", "")
        title = entry.get("title", "")
        if vid_id:
            results.append({
                "VIDEO_URL": f"https://www.youtube.com/watch?v={vid_id}",
                "VIDEO_ID": vid_id,
                "TITLE": title,
                "SEARCH_TERM": term,
            })

    logger.info("Search %r resolved %d videos", term, len(results))
    return results
