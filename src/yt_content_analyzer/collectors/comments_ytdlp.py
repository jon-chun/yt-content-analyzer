from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings

logger = logging.getLogger(__name__)


def collect_comments_ytdlp(video_url: str, cfg: Settings) -> list[dict[str, Any]]:
    """Collect comments for a single video via yt-dlp.

    Returns raw comment list from yt-dlp's info dict.
    Retries on failure with exponential backoff.
    """
    import yt_dlp

    max_comments = cfg.MAX_COMMENTS_PER_VIDEO
    max_thread_depth = cfg.MAX_COMMENT_THREAD_DEPTH

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {
                "max_comments": [
                    str(max_comments),       # top-level limit
                    str(max_thread_depth),   # max replies per top-level comment
                    str(max_comments),       # total limit
                    str(max_thread_depth),   # max reply-of-reply depth
                ],
            }
        },
        "quiet": True,
        "no_warnings": True,
    }

    logger.info("Collecting comments via yt-dlp for %s (max=%d)", video_url, max_comments)

    max_retries = cfg.MAX_RETRY_SCRAPE
    backoff = cfg.BACKOFF_BASE_SECONDS

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            break
        except Exception as exc:
            if attempt < max_retries:
                wait = min(backoff * (2 ** attempt), cfg.BACKOFF_MAX_SECONDS)
                logger.warning(
                    "yt-dlp comments attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_retries + 1, exc, wait,
                )
                time.sleep(wait)
                continue
            logger.error("yt-dlp comments exhausted %d retries for %s", max_retries + 1, video_url)
            raise

    comments: list[dict[str, Any]] = info.get("comments") or []
    logger.info("Collected %d comments for %s", len(comments), info.get("id", video_url))

    return comments
