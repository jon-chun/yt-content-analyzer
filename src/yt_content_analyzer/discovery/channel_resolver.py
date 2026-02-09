from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_channel_url(channel: str) -> str:
    """Normalize a channel handle, ID, or URL to a full /videos URL.

    Accepts:
      - ``@handle`` (e.g. ``@engineerprompt``)
      - ``UC...`` channel IDs
      - Full URLs (``https://www.youtube.com/@handle``)
    """
    channel = channel.strip()

    if channel.startswith(("https://", "http://")):
        url = channel.rstrip("/")
        if not url.endswith("/videos"):
            url += "/videos"
        return url

    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}/videos"

    if channel.startswith("UC"):
        return f"https://www.youtube.com/channel/{channel}/videos"

    # Assume it's a handle without @
    return f"https://www.youtube.com/@{channel}/videos"


def resolve_channel_videos(
    channel: str,
    max_videos: int,
    cfg: Any,
) -> list[dict[str, str]]:
    """Resolve the latest *max_videos* video IDs from a YouTube channel.

    Uses yt-dlp's ``extract_flat`` mode to list videos on the channel page
    without downloading them.

    Returns a list of dicts: ``{"VIDEO_URL": ..., "VIDEO_ID": ..., "TITLE": ...}``.
    """
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "yt-dlp is required for subscription mode. "
            "Install with: pip install yt-content-analyzer[scrape]"
        )

    channel_url = _normalize_channel_url(channel)
    logger.info("Resolving videos from %s (max %d)", channel_url, max_videos)

    max_retries = getattr(cfg, "MAX_RETRY_SCRAPE", 3)
    backoff_base = getattr(cfg, "BACKOFF_BASE_SECONDS", 2.0)
    backoff_max = getattr(cfg, "BACKOFF_MAX_SECONDS", 60.0)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": max_videos,
    }

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
            break
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                jitter = random.uniform(0, delay * 0.25)
                logger.warning(
                    "yt-dlp attempt %d/%d failed for %s: %s — retrying in %.1fs",
                    attempt, max_retries, channel_url, exc, delay + jitter,
                )
                time.sleep(delay + jitter)
            else:
                logger.error(
                    "yt-dlp exhausted %d retries for %s: %s",
                    max_retries, channel_url, exc,
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
            })

    logger.info("Resolved %d videos from %s", len(results), channel)
    return results
