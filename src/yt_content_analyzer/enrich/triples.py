from __future__ import annotations

import logging

from ..config import Settings
from .llm_client import chat_completion, parse_json_response

logger = logging.getLogger(__name__)


def extract_triples(
    items: list[dict],
    video_id: str,
    asset_type: str,
    cfg: Settings,
) -> list[dict]:
    """Extract subject-predicate-object triples using an LLM.

    LLM-only: returns [] with a warning if no LLM provider is configured.
    Batches items in groups of 20.

    Returns list of dicts with keys:
    VIDEO_ID, ASSET_TYPE, SUBJECT, PREDICATE, OBJECT, CONFIDENCE, SOURCE_TEXT
    """
    if not items:
        return []

    if not cfg.LLM_PROVIDER:
        logger.warning("Triples extraction requires LLM_PROVIDER — skipping (no provider configured)")
        return []

    batch_size = 20
    results: list[dict] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        batch_texts: list[dict[str, str]] = []
        for item in batch:
            text = item.get("TEXT", "")
            if not text.strip():
                continue
            batch_texts.append({"index": str(batch_start + len(batch_texts)), "text": text[:500]})

        if not batch_texts:
            continue

        numbered = "\n".join(f'[{bt["index"]}] {bt["text"]}' for bt in batch_texts)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a knowledge extraction assistant. Extract factual "
                    "subject-predicate-object triples from the provided texts. "
                    "Return ONLY valid JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Extract knowledge triples from these texts.\n\n"
                    f"{numbered}\n\n"
                    "Return JSON in this exact format:\n"
                    '{"triples": [\n'
                    '  {"subject": "entity", "predicate": "relation", "object": "entity", '
                    '"confidence": 0.9, "source_index": 0}\n'
                    "]}\n\n"
                    "- subject: the subject entity\n"
                    "- predicate: the relationship\n"
                    "- object: the object entity\n"
                    "- confidence: 0.0-1.0 confidence score\n"
                    "- source_index: index of the source text"
                ),
            },
        ]

        logger.info(
            "Triples LLM batch %d-%d of %d",
            batch_start, batch_start + len(batch_texts), len(items),
        )

        try:
            raw = chat_completion(cfg, messages, temperature=0.2, max_tokens=2048)
            parsed = parse_json_response(raw)
        except Exception:
            logger.warning(
                "Triples LLM batch %d failed for %s/%s — skipping batch",
                batch_start, video_id, asset_type, exc_info=True,
            )
            continue
        triples = parsed.get("triples", []) if isinstance(parsed, dict) else []

        # Build text lookup for source_index
        text_lookup = {int(bt["index"]): bt["text"] for bt in batch_texts}

        for triple in triples:
            source_idx = triple.get("source_index")
            source_text = ""
            if isinstance(source_idx, int) and source_idx in text_lookup:
                source_text = text_lookup[source_idx][:200]

            results.append({
                "VIDEO_ID": video_id,
                "ASSET_TYPE": asset_type,
                "SUBJECT": triple.get("subject", ""),
                "PREDICATE": triple.get("predicate", ""),
                "OBJECT": triple.get("object", ""),
                "CONFIDENCE": round(float(triple.get("confidence", 0)), 4),
                "SOURCE_TEXT": source_text,
            })

    return results
