from __future__ import annotations

import logging
import random

from ..config import Settings
from .llm_client import chat_completion, parse_json_response

logger = logging.getLogger(__name__)


def extract_topics_llm(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Extract topics using an LLM.

    Samples items per config limits, sends to LLM for topic extraction.

    Returns:
        List of topic dicts with keys:
        VIDEO_ID, ASSET_TYPE, TOPIC_ID, LABEL, KEYWORDS, REPRESENTATIVE_TEXTS, SCORE
    """
    if not items:
        return []

    # Sample items per config limits
    if asset_type == "comments":
        max_items = cfg.TOPIC_SAMPLING_MAX_COMMENTS_PER_VIDEO
    else:
        max_items = cfg.TOPIC_SAMPLING_MAX_TRANSCRIPT_CHUNKS_PER_VIDEO

    sampled = items if len(items) <= max_items else random.sample(items, max_items)
    texts = [item.get("TEXT", "") for item in sampled]
    texts = [t for t in texts if t.strip()]

    if not texts:
        return []

    n_topics = min(10, len(texts) // 20 + 1)
    n_topics = max(1, n_topics)

    # Build prompt with numbered items
    numbered = "\n".join(f"[{i}] {t[:500]}" for i, t in enumerate(texts))
    messages = [
        {
            "role": "system",
            "content": (
                "You are a topic extraction assistant. Analyze the provided texts "
                "and identify the main topics. Return ONLY valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyze these {len(texts)} texts and identify up to {n_topics} main topics.\n\n"
                f"{numbered}\n\n"
                "Return JSON in this exact format:\n"
                '{"topics": [\n'
                '  {"label": "short topic label", "keywords": ["kw1", "kw2", ...], '
                '"representative_indices": [0, 1, 2], "score": 0.35}\n'
                "]}\n\n"
                "- label: a short descriptive name for the topic\n"
                "- keywords: 3-10 relevant keywords\n"
                "- representative_indices: indices of 1-3 most representative texts\n"
                "- score: estimated proportion of texts belonging to this topic (0.0-1.0)\n"
                "- scores should sum to approximately 1.0"
            ),
        },
    ]

    logger.info(
        "Extracting topics via LLM (%d texts, up to %d topics)", len(texts), n_topics
    )

    try:
        raw = chat_completion(cfg, messages, temperature=0.3, max_tokens=2048)
        parsed = parse_json_response(raw)
    except Exception:
        logger.warning("LLM topic extraction failed for %s/%s — returning []", video_id, asset_type, exc_info=True)
        return []

    topics = parsed.get("topics", []) if isinstance(parsed, dict) else []

    results: list[dict] = []
    for topic_id, topic in enumerate(topics):
        rep_indices = topic.get("representative_indices", [])
        rep_texts = [
            texts[i][:200] for i in rep_indices if isinstance(i, int) and 0 <= i < len(texts)
        ]

        results.append({
            "VIDEO_ID": video_id,
            "ASSET_TYPE": asset_type,
            "TOPIC_ID": topic_id,
            "LABEL": topic.get("label", f"Topic {topic_id}"),
            "KEYWORDS": topic.get("keywords", []),
            "REPRESENTATIVE_TEXTS": rep_texts,
            "SCORE": round(float(topic.get("score", 0)), 4),
        })

    return results
