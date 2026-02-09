from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import Settings


def normalize_comments(
    raw_comments: list[dict[str, Any]],
    video_id: str,
    cfg: Settings,
    sort_mode: str = "default",
) -> list[dict[str, Any]]:
    """Normalize raw comments to the canonical schema.

    Schema fields: VIDEO_ID, COMMENT_ID, PARENT_ID, AUTHOR, TEXT,
                   LIKE_COUNT, REPLY_COUNT, PUBLISHED_AT, SORT_MODE, THREAD_DEPTH

    Supports raw dicts from both Playwright and yt-dlp collectors.
    """
    normalized: list[dict[str, Any]] = []

    for comment in raw_comments:
        parent_id = comment.get("parent", "root")
        if parent_id == "root":
            parent_id = ""
            thread_depth = 0
        else:
            thread_depth = 1

        # Convert unix timestamp to ISO 8601
        timestamp = comment.get("timestamp")
        if timestamp is not None:
            published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        else:
            published_at = ""

        normalized.append({
            "VIDEO_ID": video_id,
            "COMMENT_ID": comment.get("id", ""),
            "PARENT_ID": parent_id,
            "AUTHOR": comment.get("author", ""),
            "TEXT": comment.get("text", ""),
            "LIKE_COUNT": comment.get("like_count", 0) or 0,
            "REPLY_COUNT": comment.get("reply_count", 0) or 0,
            "PUBLISHED_AT": published_at,
            "SORT_MODE": sort_mode,
            "THREAD_DEPTH": thread_depth,
        })

    return normalized
