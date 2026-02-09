from __future__ import annotations

import logging
from typing import Any

from ..config import Settings

logger = logging.getLogger(__name__)


def chunk_transcripts(
    segments: list[dict[str, Any]], cfg: Settings
) -> list[dict[str, Any]]:
    """Chunk normalized transcript segments into time-based sliding windows.

    Uses TRANSCRIPT_CHUNK_SECONDS as window width and
    TRANSCRIPT_CHUNK_OVERLAP_SECONDS as overlap between consecutive chunks.

    Schema: VIDEO_ID, CHUNK_INDEX, START_S, END_S, TEXT, SEGMENT_INDICES, OVERLAP_S
    """
    if not segments:
        return []

    window_s = cfg.TRANSCRIPT_CHUNK_SECONDS
    overlap_s = cfg.TRANSCRIPT_CHUNK_OVERLAP_SECONDS
    video_id = segments[0]["VIDEO_ID"]

    # Find the time range
    min_start = segments[0]["START_S"]
    max_end = max(seg["END_S"] for seg in segments)

    chunks: list[dict[str, Any]] = []
    chunk_start = min_start
    chunk_index = 0
    step = window_s - overlap_s
    if step <= 0:
        logger.warning(
            "TRANSCRIPT_CHUNK_OVERLAP_SECONDS (%d) >= TRANSCRIPT_CHUNK_SECONDS (%d); "
            "falling back to non-overlapping chunks",
            overlap_s, window_s,
        )
        step = window_s
        overlap_s = 0

    while chunk_start < max_end:
        chunk_end = chunk_start + window_s

        # Collect segments that overlap with this window
        included_indices: list[int] = []
        texts: list[str] = []

        for seg in segments:
            seg_start = seg["START_S"]
            seg_end = seg["END_S"]
            # Segment overlaps with window if it starts before window ends
            # and ends after window starts
            if seg_start < chunk_end and seg_end > chunk_start:
                included_indices.append(seg["SEGMENT_INDEX"])
                texts.append(seg["TEXT"])

        if texts:
            actual_end = min(chunk_end, max_end)
            actual_overlap = overlap_s if chunk_index > 0 else 0.0

            chunks.append({
                "VIDEO_ID": video_id,
                "CHUNK_INDEX": chunk_index,
                "START_S": round(chunk_start, 3),
                "END_S": round(actual_end, 3),
                "TEXT": " ".join(texts),
                "SEGMENT_INDICES": included_indices,
                "OVERLAP_S": round(actual_overlap, 3),
            })
            chunk_index += 1

        chunk_start += step

    return chunks
