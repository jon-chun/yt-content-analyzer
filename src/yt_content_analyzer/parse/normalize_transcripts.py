from __future__ import annotations

from typing import Any

from ..config import Settings


def normalize_transcripts(
    raw_transcript: dict[str, Any], video_id: str, cfg: Settings
) -> list[dict[str, Any]]:
    """Normalize raw transcript entries to the canonical schema.

    Schema fields: VIDEO_ID, SEGMENT_INDEX, START_S, END_S, TEXT, SPEAKER, SOURCE, LANG

    Enforces MAX_TRANSCRIPT_CHARS_PER_VIDEO — truncates segments once the limit is hit.
    """
    entries = raw_transcript.get("entries", [])
    source = raw_transcript.get("source", "unknown")
    lang = raw_transcript.get("lang", "")
    max_chars = cfg.MAX_TRANSCRIPT_CHARS_PER_VIDEO

    segments: list[dict[str, Any]] = []
    total_chars = 0

    for i, entry in enumerate(entries):
        text = entry.get("text", "")
        if total_chars + len(text) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 0:
                text = text[:remaining]
            else:
                break

        start = entry.get("start", 0.0)
        duration = entry.get("duration", 0.0)

        segments.append({
            "VIDEO_ID": video_id,
            "SEGMENT_INDEX": i,
            "START_S": round(start, 3),
            "END_S": round(start + duration, 3),
            "TEXT": text,
            "SPEAKER": "",
            "SOURCE": source,
            "LANG": lang,
        })

        total_chars += len(text)
        if total_chars >= max_chars:
            break

    return segments
