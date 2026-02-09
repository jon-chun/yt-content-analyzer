from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

from ..config import Settings

logger = logging.getLogger(__name__)


def collect_transcript_ytdlp(video_url: str, cfg: Settings) -> dict[str, Any]:
    """Collect transcript for a single video via yt-dlp subtitle extraction.

    Returns dict with keys: video_id, source, lang, entries
    where entries is a list of {text, start, duration}.
    Retries on failure with exponential backoff.
    """
    import yt_dlp

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": cfg.TRANSCRIPTS_ALLOW_AUTO,
        "subtitleslangs": cfg.TRANSCRIPTS_LANG_PREFERENCE,
        "quiet": True,
        "no_warnings": True,
    }

    max_retries = cfg.MAX_RETRY_SCRAPE
    backoff = cfg.BACKOFF_BASE_SECONDS

    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            break
        except Exception as exc:
            if attempt < max_retries:
                wait = min(backoff * (2 ** attempt), cfg.BACKOFF_MAX_SECONDS)
                logger.warning(
                    "yt-dlp transcript attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_retries + 1, exc, wait,
                )
                time.sleep(wait)
                continue
            logger.error(
                "yt-dlp transcript exhausted %d retries for %s", max_retries + 1, video_url
            )
            raise

    video_id = info.get("id", "")
    lang_prefs = cfg.TRANSCRIPTS_LANG_PREFERENCE

    # Pick best subtitle track: prefer manual, fall back to auto
    manual_subs: dict = info.get("subtitles") or {}
    auto_subs: dict = info.get("automatic_captions") or {}

    chosen_lang = None
    chosen_url = None
    source = "unknown"

    if cfg.TRANSCRIPTS_PREFER_MANUAL:
        for lang in lang_prefs:
            if lang in manual_subs:
                chosen_lang = lang
                source = "manual"
                chosen_url = _pick_json3_url(manual_subs[lang])
                break

    if chosen_url is None and cfg.TRANSCRIPTS_ALLOW_AUTO:
        for lang in lang_prefs:
            if lang in auto_subs:
                chosen_lang = lang
                source = "auto"
                chosen_url = _pick_json3_url(auto_subs[lang])
                break

    if chosen_url is None:
        logger.warning("No subtitles found for %s", video_id)
        return {"video_id": video_id, "source": "none", "lang": "", "entries": []}

    logger.info(
        "Downloading %s subtitles (%s) for %s", source, chosen_lang, video_id
    )

    # Download and parse json3 subtitle data (with retry)
    for attempt in range(max_retries + 1):
        try:
            entries = _download_and_parse_json3(chosen_url)
            break
        except Exception as exc:
            if attempt < max_retries:
                wait = min(backoff * (2 ** attempt), cfg.BACKOFF_MAX_SECONDS)
                logger.warning(
                    "json3 download attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_retries + 1, exc, wait,
                )
                time.sleep(wait)
                continue
            logger.error("json3 download exhausted %d retries for %s", max_retries + 1, video_id)
            raise

    return {
        "video_id": video_id,
        "source": source,
        "lang": chosen_lang,
        "entries": entries,
    }


def _pick_json3_url(formats: list[dict]) -> str | None:
    """Pick the json3 format URL from a list of subtitle format dicts."""
    for fmt in formats:
        if fmt.get("ext") == "json3":
            return fmt.get("url")
    # Fallback: try first available format
    if formats:
        return formats[0].get("url")
    return None


def _download_and_parse_json3(url: str) -> list[dict[str, Any]]:
    """Download json3 subtitle file and parse into [{text, start, duration}]."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    entries: list[dict[str, Any]] = []
    for event in data.get("events", []):
        # Skip events without segment data
        segs = event.get("segs")
        if not segs:
            continue

        text = "".join(seg.get("utf8", "") for seg in segs).strip()
        if not text or text == "\n":
            continue

        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)

        entries.append({
            "text": text,
            "start": start_ms / 1000.0,
            "duration": duration_ms / 1000.0,
        })

    return entries
