from __future__ import annotations

import logging
import random

from ..config import Settings
from .llm_client import chat_completion, parse_json_response

logger = logging.getLogger(__name__)


def summarize_content(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Summarize a set of items (comments or transcript chunks) using an LLM.

    LLM-only: returns [] with a warning if no LLM provider is configured.
    Returns 0 or 1 dict (one summary per video+asset_type call).

    Output schema:
    VIDEO_ID, ASSET_TYPE, SUMMARY, KEY_THEMES, TONE, ITEM_COUNT, ITEM_COUNT_ANALYZED
    """
    if not items:
        return []

    if not cfg.LLM_PROVIDER:
        logger.warning(
            "Summarization requires LLM_PROVIDER — skipping (no provider configured)"
        )
        return []

    total_count = len(items)
    max_items = cfg.SUMMARY_MAX_ITEMS

    # Sample down if needed
    if len(items) > max_items:
        if asset_type == "transcripts":
            # Stride-based sampling to preserve temporal order
            stride = len(items) / max_items
            items = [items[int(i * stride)] for i in range(max_items)]
        else:
            items = random.sample(items, max_items)

    analyzed_count = len(items)

    # Build numbered text block, each truncated to 500 chars
    numbered_lines: list[str] = []
    for i, item in enumerate(items):
        text = (item.get("TEXT") or "")[:500]
        if text.strip():
            numbered_lines.append(f"[{i}] {text}")

    if not numbered_lines:
        return []

    numbered = "\n".join(numbered_lines)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a content analysis assistant. Summarize the provided texts "
                "and identify key themes and overall tone. Return ONLY valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Summarize these {asset_type} from a YouTube video.\n\n"
                f"{numbered}\n\n"
                "Return JSON in this exact format:\n"
                '{"summary": "...", "key_themes": ["theme1", "theme2", ...], '
                '"tone": "..."}\n\n'
                "- summary: a concise paragraph summarizing the main content\n"
                "- key_themes: list of 3-7 key themes or topics discussed\n"
                "- tone: overall tone (e.g. positive, negative, neutral, mixed, "
                "informative, critical, enthusiastic)"
            ),
        },
    ]

    logger.info(
        "Summarization LLM call for %s/%s (%d items, %d analyzed)",
        video_id, asset_type, total_count, analyzed_count,
    )

    try:
        raw = chat_completion(
            cfg, messages, temperature=0.3, max_tokens=cfg.SUMMARY_MAX_RESPONSE_TOKENS,
        )
        parsed = parse_json_response(raw)
    except Exception:
        logger.warning(
            "Summarization LLM call failed for %s/%s — skipping",
            video_id, asset_type, exc_info=True,
        )
        return []

    if not isinstance(parsed, dict):
        return []

    return [{
        "VIDEO_ID": video_id,
        "ASSET_TYPE": asset_type,
        "SUMMARY": parsed.get("summary", ""),
        "KEY_THEMES": parsed.get("key_themes", []),
        "TONE": parsed.get("tone", ""),
        "ITEM_COUNT": total_count,
        "ITEM_COUNT_ANALYZED": analyzed_count,
    }]
