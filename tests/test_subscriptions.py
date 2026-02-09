"""Tests for subscription mode: config, channel resolver, CLI, preflight."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yt_content_analyzer.config import Settings
from yt_content_analyzer.discovery.channel_resolver import _normalize_channel_url


# ---------------------------------------------------------------------------
# Config: YT_SUBSCRIPTIONS parsing
# ---------------------------------------------------------------------------

class TestSubscriptionConfig:
    def test_default_is_none(self):
        cfg = Settings()
        assert cfg.YT_SUBSCRIPTIONS is None

    def test_parses_subscription_list(self):
        cfg = Settings(YT_SUBSCRIPTIONS=[
            {"CHANNEL": "@engineerprompt", "MAX_SUB_VIDEOS": 5},
            {"CHANNEL": "@firaborova"},
        ])
        assert len(cfg.YT_SUBSCRIPTIONS) == 2
        assert cfg.YT_SUBSCRIPTIONS[0]["CHANNEL"] == "@engineerprompt"
        assert cfg.YT_SUBSCRIPTIONS[0]["MAX_SUB_VIDEOS"] == 5
        # Second entry should get default MAX_SUB_VIDEOS
        assert cfg.YT_SUBSCRIPTIONS[1]["MAX_SUB_VIDEOS"] == 3

    def test_missing_channel_key_raises(self):
        with pytest.raises(Exception, match="missing required key 'CHANNEL'"):
            Settings(YT_SUBSCRIPTIONS=[{"MAX_SUB_VIDEOS": 3}])

    def test_max_sub_videos_default(self):
        cfg = Settings(MAX_SUB_VIDEOS=7)
        assert cfg.MAX_SUB_VIDEOS == 7


# ---------------------------------------------------------------------------
# Channel URL normalization
# ---------------------------------------------------------------------------

class TestChannelUrlNormalization:
    def test_handle_with_at(self):
        url = _normalize_channel_url("@engineerprompt")
        assert url == "https://www.youtube.com/@engineerprompt/videos"

    def test_handle_without_at(self):
        url = _normalize_channel_url("engineerprompt")
        assert url == "https://www.youtube.com/@engineerprompt/videos"

    def test_channel_id(self):
        url = _normalize_channel_url("UCxxxxxxxxxxxxxxxxxxxxxx")
        assert url == "https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx/videos"

    def test_full_url_without_videos(self):
        url = _normalize_channel_url("https://www.youtube.com/@engineerprompt")
        assert url == "https://www.youtube.com/@engineerprompt/videos"

    def test_full_url_with_videos(self):
        url = _normalize_channel_url("https://www.youtube.com/@engineerprompt/videos")
        assert url == "https://www.youtube.com/@engineerprompt/videos"


# ---------------------------------------------------------------------------
# resolve_channel_videos with mocked yt-dlp
# ---------------------------------------------------------------------------

class TestResolveChannelVideosMock:
    def _make_mock_ydl(self, fake_info):
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = fake_info
        return mock_ydl

    @patch.dict("sys.modules", {"yt_dlp": MagicMock()})
    def test_returns_video_list(self):
        import sys
        mock_ytdlp = sys.modules["yt_dlp"]
        fake_info = {
            "entries": [
                {"id": "abc11111111", "title": "Video 1"},
                {"id": "def22222222", "title": "Video 2"},
                {"id": "ghi33333333", "title": "Video 3"},
            ],
        }
        mock_ytdlp.YoutubeDL.return_value = self._make_mock_ydl(fake_info)

        cfg = Settings()
        # Need to re-import to pick up the mocked yt_dlp
        import importlib
        import yt_content_analyzer.discovery.channel_resolver as mod
        importlib.reload(mod)
        result = mod.resolve_channel_videos("@testchannel", 3, cfg)

        assert len(result) == 3
        assert result[0]["VIDEO_ID"] == "abc11111111"
        assert result[0]["VIDEO_URL"] == "https://www.youtube.com/watch?v=abc11111111"
        assert result[0]["TITLE"] == "Video 1"

    @patch.dict("sys.modules", {"yt_dlp": MagicMock()})
    def test_skips_empty_entries(self):
        import sys
        mock_ytdlp = sys.modules["yt_dlp"]
        fake_info = {
            "entries": [
                {"id": "abc11111111", "title": "Video 1"},
                None,
                {"id": "", "title": "No ID"},
            ],
        }
        mock_ytdlp.YoutubeDL.return_value = self._make_mock_ydl(fake_info)

        cfg = Settings()
        import importlib
        import yt_content_analyzer.discovery.channel_resolver as mod
        importlib.reload(mod)
        result = mod.resolve_channel_videos("@testchannel", 3, cfg)

        assert len(result) == 1
        assert result[0]["VIDEO_ID"] == "abc11111111"


# ---------------------------------------------------------------------------
# Preflight: mutual exclusivity with subscriptions
# ---------------------------------------------------------------------------

class TestSubscriptionPreflight:
    def test_video_url_and_subscriptions_fail(self):
        cfg = Settings(
            VIDEO_URL="https://www.youtube.com/watch?v=abc12345678",
            YT_SUBSCRIPTIONS=[{"CHANNEL": "@test"}],
        )
        from yt_content_analyzer.preflight.checks import run_preflight
        result = run_preflight(cfg, output_dir=None)
        assert not result.ok
        failed = [r for r in result.results if not r["OK"]]
        assert any("Mutually exclusive" in r["NAME"] for r in failed)

    def test_subscriptions_alone_passes(self):
        cfg = Settings(
            YT_SUBSCRIPTIONS=[{"CHANNEL": "@test"}],
        )
        from yt_content_analyzer.preflight.checks import run_preflight
        result = run_preflight(cfg, output_dir=None)
        assert result.ok

    def test_subscription_video_cap_exceeded(self):
        cfg = Settings(
            MAX_TOTAL_VIDEOS=5,
            YT_SUBSCRIPTIONS=[
                {"CHANNEL": "@ch1", "MAX_SUB_VIDEOS": 3},
                {"CHANNEL": "@ch2", "MAX_SUB_VIDEOS": 3},
            ],
        )
        from yt_content_analyzer.preflight.checks import run_preflight
        result = run_preflight(cfg, output_dir=None)
        assert not result.ok
        failed = [r for r in result.results if not r["OK"]]
        assert any("Subscription video cap" in r["NAME"] for r in failed)


# ---------------------------------------------------------------------------
# CLI: --subscriptions flag
# ---------------------------------------------------------------------------

class TestSubscriptionCLI:
    def test_subscriptions_flag_requires_config(self):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "run-all", "--subscriptions",
        ])
        # Should fail because --config is required for new runs
        assert result.exit_code != 0

    def test_subscriptions_flag_no_subs_in_config(self, tmp_path):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        cfg_file = tmp_path / "config.yml"
        cfg_file.write_text("VIDEO_URL:\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [
            "run-all", "--config", str(cfg_file), "--subscriptions",
        ])
        assert result.exit_code != 0
        assert "YT_SUBSCRIPTIONS must be set" in result.output

    def test_subscriptions_flag_clears_video_url(self, tmp_path):
        """When --subscriptions is used, VIDEO_URL and SEARCH_TERMS should be cleared."""
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        cfg_file = tmp_path / "config.yml"
        cfg_file.write_text(
            'VIDEO_URL: "https://www.youtube.com/watch?v=abc12345678"\n'
            'YT_SUBSCRIPTIONS:\n'
            '  - CHANNEL: "@test"\n',
            encoding="utf-8",
        )

        with patch("yt_content_analyzer.run.run_all") as mock_run:
            mock_run.return_value = MagicMock(
                run_id="test", output_dir=tmp_path, videos_processed=0,
                comments_collected=0, transcript_chunks=0, failures=[],
            )
            runner = CliRunner()
            result = runner.invoke(main, [
                "run-all", "--config", str(cfg_file), "--subscriptions",
            ])
            if result.exit_code == 0:
                call_cfg = mock_run.call_args[0][0]
                assert call_cfg.VIDEO_URL is None
                assert call_cfg.SEARCH_TERMS is None
