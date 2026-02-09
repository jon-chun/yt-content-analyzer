from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .exceptions import CollectionError, PreflightError
from .models import RunResult
from .preflight.checks import run_preflight
from .utils.logger import setup_file_handler
from .utils.io import read_jsonl, write_jsonl, write_failure
from .state.checkpoint import CheckpointStore

logger = logging.getLogger(__name__)


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_BARE_VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats or a bare 11-char ID.

    Supports:
      - Bare 11-character video IDs (e.g. ``4jQChe0rg1c``)
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://youtube.com/watch?v=VIDEO_ID
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - https://www.youtube.com/v/VIDEO_ID

    Raises ValueError if no video ID can be extracted.
    """
    url = url.strip()
    if _BARE_VIDEO_ID_RE.match(url):
        return url
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


def _build_video_list(cfg: Settings, out_dir: Path) -> list[dict[str, str]]:
    """Build the list of videos to process based on the input mode.

    Returns a list of dicts with keys: VIDEO_URL, VIDEO_ID, TITLE (optional).
    """
    if cfg.VIDEO_URL:
        video_id = extract_video_id(cfg.VIDEO_URL)
        return [{"VIDEO_URL": cfg.VIDEO_URL, "VIDEO_ID": video_id, "TITLE": ""}]

    if cfg.YT_SUBSCRIPTIONS:
        from .discovery.channel_resolver import resolve_channel_videos

        all_videos: list[dict[str, str]] = []
        for entry in cfg.YT_SUBSCRIPTIONS:
            channel = entry["CHANNEL"]
            max_vids = entry.get("MAX_SUB_VIDEOS", cfg.MAX_SUB_VIDEOS)
            try:
                videos = resolve_channel_videos(channel, max_vids, cfg)
                all_videos.extend(videos)
            except Exception as exc:
                logger.error("Failed to resolve channel %s: %s", channel, exc)
                if cfg.ON_VIDEO_FAILURE == "abort":
                    raise CollectionError(
                        f"Failed to resolve channel {channel}: {exc}"
                    ) from exc

        # Write discovery manifest
        if all_videos:
            disc_path = out_dir / "discovery" / "discovered_videos.jsonl"
            write_jsonl(disc_path, all_videos, mode="w")
            logger.info("Discovered %d videos from %d channels",
                        len(all_videos), len(cfg.YT_SUBSCRIPTIONS))
        return all_videos

    if cfg.SEARCH_TERMS:
        from .discovery.search_resolver import resolve_search_videos

        search_videos: list[dict[str, str]] = []
        for term in cfg.SEARCH_TERMS:
            try:
                videos = resolve_search_videos(term, cfg.MAX_VIDEOS_PER_TERM, cfg)
                search_videos.extend(videos)
            except Exception as exc:
                logger.error("Search failed for term %r: %s", term, exc)
                if cfg.ON_VIDEO_FAILURE == "abort":
                    raise CollectionError(
                        f"Search failed for term {term!r}: {exc}"
                    ) from exc

        # Deduplicate by VIDEO_ID
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for v in search_videos:
            if v["VIDEO_ID"] not in seen:
                seen.add(v["VIDEO_ID"])
                deduped.append(v)
        search_videos = deduped[:cfg.MAX_TOTAL_VIDEOS]

        # Write discovery manifest
        if search_videos:
            disc_path = out_dir / "discovery" / "discovered_videos.jsonl"
            write_jsonl(disc_path, search_videos, mode="w")
            logger.info("Discovered %d videos from %d search terms",
                        len(search_videos), len(cfg.SEARCH_TERMS))
        return search_videos

    # No input mode matched
    return []


def _video_out_dir(out_dir: Path, video_id: str, per_video: bool) -> Path:
    """Return the output directory for a single video's data."""
    if per_video:
        return out_dir / "videos" / video_id
    return out_dir


