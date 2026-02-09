from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from ..config import Settings

logger = logging.getLogger(__name__)

# Matches http:// and https:// URLs, stopping at whitespace and common delimiters.
# Parentheses are allowed so Wikipedia-style URLs like /wiki_(topic) are captured;
# unmatched trailing ')' is stripped by _clean_url().
_URL_RE = re.compile(r"https?://[^\s<>\"'\]\},;]+")

# Trailing punctuation that is almost never part of a real URL
_TRAILING_JUNK = re.compile(r"[.,;:!?]+$")


def _clean_url(raw: str) -> str:
    """Strip trailing punctuation and unmatched parentheses from a raw URL match."""
    url = _TRAILING_JUNK.sub("", raw)
    # Handle unmatched trailing parenthesis: if ')' count exceeds '(' count, trim
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    return url


def extract_urls(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Extract and aggregate URLs mentioned in item TEXT fields.

    Pure regex — no LLM, no network calls, no optional deps.

    Returns list of dicts with keys:
    VIDEO_ID, ASSET_TYPE, URL, DOMAIN, MENTION_COUNT, FIRST_SEEN_ITEM_ID
    """
    if not items:
        return []

    # url -> {count, first_seen_item_id}
    agg: dict[str, dict] = {}

    for item in items:
        text = item.get("TEXT", "")
        if not text:
            continue

        # Resolve item ID: COMMENT_ID for comments, CHUNK_INDEX for transcripts
        item_id = item.get("COMMENT_ID") or str(item.get("CHUNK_INDEX", ""))

        for match in _URL_RE.finditer(text):
            url = _clean_url(match.group())
            if not url:
                continue
            if url in agg:
                agg[url]["count"] += 1
            else:
                agg[url] = {"count": 1, "first_seen_item_id": item_id}

    results: list[dict] = []
    for url, info in agg.items():
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ""
        results.append({
            "VIDEO_ID": video_id,
            "ASSET_TYPE": asset_type,
            "URL": url,
            "DOMAIN": domain,
            "MENTION_COUNT": info["count"],
            "FIRST_SEEN_ITEM_ID": info["first_seen_item_id"],
        })

    # Sort by mention count descending
    results.sort(key=lambda r: r["MENTION_COUNT"], reverse=True)
    return results
