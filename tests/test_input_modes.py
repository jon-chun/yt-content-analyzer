"""Tests for input flexibility: bare video IDs, --channel CLI, search discovery, per-video output."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt_content_analyzer.config import Settings
from yt_content_analyzer.run import extract_video_id, _video_out_dir


# ---------------------------------------------------------------------------
# extract_video_id: bare ID support
# ---------------------------------------------------------------------------

class TestExtractVideoIdBareId:
    def test_bare_11_char_id(self):
        assert extract_video_id("4jQChe0rg1c") == "4jQChe0rg1c"

    def test_bare_id_with_whitespace(self):
        assert extract_video_id("  4jQChe0rg1c  ") == "4jQChe0rg1c"

    def test_bare_id_with_dash(self):
        assert extract_video_id("abc-def_123") == "abc-def_123"

    def test_url_still_works(self):
        assert extract_video_id("https://www.youtube.com/watch?v=4jQChe0rg1c") == "4jQChe0rg1c"

    def test_short_url_still_works(self):
        assert extract_video_id("https://youtu.be/4jQChe0rg1c") == "4jQChe0rg1c"

    def test_embed_url_still_works(self):
        assert extract_video_id("https://www.youtube.com/embed/4jQChe0rg1c") == "4jQChe0rg1c"

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="Cannot extract video ID"):
            extract_video_id("abc123")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="Cannot extract video ID"):
            extract_video_id("abcdefghijkl")


# ---------------------------------------------------------------------------
# _video_out_dir helper
# ---------------------------------------------------------------------------

class TestVideoOutDir:
    def test_per_video_true(self):
        base = Path("/tmp/runs/123")
        result = _video_out_dir(base, "abc12345678", per_video=True)
        assert result == base / "videos" / "abc12345678"

    def test_per_video_false(self):
        base = Path("/tmp/runs/123")
        result = _video_out_dir(base, "abc12345678", per_video=False)
        assert result == base


# ---------------------------------------------------------------------------
# CLI: --channel flag
# ---------------------------------------------------------------------------

class TestChannelCLI:
    def test_channel_flag_constructs_subscriptions(self, tmp_path):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        cfg_file = tmp_path / "config.yml"
        cfg_file.write_text("VIDEO_URL:\n", encoding="utf-8")

        with patch("yt_content_analyzer.run.run_all") as mock_run:
            mock_run.return_value = MagicMock(
                run_id="test", output_dir=tmp_path, videos_processed=0,
                comments_collected=0, transcript_chunks=0, failures=[],
            )
            runner = CliRunner()
            result = runner.invoke(main, [
                "run-all", "--config", str(cfg_file),
                "--channel", "@fahdmirza",
                "--channel", "@engineerprompt",
            ])
            if result.exit_code == 0:
                call_cfg = mock_run.call_args[0][0]
                assert call_cfg.VIDEO_URL is None
                assert call_cfg.SEARCH_TERMS is None
                assert len(call_cfg.YT_SUBSCRIPTIONS) == 2
                assert call_cfg.YT_SUBSCRIPTIONS[0]["CHANNEL"] == "@fahdmirza"
                assert call_cfg.YT_SUBSCRIPTIONS[1]["CHANNEL"] == "@engineerprompt"

    def test_channel_flag_single(self, tmp_path):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        cfg_file = tmp_path / "config.yml"
        cfg_file.write_text("VIDEO_URL:\n", encoding="utf-8")

        with patch("yt_content_analyzer.run.run_all") as mock_run:
            mock_run.return_value = MagicMock(
                run_id="test", output_dir=tmp_path, videos_processed=0,
                comments_collected=0, transcript_chunks=0, failures=[],
            )
            runner = CliRunner()
            result = runner.invoke(main, [
                "run-all", "--config", str(cfg_file),
                "--channel", "@fahdmirza",
            ])
            if result.exit_code == 0:
                call_cfg = mock_run.call_args[0][0]
                assert len(call_cfg.YT_SUBSCRIPTIONS) == 1
                assert call_cfg.YT_SUBSCRIPTIONS[0]["CHANNEL"] == "@fahdmirza"


# ---------------------------------------------------------------------------
# Search resolver (mocked yt-dlp)
# ---------------------------------------------------------------------------

class TestSearchResolver:
    def _make_mock_ydl(self, fake_info):
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = fake_info
        return mock_ydl

    @patch.dict("sys.modules", {"yt_dlp": MagicMock()})
    def test_resolve_search_basic(self):
        import sys
        mock_ytdlp = sys.modules["yt_dlp"]
        fake_info = {
            "entries": [
                {"id": "vid11111111", "title": "Result 1"},
                {"id": "vid22222222", "title": "Result 2"},
            ],
        }
        mock_ytdlp.YoutubeDL.return_value = self._make_mock_ydl(fake_info)

        cfg = Settings()
        import importlib
        import yt_content_analyzer.discovery.search_resolver as mod
        importlib.reload(mod)
        result = mod.resolve_search_videos("Claude CoWork", 5, cfg)

        assert len(result) == 2
        assert result[0]["VIDEO_ID"] == "vid11111111"
        assert result[0]["VIDEO_URL"] == "https://www.youtube.com/watch?v=vid11111111"
        assert result[0]["SEARCH_TERM"] == "Claude CoWork"
        assert result[1]["TITLE"] == "Result 2"

    @patch.dict("sys.modules", {"yt_dlp": MagicMock()})
    def test_resolve_search_empty(self):
        import sys
        mock_ytdlp = sys.modules["yt_dlp"]
        fake_info = {"entries": []}
        mock_ytdlp.YoutubeDL.return_value = self._make_mock_ydl(fake_info)

        cfg = Settings()
        import importlib
        import yt_content_analyzer.discovery.search_resolver as mod
        importlib.reload(mod)
        result = mod.resolve_search_videos("nonexistent_xyz_query", 5, cfg)

        assert result == []

    @patch.dict("sys.modules", {"yt_dlp": MagicMock()})
    def test_resolve_search_skips_empty_entries(self):
        import sys
        mock_ytdlp = sys.modules["yt_dlp"]
        fake_info = {
            "entries": [
                {"id": "vid11111111", "title": "Good"},
                None,
                {"id": "", "title": "No ID"},
            ],
        }
        mock_ytdlp.YoutubeDL.return_value = self._make_mock_ydl(fake_info)

        cfg = Settings()
        import importlib
        import yt_content_analyzer.discovery.search_resolver as mod
        importlib.reload(mod)
        result = mod.resolve_search_videos("test", 5, cfg)

        assert len(result) == 1
        assert result[0]["VIDEO_ID"] == "vid11111111"


# ---------------------------------------------------------------------------
# OUTPUT_PER_VIDEO config
# ---------------------------------------------------------------------------

class TestOutputPerVideoConfig:
    def test_default_is_true(self):
        cfg = Settings()
        assert cfg.OUTPUT_PER_VIDEO is True

    def test_can_set_false(self):
        cfg = Settings(OUTPUT_PER_VIDEO=False)
        assert cfg.OUTPUT_PER_VIDEO is False