def run_all(
    cfg: Settings,
    *,
    output_dir: Path | str | None = None,
    resume_run_id: str | None = None,
) -> RunResult:
    """Run the full collection + enrichment pipeline.

    Parameters
    ----------
    cfg:
        Resolved application settings.
    output_dir:
        Base directory for run outputs.  Defaults to ``Path("runs")``.
    resume_run_id:
        If given, resume an existing run instead of starting fresh.

    Returns
    -------
    RunResult
        Summary of what was collected and where outputs live.

    Raises
    ------
    PreflightError
        If preflight checks fail (new runs only).
    """
    base_dir = Path(output_dir) if output_dir is not None else Path("runs")

    if resume_run_id:
        # Validate run_id to prevent path traversal
        if re.search(r"[/\\]|^\.\.", resume_run_id) or ".." in resume_run_id:
            raise ValueError(f"Invalid resume run_id (path traversal attempt): {resume_run_id!r}")
        run_id = resume_run_id
        out_dir = base_dir / run_id
        logger.info("Resuming run %s", run_id)
    else:
        run_id = _new_run_id()
        out_dir = base_dir / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # preflight
        preflight_result = run_preflight(cfg, output_dir=out_dir)
        if not preflight_result.ok:
            raise PreflightError(preflight_result.results)

    result = RunResult(run_id=run_id, output_dir=out_dir)

    # manifest snapshot (always write/overwrite, secrets scrubbed)
    (out_dir / "logs").mkdir(exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    _SECRET_KEYS = {"YOUTUBE_API_KEY"}
    manifest_data = {
        k: ("***" if k in _SECRET_KEYS and v else v)
        for k, v in cfg.model_dump().items()
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # state
    ckpt = CheckpointStore(out_dir / "state" / "checkpoint.json")
    ckpt.init_if_missing()

    # file logging
    setup_file_handler(logging.getLogger("yt_content_analyzer"), out_dir / "logs")

    logger.info("Run started", extra={"RUN_ID": run_id, "OUTPUT_DIR": str(out_dir)})

    failures_dir = out_dir / "failures"

    # --- Build video list ---
    video_list = _build_video_list(cfg, out_dir)

    if not video_list:
        logger.warning(
            "No videos to process. Set VIDEO_URL, SEARCH_TERMS, or YT_SUBSCRIPTIONS."
        )
        return result

    # --- Process each video ---
    for video_entry in video_list:
        video_url = video_entry["VIDEO_URL"]
        video_id = video_entry["VIDEO_ID"]
        _process_single_video(
            cfg, video_url, video_id, out_dir, ckpt, result, failures_dir,
        )

    return result


def _process_single_video(
    cfg, video_url, video_id, out_dir, ckpt, result, failures_dir,
):
    """Run the collection + enrichment pipeline for a single video."""
    unit_key = video_id
    vdir = _video_out_dir(out_dir, video_id, cfg.OUTPUT_PER_VIDEO)
    vfailures = vdir / "failures" if cfg.OUTPUT_PER_VIDEO else failures_dir

    for stage_name, stage_fn in [
        ("transcript", lambda: _collect_and_process_transcript(
            cfg, video_url, video_id, vdir, ckpt, unit_key, result)),
        ("comments", lambda: _collect_and_process_comments(
            cfg, video_url, video_id, vdir, ckpt, unit_key, result, vfailures)),
    ]:
        try:
            stage_fn()
        except Exception as exc:
            logger.exception("Collection stage '%s' failed for %s", stage_name, video_id)
            write_failure(vfailures, stage_name, video_id, exc)
            result.failures.append({
                "stage": stage_name, "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, stage_name, status="FAILED")
            if cfg.ON_VIDEO_FAILURE == "abort":
                raise CollectionError(
                    f"Collection stage '{stage_name}' failed for {video_id}: {exc}"
                ) from exc
            logger.warning("Skipping failed stage '%s' for %s (ON_VIDEO_FAILURE=skip)",
                           stage_name, video_id)

    _enrich_video(cfg, video_id, vdir, ckpt, unit_key, result, vfailures)
    result.videos_processed += 1

    logger.info("Pipeline complete for video %s", video_id)


def _collect_and_process_transcript(
    cfg, video_url, video_id, out_dir, ckpt, unit_key, result,
):
    from .collectors.transcript_ytdlp import collect_transcript_ytdlp
    from .parse.normalize_transcripts import normalize_transcripts
    from .parse.chunk_transcripts import chunk_transcripts

    if not cfg.TRANSCRIPTS_ENABLE:
        logger.info("Transcripts disabled, skipping")
        return

    if ckpt.is_done(unit_key, "transcript_chunk"):
        logger.info("Transcript already processed for %s, skipping", video_id)
        return

    # Collect
    logger.info("Collecting transcript for %s", video_id)
    t0 = time.time()
    raw_transcript = collect_transcript_ytdlp(video_url, cfg)
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
    result.output_files.append(seg_path)
    logger.info("Wrote %d transcript segments to %s", len(segments), seg_path)

    # Chunk
    chunks = chunk_transcripts(segments, cfg)
    ckpt.mark(unit_key, "transcript_chunk")

    # Write chunks
    chunk_path = out_dir / "transcripts" / "transcript_chunks.jsonl"
    write_jsonl(chunk_path, chunks)
    result.output_files.append(chunk_path)
    result.transcript_chunks += len(chunks)
    logger.info("Wrote %d transcript chunks to %s", len(chunks), chunk_path)


def _collect_and_process_comments(
    cfg, video_url, video_id, out_dir, ckpt, unit_key, result, failures_dir,
):
    from .parse.normalize_comments import normalize_comments

    if ckpt.is_done(unit_key, "comments_normalize"):
        logger.info("Comments already processed for %s, skipping", video_id)
        return

    all_normalized = []

    for sort_mode in cfg.COLLECT_SORT_MODES:
        sm_ckpt_key = f"comments_collect_{sort_mode}"

        if ckpt.is_done(unit_key, sm_ckpt_key):
            # Already collected this sort mode — read from per-mode file
            per_mode_path = out_dir / "comments" / f"comments_{sort_mode}.jsonl"
            rows = read_jsonl(per_mode_path)
            # Filter to current video_id for multi-video runs
            rows = [r for r in rows if r.get("VIDEO_ID") == video_id]
            all_normalized.extend(rows)
            continue

        raw_comments = []

        # --- Fallback chain: Playwright → yt-dlp ---
        try:
            from .collectors.comments_playwright_ui import collect_comments_playwright_ui
            t0 = time.time()
            raw_comments = collect_comments_playwright_ui(
                video_url, cfg, sort_mode, artifact_dir=failures_dir,
            )
            logger.info(
                "Playwright collected %d comments (%s sort) in %.1fs",
                len(raw_comments), sort_mode, time.time() - t0,
            )
        except Exception as exc:
            logger.warning("Playwright failed for %s (%s): %s", video_id, sort_mode, exc)

        if not raw_comments:
            try:
                from .collectors.comments_ytdlp import collect_comments_ytdlp
                t0 = time.time()
                raw_comments = collect_comments_ytdlp(video_url, cfg)
                logger.info(
                    "yt-dlp fallback collected %d comments in %.1fs",
                    len(raw_comments), time.time() - t0,
                )
            except Exception as exc:
                logger.warning("yt-dlp fallback also failed for %s: %s", video_id, exc)

        if not raw_comments:
            logger.warning("No comments collected for %s (%s sort)", video_id, sort_mode)
            ckpt.mark(unit_key, sm_ckpt_key)
            continue

        # Normalize with sort_mode tag
        normalized = normalize_comments(raw_comments, video_id, cfg, sort_mode=sort_mode)

        # Write per-sort-mode file
        per_mode_path = out_dir / "comments" / f"comments_{sort_mode}.jsonl"
        write_jsonl(per_mode_path, normalized)
        ckpt.mark(unit_key, sm_ckpt_key)

        all_normalized.extend(normalized)

    # Deduplicate by COMMENT_ID (keep first occurrence)
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for c in all_normalized:
        cid = c["COMMENT_ID"]
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(c)
        elif not cid:
            deduped.append(c)  # keep comments with no ID

    # Write merged file
    comments_path = out_dir / "comments" / "comments.jsonl"
    write_jsonl(comments_path, deduped)
    result.output_files.append(comments_path)
    result.comments_collected += len(deduped)
    logger.info(
        "Wrote %d comments (%d before dedup) to %s",
        len(deduped), len(all_normalized), comments_path,
    )
    ckpt.mark(unit_key, "comments_normalize")


def _enrich_video(cfg, video_id, out_dir, ckpt, unit_key, result, failures_dir):
    from .enrich.embeddings_client import compute_embeddings
    from .enrich.topics_nlp import extract_topics_nlp
    from .enrich.topics_llm import extract_topics_llm
    from .enrich.sentiment import analyze_sentiment
    from .enrich.triples import extract_triples
    from .enrich.url_extraction import extract_urls
    from .enrich.summarization import summarize_content

    # Read collected data, filtering to current video_id
    all_comments = read_jsonl(out_dir / "comments" / "comments.jsonl")
    comments = [c for c in all_comments if c.get("VIDEO_ID") == video_id]
    all_chunks = read_jsonl(out_dir / "transcripts" / "transcript_chunks.jsonl")
    chunks = [c for c in all_chunks if c.get("VIDEO_ID") == video_id]
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
        try:
            texts = [item.get("TEXT", "") for item in all_items]
            embeddings = compute_embeddings(texts, cfg)
            ckpt.mark(unit_key, "enrich_embeddings")
        except Exception as exc:
            logger.exception("Embeddings failed for %s", video_id)
            write_failure(failures_dir, "enrich_embeddings", video_id, exc)
            result.failures.append({
                "stage": "enrich_embeddings", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_embeddings", status="FAILED")

    # --- Topics ---
    if not ckpt.is_done(unit_key, "enrich_topics"):
        try:
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
                topics_path = enrich_dir / "topics.jsonl"
                write_jsonl(topics_path, all_topics)
                result.output_files.append(topics_path)
                logger.info("Wrote %d topic records to enrich/topics.jsonl", len(all_topics))
            ckpt.mark(unit_key, "enrich_topics")
        except Exception as exc:
            logger.exception("Topics enrichment failed for %s", video_id)
            write_failure(failures_dir, "enrich_topics", video_id, exc)
            result.failures.append({
                "stage": "enrich_topics", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_topics", status="FAILED")

    # --- Sentiment ---
    if not ckpt.is_done(unit_key, "enrich_sentiment"):
        try:
            all_sentiment: list[dict] = []
            for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
                if not items:
                    continue
                sentiment = analyze_sentiment(items, video_id, asset_type, cfg)
                all_sentiment.extend(sentiment)

            if all_sentiment:
                sentiment_path = enrich_dir / "sentiment.jsonl"
                write_jsonl(sentiment_path, all_sentiment)
                result.output_files.append(sentiment_path)
                logger.info("Wrote %d sentiment records to enrich/sentiment.jsonl", len(all_sentiment))
            ckpt.mark(unit_key, "enrich_sentiment")
        except Exception as exc:
            logger.exception("Sentiment enrichment failed for %s", video_id)
            write_failure(failures_dir, "enrich_sentiment", video_id, exc)
            result.failures.append({
                "stage": "enrich_sentiment", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_sentiment", status="FAILED")

    # --- Triples ---
    if not ckpt.is_done(unit_key, "enrich_triples"):
        try:
            all_triples: list[dict] = []
            for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
                if not items:
                    continue
                triples = extract_triples(items, video_id, asset_type, cfg)
                all_triples.extend(triples)

            if all_triples:
                triples_path = enrich_dir / "triples.jsonl"
                write_jsonl(triples_path, all_triples)
                result.output_files.append(triples_path)
                logger.info("Wrote %d triple records to enrich/triples.jsonl", len(all_triples))
            ckpt.mark(unit_key, "enrich_triples")
        except Exception as exc:
            logger.exception("Triples enrichment failed for %s", video_id)
            write_failure(failures_dir, "enrich_triples", video_id, exc)
            result.failures.append({
                "stage": "enrich_triples", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_triples", status="FAILED")

    # --- URL extraction ---
    if cfg.URL_EXTRACTION_ENABLE and not ckpt.is_done(unit_key, "enrich_urls"):
        try:
            all_urls: list[dict] = []
            for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
                if not items:
                    continue
                urls = extract_urls(items, video_id, asset_type, cfg)
                all_urls.extend(urls)

            if all_urls:
                urls_path = enrich_dir / "urls.jsonl"
                write_jsonl(urls_path, all_urls)
                result.output_files.append(urls_path)
                logger.info("Wrote %d URL records to enrich/urls.jsonl", len(all_urls))
            ckpt.mark(unit_key, "enrich_urls")
        except Exception as exc:
            logger.exception("URL extraction failed for %s", video_id)
            write_failure(failures_dir, "enrich_urls", video_id, exc)
            result.failures.append({
                "stage": "enrich_urls", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_urls", status="FAILED")

    # --- Summarization ---
    if cfg.SUMMARY_ENABLE and not ckpt.is_done(unit_key, "enrich_summary"):
        try:
            all_summaries: list[dict] = []
            for asset_type, items in [("comments", comments), ("transcripts", chunks)]:
                if not items:
                    continue
                summaries = summarize_content(items, video_id, asset_type, cfg)
                all_summaries.extend(summaries)

            if all_summaries:
                summary_path = enrich_dir / "summary.jsonl"
                write_jsonl(summary_path, all_summaries)
                result.output_files.append(summary_path)
                logger.info("Wrote %d summary records to enrich/summary.jsonl", len(all_summaries))
            ckpt.mark(unit_key, "enrich_summary")
        except Exception as exc:
            logger.exception("Summarization failed for %s", video_id)
            write_failure(failures_dir, "enrich_summary", video_id, exc)
            result.failures.append({
                "stage": "enrich_summary", "video_id": video_id, "error": str(exc),
            })
            ckpt.mark(unit_key, "enrich_summary", status="FAILED")
