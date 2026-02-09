from __future__ import annotations

import logging

from ..config import Settings
from .llm_client import chat_completion, parse_json_response

logger = logging.getLogger(__name__)


def analyze_sentiment_nlp(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Analyze sentiment using TextBlob (NLP fallback).

    Returns list of dicts with keys:
    VIDEO_ID, ASSET_TYPE, ITEM_ID, POLARITY, SCORE, TEXT_EXCERPT
    """
    from textblob import TextBlob

    results: list[dict] = []
    for item in items:
        text = item.get("TEXT", "")
        if not text.strip():
            continue

        blob = TextBlob(text)
        score = round(blob.sentiment.polarity, 4)

        if score > 0.1:
            polarity = "positive"
        elif score < -0.1:
            polarity = "negative"
        else:
            polarity = "neutral"

        item_id = item.get("COMMENT_ID") or item.get("CHUNK_INDEX", "")

        results.append({
            "VIDEO_ID": video_id,
            "ASSET_TYPE": asset_type,
            "ITEM_ID": str(item_id),
            "POLARITY": polarity,
            "SCORE": score,
            "TEXT_EXCERPT": text[:200],
        })

    return results


def analyze_sentiment_llm(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Analyze sentiment using an LLM.

    Batches items in groups of 50, asks LLM to classify polarity and score.

    Returns list of dicts with keys:
    VIDEO_ID, ASSET_TYPE, ITEM_ID, POLARITY, SCORE, TEXT_EXCERPT
    """
    if not items:
        return []

    batch_size = 50
    results: list[dict] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        batch_items = []
        for item in batch:
            text = item.get("TEXT", "")
            if not text.strip():
                continue
            item_id = item.get("COMMENT_ID") or item.get("CHUNK_INDEX", "")
            batch_items.append({"id": str(item_id), "text": text[:500]})

        if not batch_items:
            continue

        numbered = "\n".join(
            f'[{bi["id"]}] {bi["text"]}' for bi in batch_items
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a sentiment analysis assistant. Analyze the sentiment of each text. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Classify the sentiment of each text below.\n\n"
                    f"{numbered}\n\n"
                    "Return JSON in this exact format:\n"
                    '{"results": [\n'
                    '  {"id": "item_id", "polarity": "positive|negative|neutral", '
                    '"score": 0.85}\n'
                    "]}\n\n"
                    "- polarity: positive, negative, or neutral\n"
                    "- score: confidence from -1.0 (most negative) to 1.0 (most positive)"
                ),
            },
        ]

        logger.info(
            "Sentiment LLM batch %d-%d of %d",
            batch_start, batch_start + len(batch_items), len(items),
        )

        try:
            raw = chat_completion(cfg, messages, temperature=0.1, max_tokens=2048)
            parsed = parse_json_response(raw)
        except Exception:
            logger.warning(
                "Sentiment LLM batch %d failed for %s/%s — skipping batch",
                batch_start, video_id, asset_type, exc_info=True,
            )
            continue
        llm_results = parsed.get("results", []) if isinstance(parsed, dict) else []

        # Build lookup for IDs
        text_lookup = {bi["id"]: bi["text"] for bi in batch_items}

        for r in llm_results:
            rid = str(r.get("id", ""))
            results.append({
                "VIDEO_ID": video_id,
                "ASSET_TYPE": asset_type,
                "ITEM_ID": rid,
                "POLARITY": r.get("polarity", "neutral"),
                "SCORE": round(float(r.get("score", 0)), 4),
                "TEXT_EXCERPT": text_lookup.get(rid, "")[:200],
            })

    return results


def analyze_sentiment(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Dispatch sentiment analysis: LLM if configured, NLP fallback otherwise."""
    if not items:
        return []

    if cfg.LLM_PROVIDER:
        logger.info("Sentiment analysis via LLM (provider=%s)", cfg.LLM_PROVIDER)
        return analyze_sentiment_llm(items, video_id, asset_type, cfg)
    else:
        logger.info("Sentiment analysis via NLP (TextBlob)")
        return analyze_sentiment_nlp(items, video_id, asset_type, cfg)
