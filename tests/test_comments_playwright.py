from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from yt_content_analyzer.collectors.comments_playwright_ui import (
    _extract_comments_from_api_response,
    _extract_text_from_runs,
    _parse_comment_entity_payload,
    _parse_comment_renderer,
    _parse_relative_time,
    _parse_vote_count,
)
from yt_content_analyzer.config import Settings
from yt_content_analyzer.parse.normalize_comments import normalize_comments


def _make_cfg(**overrides) -> Settings:
    return Settings(**overrides)


# ---------------------------------------------------------------------------
# _parse_vote_count
# ---------------------------------------------------------------------------

class TestParseVoteCount:
    def test_plain_number(self):
        assert _parse_vote_count("42") == 42

    def test_thousands(self):
        assert _parse_vote_count("1.2K") == 1200

    def test_millions(self):
        assert _parse_vote_count("1.5M") == 1500000

    def test_empty_string(self):
        assert _parse_vote_count("") == 0

    def test_whitespace_only(self):
        assert _parse_vote_count("  ") == 0

    def test_comma_separated(self):
        assert _parse_vote_count("1,234") == 1234


# ---------------------------------------------------------------------------
# _parse_relative_time
# ---------------------------------------------------------------------------

class TestParseRelativeTime:
    def test_days_ago(self):
        result = _parse_relative_time("2 days ago")
        expected = int(time.time()) - 2 * 86400
        assert abs(result - expected) < 5

    def test_just_now(self):
        result = _parse_relative_time("just now")
        assert abs(result - int(time.time())) < 5

    def test_edited_stripped(self):
        result = _parse_relative_time("3 hours ago (edited)")
        expected = int(time.time()) - 3 * 3600
        assert abs(result - expected) < 5

    def test_garbage_returns_none(self):
        assert _parse_relative_time("not a timestamp") is None

    def test_empty_returns_none(self):
        assert _parse_relative_time("") is None

    def test_none_returns_none(self):
        assert _parse_relative_time(None) is None

    def test_weeks_ago(self):
        result = _parse_relative_time("1 week ago")
        expected = int(time.time()) - 604800
        assert abs(result - expected) < 5

    def test_months_ago(self):
        result = _parse_relative_time("6 months ago")
        expected = int(time.time()) - 6 * 2592000
        assert abs(result - expected) < 5


# ---------------------------------------------------------------------------
# _extract_text_from_runs
# ---------------------------------------------------------------------------

class TestExtractTextFromRuns:
    def test_joins_runs(self):
        runs = [{"text": "Hello "}, {"text": "world"}]
        assert _extract_text_from_runs(runs) == "Hello world"

    def test_empty_runs(self):
        assert _extract_text_from_runs([]) == ""

    def test_single_run(self):
        assert _extract_text_from_runs([{"text": "test"}]) == "test"

    def test_missing_text_key(self):
        runs = [{"text": "a"}, {"url": "http://example.com"}, {"text": "b"}]
        assert _extract_text_from_runs(runs) == "ab"


# ---------------------------------------------------------------------------
# _parse_comment_renderer
# ---------------------------------------------------------------------------

class TestParseCommentRenderer:
    def test_full_renderer(self):
        renderer = {
            "commentId": "Ugz123abc",
            "authorText": {"simpleText": "@testuser"},
            "contentText": {"runs": [{"text": "Great video!"}]},
            "voteCount": {"simpleText": "42"},
            "publishedTimeText": {"runs": [{"text": "2 days ago"}]},
            "replyCount": 5,
        }
        result = _parse_comment_renderer(renderer, parent_id="root")

        assert result is not None
        assert result["id"] == "Ugz123abc"
        assert result["parent"] == "root"
        assert result["author"] == "@testuser"
        assert result["text"] == "Great video!"
        assert result["like_count"] == 42
        assert result["reply_count"] == 5
        assert result["timestamp"] is not None

    def test_malformed_returns_none(self):
        # Missing commentId key
        renderer = {
            "authorText": {"simpleText": "@user"},
            "contentText": {"runs": [{"text": "test"}]},
        }
        result = _parse_comment_renderer(renderer)
        assert result is None

    def test_reply_has_zero_reply_count(self):
        renderer = {
            "commentId": "Ugz456def",
            "authorText": {"simpleText": "@replyer"},
            "contentText": {"runs": [{"text": "I agree"}]},
            "voteCount": {"simpleText": "3"},
            "publishedTimeText": {"runs": [{"text": "1 hour ago"}]},
            "replyCount": 10,  # should be ignored for replies
        }
        result = _parse_comment_renderer(renderer, parent_id="Ugz123abc")
        assert result is not None
        assert result["reply_count"] == 0
        assert result["parent"] == "Ugz123abc"


