from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .config import Settings
from .preflight.checks import run_preflight
from .utils.logger import get_logger
from .utils.io import read_jsonl, write_jsonl
from .state.checkpoint import CheckpointStore


def _new_run_id() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats.

    Supports:
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://youtube.com/watch?v=VIDEO_ID
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - https://www.youtube.com/v/VIDEO_ID

    Raises ValueError if no video ID can be extracted.
    """
    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([\w-]{11})",
        r"(?:youtu\.be/)([\w-]{11})",
        r"(?:youtube\.com/embed/)([\w-]{11})",
        r"(?:youtube\.com/v/)([\w-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Cannot extract video ID from URL: {url}")


def run_all(cfg: Settings) -> None:
    logger = get_logger()
    run_id = _new_run_id()
    out_dir = Path("runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # preflight
    ok = run_preflight(cfg, output_dir=out_dir)
    if not ok:
        raise SystemExit(2)

    # manifest snapshot
    (out_dir / "logs").mkdir(exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(cfg.model_dump(), indent=2), encoding="utf-8")

    # state
    ckpt = CheckpointStore(out_dir / "state" / "checkpoint.json")
    ckpt.init_if_missing()

    logger.info("Run started", extra={"RUN_ID": run_id, "OUTPUT_DIR": str(out_dir)})

    # --- Single-video collection pipeline ---
    if cfg.VIDEO_URL:
        video_id = extract_video_id(cfg.VIDEO_URL)
        unit_key = video_id

        _collect_and_process_transcript(cfg, video_id, out_dir, ckpt, unit_key, logger)
        _collect_and_process_comments(cfg, video_id, out_dir, ckpt, unit_key, logger)
        _enrich_video(cfg, video_id, out_dir, ckpt, unit_key, logger)

        logger.info("Pipeline complete for video %s", video_id)
    else:
        logger.warning(
            "No VIDEO_URL set. Discovery-based pipeline not yet implemented."
        )


def _collect_and_process_transcript(cfg, video_id, out_dir, ckpt, unit_key, logger):
    from .collectors.transcript_ytdlp import collect_transcript_ytdlp
    from .parse.normalize_transcripts import normalize_transcripts
    from .parse.chunk_transcripts import chunk_transcripts

    if not cfg.TRANSCRIPTS_ENABLE:
        logger.info("Transcripts disabled, skipping")
        return

    # Collect
    logger.info("Collecting transcript for %s", video_id)
    t0 = time.time()
    raw_transcript = collect_transcript_ytdlp(cfg.VIDEO_URL, cfg)
    logger.info("Transcript collected in %.1fs (%d entries)",
                time.time() - t0, len(raw_transcript.get("entries", [])))
    ckpt.mark(unit_key, "transcript_collect")

    if not raw_transcript.get("entries"):
        logger.warning("No transcript entries for %s", video_id)
        return

    # Normalize
    segments = normalize_transcripts(raw_transcript, video_id, cfg)
    ckpt.mark(unit_key, "transcript_normalize")

    # Write segments
    seg_path = out_dir / "transcripts" / "transcript_segments.jsonl"
    write_jsonl(seg_path, segments)
    logger.info("Wrote %d transcript segments to %s", len(segments), seg_path)

    # Chunk
    chunks = chunk_transcripts(segments, cfg)
    ckpt.mark(unit_key, "transcript_chunk")

    # Write chunks
    chunk_path = out_dir / "transcripts" / "transcript_chunks.jsonl"
    write_jsonl(chunk_path, chunks)
    logger.info("Wrote %d transcript chunks to %s", len(chunks), chunk_path)


def _collect_and_process_comments(cfg, video_id, out_dir, ckpt, unit_key, logger):
    from .collectors.comments_ytdlp import collect_comments_ytdlp
    from .parse.normalize_comments import normalize_comments

    # Collect
    logger.info("Collecting comments for %s", video_id)
    t0 = time.time()
    raw_comments = collect_comments_ytdlp(cfg.VIDEO_URL, cfg)
    logger.info("Comments collected in %.1fs (%d comments)",
                time.time() - t0, len(raw_comments))
    ckpt.mark(unit_key, "comments_collect")

    if not raw_comments:
        logger.warning("No comments for %s", video_id)
        return

    # Normalize
    normalized = normalize_comments(raw_comments, video_id, cfg)
    ckpt.mark(unit_key, "comments_normalize")

    # Write
    comments_path = out_dir / "comments" / "comments.jsonl"
    write_jsonl(comments_path, normalized)
    logger.info("Wrote %d comments to %s", len(normalized), comments_path)


def _enrich_video(cfg, video_id, out_dir, ckpt, unit_key, logger):
    from .enrich.embeddings_client import compute_embeddings
    from .enrich.topics_nlp import extract_topics_nlp
    from .enrich.topics_llm import extract_topics_llm
    from .enrich.sentiment import analyze_sentiment
    from .enrich.triples import extract_triples

    # Read collected data
    comments = read_jsonl(out_dir / "comments" / "comments.jsonl")
    chunks = read_jsonl(out_dir / "transcripts" / "transcript_chunks.jsonl")
    all_items = comments + chunks

    if not all_items:
        logger.warning("No items to enrich for %s", video_id)
        return

    logger.info(
        "Enrichment starting for %s (%d comments, %d chunks)",
        video_id, len(comments), len(chunks),
    )

    enrich_dir = out_dir / "enrich"
    enrich_dir.mkdir(parents=True, exist_ok=True)

    # --- Embeddings (optional, used by NLP topics) ---
    embeddings = None
    if cfg.EMBEDDINGS_ENABLE and not ckpt.is_done(unit_key, "enrich_embeddings"):
        texts = [item.get("TEXT", "") for item in all_items]
        embeddings = compute_embeddings(texts, cfg)
        ckpt.mark(unit_key, "enrich_embeddings")

    # --- Topics ---
    if not ckpt.is_done(unit_key, "enrich_topics"):
        all_topics: list[dict] = []
        for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
            if not items:
                continue
            if cfg.TM_CLUSTERING == "llm":
                topics = extract_topics_llm(items, video_id, asset_type, cfg)
            else:
                asset_embeddings = None
                if embeddings is not None:
                    offset = 0 if asset_type == "comments" else len(comments)
                    asset_embeddings = embeddings[offset : offset + len(items)]
                topics = extract_topics_nlp(items, video_id, asset_type, cfg, asset_embeddings)
            all_topics.extend(topics)

        if all_topics:
            write_jsonl(enrich_dir / "topics.jsonl", all_topics)
            logger.info("Wrote %d topic records to enrich/topics.jsonl", len(all_topics))
        ckpt.mark(unit_key, "enrich_topics")

    # --- Sentiment ---
    if not ckpt.is_done(unit_key, "enrich_sentiment"):
        all_sentiment: list[dict] = []
        for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
            if not items:
                continue
            sentiment = analyze_sentiment(items, video_id, asset_type, cfg)
            all_sentiment.extend(sentiment)

        if all_sentiment:
            write_jsonl(enrich_dir / "sentiment.jsonl", all_sentiment)
            logger.info("Wrote %d sentiment records to enrich/sentiment.jsonl", len(all_sentiment))
        ckpt.mark(unit_key, "enrich_sentiment")

    # --- Triples ---
    if not ckpt.is_done(unit_key, "enrich_triples"):
        all_triples: list[dict] = []
        for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
            if not items:
                continue
            triples = extract_triples(items, video_id, asset_type, cfg)
            all_triples.extend(triples)

        if all_triples:
            write_jsonl(enrich_dir / "triples.jsonl", all_triples)
            logger.info("Wrote %d triple records to enrich/triples.jsonl", len(all_triples))
        ckpt.mark(unit_key, "enrich_triples")
