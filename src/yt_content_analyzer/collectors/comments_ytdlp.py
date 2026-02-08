from __future__ import annotations

from typing import Any

from ..config import Settings
from ..utils.logger import get_logger


def collect_comments_ytdlp(video_url: str, cfg: Settings) -> list[dict[str, Any]]:
    """Collect comments for a single video via yt-dlp.

    Returns raw comment list from yt-dlp's info dict.
    """
    import yt_dlp

    logger = get_logger()

    max_comments = cfg.MAX_COMMENTS_PER_VIDEO

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {
            "youtube": {
                "max_comments": [
                    str(max_comments),  # top-level limit
                    "0",                # max replies per comment (0 = all)
                    str(max_comments),  # total limit
                    "0",                # max reply-of-reply
                ],
            }
        },
        "quiet": True,
        "no_warnings": True,
    }

    logger.info("Collecting comments via yt-dlp for %s (max=%d)", video_url, max_comments)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    comments: list[dict[str, Any]] = info.get("comments") or []
    logger.info("Collected %d comments for %s", len(comments), info.get("id", video_url))

    return comments