# ---------------------------------------------------------------------------
# _parse_comment_entity_payload (new 2025+ YouTube format)
# ---------------------------------------------------------------------------

class TestParseCommentEntityPayload:
    def test_full_entity(self):
        entity = {
            "properties": {
                "commentId": "Ugz123abc",
                "content": {"content": "Great video!"},
                "publishedTime": "2 days ago",
                "replyLevel": 0,
            },
            "author": {
                "displayName": "@testuser",
                "channelId": "UC123",
            },
            "toolbar": {
                "likeCountNotliked": "42",
                "replyCount": "5",
            },
        }
        result = _parse_comment_entity_payload(entity)

        assert result is not None
        assert result["id"] == "Ugz123abc"
        assert result["parent"] == "root"
        assert result["author"] == "@testuser"
        assert result["text"] == "Great video!"
        assert result["like_count"] == 42
        assert result["reply_count"] == 5
        assert result["timestamp"] is not None

    def test_reply_entity(self):
        entity = {
            "properties": {
                "commentId": "Ugz456def",
                "content": {"content": "I agree"},
                "publishedTime": "1 hour ago",
                "replyLevel": 1,
            },
            "author": {"displayName": "@replyer"},
            "toolbar": {
                "likeCountNotliked": "3",
                "replyCount": "",
            },
        }
        result = _parse_comment_entity_payload(entity)
        assert result is not None
        assert result["reply_count"] == 0
        assert result["parent"] == "unknown_parent"

    def test_missing_comment_id(self):
        entity = {
            "properties": {"content": {"content": "test"}},
            "author": {"displayName": "@user"},
            "toolbar": {},
        }
        result = _parse_comment_entity_payload(entity)
        assert result is None

    def test_empty_likes(self):
        entity = {
            "properties": {
                "commentId": "Ugz789",
                "content": {"content": "no likes"},
                "publishedTime": "just now",
                "replyLevel": 0,
            },
            "author": {"displayName": "@user"},
            "toolbar": {"likeCountNotliked": "", "replyCount": ""},
        }
        result = _parse_comment_entity_payload(entity)
        assert result is not None
        assert result["like_count"] == 0
        assert result["reply_count"] == 0


# ---------------------------------------------------------------------------
# _extract_comments_from_api_response
# ---------------------------------------------------------------------------

