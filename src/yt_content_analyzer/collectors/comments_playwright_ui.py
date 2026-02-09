from __future__ import annotations

import logging
import random
import re
import time
from pathlib import Path
from typing import Any

from ..config import Settings

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def collect_comments_playwright_ui(
    video_url: str,
    cfg: Settings,
    sort_mode: str = "top",
    *,
    artifact_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Collect comments via Playwright API interception.

    Navigates to the video page with a headless Chromium browser, intercepts
    YouTube's internal ``youtubei/v1/next`` POST responses, and extracts
    structured comment data from the JSON payloads.

    Parameters
    ----------
    video_url:
        Full YouTube video URL.
    cfg:
        Application settings (uses MAX_COMMENTS_PER_VIDEO, MAX_COMMENT_THREAD_DEPTH,
        API_JITTER_MS_MIN/MAX, CAPTURE_ARTIFACTS_ON_ERROR).
    sort_mode:
        ``"top"`` (default) or ``"newest"``.

    Returns
    -------
    list[dict]
        Raw comment dicts ready for ``normalize_comments()``.
    """
    from playwright.sync_api import sync_playwright

    max_comments = cfg.MAX_COMMENTS_PER_VIDEO
    collected: list[dict[str, Any]] = []

    def _on_response(response):
        try:
            if (
                response.request.method == "POST"
                and "youtubei/v1/next" in response.url
                and response.status == 200
            ):
                body = response.json()
                comments = _extract_comments_from_api_response(body)
                collected.extend(comments)
        except Exception:
            pass  # non-JSON or network error — ignore

    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        page.on("response", _on_response)

        # Navigate
        try:
            page.goto(video_url, timeout=30_000, wait_until="domcontentloaded")
        except Exception as exc:
            _logger.warning("Playwright navigation timeout for %s: %s", video_url, exc)
            return []

        # Dismiss consent dialog if present
        _dismiss_consent(page)

        # Scroll to comments section
        _scroll_to_comments(page)

        # Switch sort mode
        _switch_sort_mode(page, sort_mode)

        # Scroll and collect
        _scroll_and_collect(page, collected, max_comments, cfg)

        # Expand replies
        if cfg.MAX_COMMENT_THREAD_DEPTH > 0:
            _expand_replies(page, collected, cfg)

    except Exception as exc:
        _logger.warning("Playwright comment collection error: %s", exc)
        if cfg.CAPTURE_ARTIFACTS_ON_ERROR:
            _save_artifact(
                page if "page" in dir() else None, video_url, sort_mode,
                artifact_dir=artifact_dir,
            )
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if "pw" in dir() and pw is not None:
            try:
                pw.stop()
            except Exception:
                pass

    return collected[:max_comments]


# ---------------------------------------------------------------------------
# Page interaction helpers
# ---------------------------------------------------------------------------

def _dismiss_consent(page) -> None:
    """Click through YouTube consent/cookie dialogs if present."""
    try:
        reject_btn = page.locator(
            "button:has-text('Reject all'), button:has-text('Reject All'), "
            "button:has-text('Accept all'), button:has-text('Accept All')"
        ).first
        if reject_btn.is_visible(timeout=3_000):
            reject_btn.click()
            page.wait_for_timeout(1_000)
    except Exception:
        pass


def _scroll_to_comments(page) -> None:
    """Scroll down until comments start loading.

    The ``#comments`` container appears early but comment data loads via API
    after a short delay. We wait for ``ytd-comment-thread-renderer`` elements
    (the rendered comment DOM nodes) to confirm comments have actually loaded.
    """
    for _ in range(10):
        page.evaluate("window.scrollBy(0, 300)")
        try:
            page.wait_for_selector(
                "ytd-comment-thread-renderer, ytd-comment-view-model",
                timeout=5_000,
            )
            return
        except Exception:
            continue
    _logger.debug("Comments section not found after scrolling")


def _switch_sort_mode(page, sort_mode: str) -> None:
    """Click the sort dropdown and select the desired sort mode."""
    if sort_mode not in ("top", "newest"):
        return

    try:
        # The sort button is inside #sort-menu; click the inner trigger element
        trigger = page.locator(
            "#sort-menu tp-yt-paper-menu-button #trigger, "
            "#sort-menu tp-yt-paper-menu-button #label"
        ).first
        trigger.wait_for(timeout=8_000)
        trigger.click()
        page.wait_for_timeout(1_000)

        # Index 0 = "Top comments", Index 1 = "Newest first"
        index = 0 if sort_mode == "top" else 1
        options = page.locator(
            "tp-yt-paper-listbox tp-yt-paper-item, "
            "tp-yt-paper-listbox a.yt-dropdown-menu"
        )
        options.first.wait_for(timeout=3_000)
        if options.count() > index:
            options.nth(index).click()
            page.wait_for_timeout(2_000)
    except Exception as exc:
        _logger.warning("Failed to switch sort mode to %s: %s", sort_mode, exc)


def _scroll_and_collect(
    page, collected: list[dict], max_comments: int, cfg: Settings,
) -> None:
    """Scroll the page to trigger comment loading via API interception.

    Uses a patience-based approach: the ``no_new_threshold`` is higher during
    the first few scrolls (initial load may be slow) and tightens once we
    have confirmed that comments are flowing.
    """
    no_new_count = 0
    prev_count = len(collected)
    ever_collected = prev_count > 0

    for iteration in range(200):  # safety cap
        if len(collected) >= max_comments:
            break

        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        jitter = random.uniform(cfg.API_JITTER_MS_MIN, cfg.API_JITTER_MS_MAX) / 1000
        page.wait_for_timeout(int(jitter * 1000))

        if len(collected) > prev_count:
            no_new_count = 0
            prev_count = len(collected)
            ever_collected = True
        else:
            no_new_count += 1
            # Be patient during initial load (first 10 scrolls) before any
            # comments arrive; once comments are flowing, 3 empty scrolls = done
            patience = 3 if ever_collected else 8
            if no_new_count >= patience:
                break


def _expand_replies(page, collected: list[dict], cfg: Settings) -> None:
    """Click 'View replies' and 'Show more replies' buttons to load reply threads."""
    max_depth = cfg.MAX_COMMENT_THREAD_DEPTH

    for depth in range(max_depth):
        reply_buttons = page.locator(
            "#more-replies button, "
            "ytd-button-renderer#more-replies, "
            "[aria-label*='repl' i] button, "
            "ytd-continuation-item-renderer button"
        )
        count = reply_buttons.count()
        if count == 0:
            break

        clicked = 0
        for i in range(min(count, 50)):  # limit per pass
            try:
                btn = reply_buttons.nth(i)
                if btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    clicked += 1
                    jitter = random.uniform(
                        cfg.API_JITTER_MS_MIN, cfg.API_JITTER_MS_MAX
                    ) / 1000
                    page.wait_for_timeout(int(jitter * 1000))
            except Exception:
                continue

        if clicked == 0:
            break


def _save_artifact(
    page, video_url: str, sort_mode: str, *, artifact_dir: Path | None = None,
) -> None:
    """Save a screenshot on error for debugging."""
    if page is None or artifact_dir is None:
        return
    try:
        video_id = _extract_video_id_from_url(video_url)
        path = artifact_dir / f"playwright_comments_{video_id}_{sort_mode}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path))
        _logger.debug("Saved artifact screenshot to %s", path)
    except Exception:
        pass


def _extract_video_id_from_url(url: str) -> str:
    """Extract video ID from URL for artifact naming."""
    match = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return match.group(1) if match else "unknown"


# ---------------------------------------------------------------------------
# YouTube API response parsing
# ---------------------------------------------------------------------------

def _extract_comments_from_api_response(data: dict) -> list[dict[str, Any]]:
    """Extract comment dicts from a ``youtubei/v1/next`` JSON response.

    Supports two YouTube API formats:
    - **New (2025+):** Comment data lives in ``frameworkUpdates.entityBatchUpdate.mutations``
      as ``commentEntityPayload`` objects.
    - **Legacy:** Comment data lives inline in ``commentThreadRenderer.comment.commentRenderer``
      within ``onResponseReceivedEndpoints``.
    """
    comments: list[dict[str, Any]] = []

    # --- New format: frameworkUpdates mutations ---
    mutations = (
        data.get("frameworkUpdates", {})
        .get("entityBatchUpdate", {})
        .get("mutations", [])
    )
    for mutation in mutations:
        payload = mutation.get("payload", {})
        entity = payload.get("commentEntityPayload")
        if entity:
            parsed = _parse_comment_entity_payload(entity)
            if parsed:
                comments.append(parsed)

    if comments:
        return comments

    # --- Legacy format: onResponseReceivedEndpoints ---
    endpoints = data.get("onResponseReceivedEndpoints", [])
    for endpoint in endpoints:
        items = (
            endpoint.get("appendContinuationItemsAction", {}).get("continuationItems", [])
            or endpoint.get("reloadContinuationItemsCommand", {}).get(
                "continuationItems", []
            )
        )
        for item in items:
            thread = item.get("commentThreadRenderer")
            if thread:
                renderer = thread.get("comment", {}).get("commentRenderer")
                if renderer:
                    parsed = _parse_comment_renderer(renderer, parent_id="root")
                    if parsed:
                        comments.append(parsed)

                replies_renderer = thread.get("replies", {}).get(
                    "commentRepliesRenderer", {}
                )
                for reply_item in replies_renderer.get("contents", []):
                    reply_renderer = reply_item.get("commentRenderer")
                    if reply_renderer:
                        parent_id = (
                            renderer.get("commentId", "root") if renderer else "root"
                        )
                        parsed_reply = _parse_comment_renderer(
                            reply_renderer, parent_id=parent_id
                        )
                        if parsed_reply:
                            comments.append(parsed_reply)
                continue

            bare = item.get("commentRenderer")
            if bare:
                parsed = _parse_comment_renderer(bare, parent_id="root")
                if parsed:
                    comments.append(parsed)

    return comments


def _parse_comment_entity_payload(entity: dict) -> dict[str, Any] | None:
    """Parse a ``commentEntityPayload`` (new 2025+ YouTube API format)."""
    try:
        props = entity.get("properties", {})
        comment_id = props.get("commentId")
        if not comment_id:
            return None

        text = props.get("content", {}).get("content", "")
        published_time = props.get("publishedTime", "")
        reply_level = props.get("replyLevel", 0)

        author_info = entity.get("author", {})
        author = author_info.get("displayName", "")

        toolbar = entity.get("toolbar", {})
        like_count = _parse_vote_count(toolbar.get("likeCountNotliked", ""))
        reply_count_str = toolbar.get("replyCount", "")
        reply_count = int(reply_count_str) if reply_count_str else 0

        timestamp = _parse_relative_time(published_time)
        parent_id = "root" if reply_level == 0 else "unknown_parent"

        return {
            "id": comment_id,
            "parent": parent_id,
            "author": author,
            "text": text,
            "like_count": like_count,
            "timestamp": timestamp,
            "reply_count": reply_count if reply_level == 0 else 0,
        }
    except (KeyError, TypeError, ValueError) as exc:
        _logger.debug("Skipping malformed commentEntityPayload: %s", exc)
        return None


def _parse_comment_renderer(
    renderer: dict, parent_id: str = "root",
) -> dict[str, Any] | None:
    """Parse a single ``commentRenderer`` (legacy format) into a raw comment dict."""
    try:
        comment_id = renderer["commentId"]
        author = renderer.get("authorText", {}).get("simpleText", "")
        text = _extract_text_from_runs(
            renderer.get("contentText", {}).get("runs", [])
        )
        like_count = _parse_vote_count(
            renderer.get("voteCount", {}).get("simpleText", "")
        )
        timestamp = _parse_relative_time(
            _extract_text_from_runs(
                renderer.get("publishedTimeText", {}).get("runs", [])
            )
        )
        reply_count = renderer.get("replyCount", 0) if parent_id == "root" else 0

        return {
            "id": comment_id,
            "parent": parent_id,
            "author": author,
            "text": text,
            "like_count": like_count,
            "timestamp": timestamp,
            "reply_count": reply_count,
        }
    except (KeyError, TypeError) as exc:
        _logger.debug("Skipping malformed comment renderer: %s", exc)
        return None


def _extract_text_from_runs(runs: list[dict]) -> str:
    """Join all ``text`` values from YouTube's runs format."""
    if not runs:
        return ""
    return "".join(run.get("text", "") for run in runs)


def _parse_vote_count(text: str) -> int:
    """Parse YouTube vote count strings.

    Examples: ``"42"`` -> 42, ``"1.2K"`` -> 1200, ``"1.5M"`` -> 1500000, ``""`` -> 0
    """
    if not text or not text.strip():
        return 0
    text = text.strip()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    upper = text.upper()
    for suffix, mult in multipliers.items():
        if upper.endswith(suffix):
            try:
                return int(float(upper[:-1]) * mult)
            except ValueError:
                return 0
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return 0


def _parse_relative_time(text: str) -> int | None:
    """Parse YouTube relative timestamps to Unix epoch seconds.

    Examples: ``"2 days ago"`` -> ``now - 172800``, ``"just now"`` -> ``now``.
    Strips ``"(edited)"`` suffix. Returns ``None`` if unparseable.
    """
    if not text:
        return None

    text = text.strip()
    # Strip "(edited)" suffix
    text = re.sub(r"\s*\(edited\)\s*$", "", text)
    text = text.strip()

    if not text:
        return None

    now = int(time.time())

    if text.lower() in ("just now", "0 seconds ago"):
        return now

    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text, re.I)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2).lower()
    unit_seconds = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
        "week": 604800,
        "month": 2592000,   # ~30 days
        "year": 31536000,   # ~365 days
    }

    return now - amount * unit_seconds.get(unit, 0)