class TestExtractCommentsFromApiResponse:
    def test_realistic_response(self):
        data = {
            "onResponseReceivedEndpoints": [
                {
                    "reloadContinuationItemsCommand": {
                        "continuationItems": [
                            {
                                "commentThreadRenderer": {
                                    "comment": {
                                        "commentRenderer": {
                                            "commentId": "Ugw1",
                                            "authorText": {"simpleText": "@alice"},
                                            "contentText": {
                                                "runs": [{"text": "First comment"}]
                                            },
                                            "voteCount": {"simpleText": "10"},
                                            "publishedTimeText": {
                                                "runs": [{"text": "1 day ago"}]
                                            },
                                            "replyCount": 2,
                                        }
                                    },
                                }
                            },
                            {
                                "commentThreadRenderer": {
                                    "comment": {
                                        "commentRenderer": {
                                            "commentId": "Ugw2",
                                            "authorText": {"simpleText": "@bob"},
                                            "contentText": {
                                                "runs": [{"text": "Second comment"}]
                                            },
                                            "voteCount": {"simpleText": "5"},
                                            "publishedTimeText": {
                                                "runs": [{"text": "3 days ago"}]
                                            },
                                            "replyCount": 0,
                                        }
                                    },
                                }
                            },
                        ]
                    }
                }
            ]
        }
        comments = _extract_comments_from_api_response(data)

        assert len(comments) == 2
        assert comments[0]["id"] == "Ugw1"
        assert comments[0]["text"] == "First comment"
        assert comments[0]["reply_count"] == 2
        assert comments[1]["id"] == "Ugw2"
        assert comments[1]["text"] == "Second comment"

    def test_append_continuation(self):
        data = {
            "onResponseReceivedEndpoints": [
                {
                    "appendContinuationItemsAction": {
                        "continuationItems": [
                            {
                                "commentThreadRenderer": {
                                    "comment": {
                                        "commentRenderer": {
                                            "commentId": "Ugw3",
                                            "authorText": {"simpleText": "@charlie"},
                                            "contentText": {
                                                "runs": [{"text": "Appended"}]
                                            },
                                            "voteCount": {"simpleText": ""},
                                            "publishedTimeText": {
                                                "runs": [{"text": "just now"}]
                                            },
                                        }
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
        comments = _extract_comments_from_api_response(data)
        assert len(comments) == 1
        assert comments[0]["id"] == "Ugw3"
        assert comments[0]["like_count"] == 0

    def test_new_format_framework_updates(self):
        """New YouTube format: comments in frameworkUpdates mutations."""
        data = {
            "frameworkUpdates": {
                "entityBatchUpdate": {
                    "mutations": [
                        {
                            "payload": {
                                "commentEntityPayload": {
                                    "properties": {
                                        "commentId": "Ugw_new1",
                                        "content": {"content": "New format comment"},
                                        "publishedTime": "1 day ago",
                                        "replyLevel": 0,
                                    },
                                    "author": {"displayName": "@alice"},
                                    "toolbar": {
                                        "likeCountNotliked": "10",
                                        "replyCount": "2",
                                    },
                                }
                            }
                        },
                        {
                            "payload": {
                                "commentEntityPayload": {
                                    "properties": {
                                        "commentId": "Ugw_new2",
                                        "content": {"content": "Another comment"},
                                        "publishedTime": "3 hours ago",
                                        "replyLevel": 0,
                                    },
                                    "author": {"displayName": "@bob"},
                                    "toolbar": {
                                        "likeCountNotliked": "5",
                                        "replyCount": "",
                                    },
                                }
                            }
                        },
                        {
                            "payload": {
                                "commentSharedEntityPayload": {
                                    "key": "shared_data",
                                }
                            }
                        },
                    ]
                }
            }
        }
        comments = _extract_comments_from_api_response(data)

        assert len(comments) == 2
        assert comments[0]["id"] == "Ugw_new1"
        assert comments[0]["text"] == "New format comment"
        assert comments[0]["like_count"] == 10
        assert comments[0]["reply_count"] == 2
        assert comments[1]["id"] == "Ugw_new2"

    def test_empty_response(self):
        assert _extract_comments_from_api_response({}) == []
        assert _extract_comments_from_api_response(
            {"onResponseReceivedEndpoints": []}
        ) == []

    def test_inline_replies(self):
        data = {
            "onResponseReceivedEndpoints": [
                {
                    "reloadContinuationItemsCommand": {
                        "continuationItems": [
                            {
                                "commentThreadRenderer": {
                                    "comment": {
                                        "commentRenderer": {
                                            "commentId": "UgwParent",
                                            "authorText": {"simpleText": "@parent"},
                                            "contentText": {
                                                "runs": [{"text": "Top comment"}]
                                            },
                                            "voteCount": {"simpleText": "100"},
                                            "publishedTimeText": {
                                                "runs": [{"text": "1 week ago"}]
                                            },
                                            "replyCount": 1,
                                        }
                                    },
                                    "replies": {
                                        "commentRepliesRenderer": {
                                            "contents": [
                                                {
                                                    "commentRenderer": {
                                                        "commentId": "UgwReply1",
                                                        "authorText": {
                                                            "simpleText": "@replyer"
                                                        },
                                                        "contentText": {
                                                            "runs": [{"text": "Reply!"}]
                                                        },
                                                        "voteCount": {"simpleText": "3"},
                                                        "publishedTimeText": {
                                                            "runs": [{"text": "5 days ago"}]
                                                        },
                                                    }
                                                }
                                            ]
                                        }
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
        comments = _extract_comments_from_api_response(data)
        assert len(comments) == 2
        assert comments[0]["id"] == "UgwParent"
        assert comments[0]["parent"] == "root"
        assert comments[1]["id"] == "UgwReply1"
        assert comments[1]["parent"] == "UgwParent"


# ---------------------------------------------------------------------------
# collect_comments_playwright_ui (mocked)
# ---------------------------------------------------------------------------

class TestCollectEmpty:
    def test_no_intercepted_comments(self):
        """Mock Playwright with no API responses → returns []."""
        mock_pw_instance = MagicMock()
        mock_browser = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_sync_pw = MagicMock()
        mock_sync_pw.return_value.start.return_value = mock_pw_instance

        with patch(
            "playwright.sync_api.sync_playwright", mock_sync_pw
        ):
            from yt_content_analyzer.collectors.comments_playwright_ui import (
                collect_comments_playwright_ui,
            )

            cfg = _make_cfg(MAX_COMMENTS_PER_VIDEO=100)
            result = collect_comments_playwright_ui(
                "https://www.youtube.com/watch?v=test12345", cfg, sort_mode="top"
            )
        assert result == []
        mock_browser.close.assert_called_once()


# ---------------------------------------------------------------------------
# Fallback chain in run.py
# ---------------------------------------------------------------------------

class TestFallbackChain:
    @patch("yt_content_analyzer.run.write_jsonl")
    @patch("yt_content_analyzer.run.read_jsonl", return_value=[])
    def test_playwright_fails_ytdlp_succeeds(self, mock_read, mock_write):
        """When Playwright raises, yt-dlp fallback should be used."""
        from yt_content_analyzer.run import _collect_and_process_comments

        cfg = _make_cfg(
            VIDEO_URL="https://www.youtube.com/watch?v=test12345",
            COLLECT_SORT_MODES=["top"],
        )
        ckpt = MagicMock()
        ckpt.is_done.return_value = False
        out_dir = Path("/tmp/test_run")

        fake_ytdlp_comments = [
            {
                "id": "ytdlp1",
                "parent": "root",
                "author": "User",
                "text": "From yt-dlp",
                "like_count": 1,
                "timestamp": 1700000000,
            }
        ]

        # Patch the modules that get lazily imported inside the function
        mock_pw_mod = MagicMock()
        mock_pw_mod.collect_comments_playwright_ui.side_effect = RuntimeError("Browser crashed")
        mock_ytdlp_mod = MagicMock()
        mock_ytdlp_mod.collect_comments_ytdlp.return_value = fake_ytdlp_comments

        import sys
        from yt_content_analyzer.models import RunResult
        result = RunResult(run_id="test", output_dir=out_dir)
        failures_dir = out_dir / "failures"

        with patch.dict(sys.modules, {
            "yt_content_analyzer.collectors.comments_playwright_ui": mock_pw_mod,
            "yt_content_analyzer.collectors.comments_ytdlp": mock_ytdlp_mod,
        }):
            _collect_and_process_comments(
                cfg, cfg.VIDEO_URL, "test12345", out_dir, ckpt, "test12345",
                result, failures_dir,
            )

        # Should have written per-mode and merged files
        assert mock_write.call_count >= 1


class TestSortModeLoop:
    @patch("yt_content_analyzer.run.write_jsonl")
    @patch("yt_content_analyzer.run.read_jsonl", return_value=[])
    def test_two_sort_modes_produces_files(self, mock_read, mock_write):
        """Two sort modes should produce two per-mode files + merged."""
        from yt_content_analyzer.run import _collect_and_process_comments
        from yt_content_analyzer.state.checkpoint import CheckpointStore

        cfg = _make_cfg(
            VIDEO_URL="https://www.youtube.com/watch?v=test12345",
            COLLECT_SORT_MODES=["top", "newest"],
        )
        ckpt = MagicMock(spec=CheckpointStore)
        ckpt.is_done.return_value = False
        out_dir = Path("/tmp/test_run")

        top_comments = [
            {"id": "c1", "parent": "root", "author": "A", "text": "Top",
             "like_count": 10, "timestamp": 1700000000},
            {"id": "c2", "parent": "root", "author": "B", "text": "Also top",
             "like_count": 5, "timestamp": 1700000000},
        ]
        newest_comments = [
            {"id": "c2", "parent": "root", "author": "B", "text": "Also top",
             "like_count": 5, "timestamp": 1700000000},  # duplicate
            {"id": "c3", "parent": "root", "author": "C", "text": "Newest",
             "like_count": 1, "timestamp": 1700100000},
        ]

        call_count = 0

        def fake_playwright(url, cfg, sort_mode, **kwargs):
            nonlocal call_count
            call_count += 1
            if sort_mode == "top":
                return top_comments
            return newest_comments

        from yt_content_analyzer.models import RunResult
        result = RunResult(run_id="test", output_dir=out_dir)
        failures_dir = out_dir / "failures"

        with patch.dict(
            "sys.modules",
            {
                "yt_content_analyzer.collectors.comments_playwright_ui": MagicMock(
                    collect_comments_playwright_ui=fake_playwright
                ),
            },
        ):
            _collect_and_process_comments(
                cfg, cfg.VIDEO_URL, "test12345", out_dir, ckpt, "test12345",
                result, failures_dir,
            )

        # Should have: per-mode file for "top", per-mode file for "newest", merged
        assert mock_write.call_count == 3

        # Merged file should be deduped: c1, c2, c3 (c2 appears in both)
        merged_call = mock_write.call_args_list[-1]
        merged_rows = list(merged_call[0][1])
        merged_ids = [r["COMMENT_ID"] for r in merged_rows]
        assert len(merged_ids) == 3
        assert merged_ids.count("c2") == 1  # deduped


# ---------------------------------------------------------------------------
# normalize_comments updates
# ---------------------------------------------------------------------------

class TestNormalizeSortModeParam:
    def test_sort_mode_top(self):
        raw = [
            {"id": "c1", "parent": "root", "author": "A", "text": "hi",
             "like_count": 1, "timestamp": 1700000000},
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg, sort_mode="top")
        assert result[0]["SORT_MODE"] == "top"

    def test_sort_mode_default_when_omitted(self):
        raw = [
            {"id": "c1", "parent": "root", "author": "A", "text": "hi",
             "like_count": 1, "timestamp": 1700000000},
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["SORT_MODE"] == "default"


class TestNormalizeReplyCount:
    def test_reply_count_from_raw(self):
        raw = [
            {"id": "c1", "parent": "root", "author": "A", "text": "hi",
             "like_count": 1, "timestamp": 1700000000, "reply_count": 5},
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["REPLY_COUNT"] == 5

    def test_reply_count_missing(self):
        raw = [
            {"id": "c1", "parent": "root", "author": "A", "text": "hi",
             "like_count": 1, "timestamp": 1700000000},
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["REPLY_COUNT"] == 0

    def test_reply_count_none(self):
        raw = [
            {"id": "c1", "parent": "root", "author": "A", "text": "hi",
             "like_count": 1, "timestamp": 1700000000, "reply_count": None},
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["REPLY_COUNT"] == 0
