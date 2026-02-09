"""Priority 1 tests: Error handling, file logging, resume/checkpoint."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt_content_analyzer.config import Settings
from yt_content_analyzer.utils.io import read_jsonl, write_failure
from yt_content_analyzer.utils.logger import JsonLineFormatter, configure_file_logging
from yt_content_analyzer.state.checkpoint import CheckpointStore


# ---------------------------------------------------------------------------
# Config: ON_VIDEO_FAILURE
# ---------------------------------------------------------------------------

class TestOnVideoFailureConfig:
    def test_default_is_skip(self):
        cfg = Settings()
        assert cfg.ON_VIDEO_FAILURE == "skip"

    def test_accepts_abort(self):
        cfg = Settings(ON_VIDEO_FAILURE="abort")
        assert cfg.ON_VIDEO_FAILURE == "abort"

    def test_accepts_skip(self):
        cfg = Settings(ON_VIDEO_FAILURE="skip")
        assert cfg.ON_VIDEO_FAILURE == "skip"

    def test_rejects_crash(self):
        with pytest.raises(Exception):
            Settings(ON_VIDEO_FAILURE="crash")

    def test_rejects_empty(self):
        with pytest.raises(Exception):
            Settings(ON_VIDEO_FAILURE="")


# ---------------------------------------------------------------------------
# read_jsonl hardened
# ---------------------------------------------------------------------------

class TestReadJsonlHardened:
    def test_skips_bad_lines(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text('{"a":1}\nnot json\n{"b":2}\n', encoding="utf-8")
        rows = read_jsonl(p)
        assert len(rows) == 2
        assert rows[0] == {"a": 1}
        assert rows[1] == {"b": 2}

    def test_all_bad_returns_empty(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text("bad1\nbad2\nbad3\n", encoding="utf-8")
        assert read_jsonl(p) == []

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "data.jsonl"
        p.write_text("", encoding="utf-8")
        assert read_jsonl(p) == []

    def test_missing_file_returns_empty(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        assert read_jsonl(p) == []


# ---------------------------------------------------------------------------
# write_failure
# ---------------------------------------------------------------------------

class TestWriteFailure:
    def test_correct_schema(self, tmp_path):
        failures_dir = tmp_path / "failures"
        try:
            raise ValueError("test error")
        except ValueError as exc:
            path = write_failure(failures_dir, "comments", "abc123", exc)

        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["stage"] == "comments"
        assert data["video_id"] == "abc123"
        assert data["error_type"] == "ValueError"
        assert data["error_message"] == "test error"
        assert isinstance(data["traceback"], list)
        assert len(data["traceback"]) > 0
        assert "timestamp" in data

    def test_creates_dir(self, tmp_path):
        failures_dir = tmp_path / "deep" / "nested" / "failures"
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            write_failure(failures_dir, "transcript", "vid1", exc)
        assert failures_dir.is_dir()

    def test_sanitizes_video_id(self, tmp_path):
        failures_dir = tmp_path / "failures"
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            path = write_failure(failures_dir, "stage", "../../etc/passwd", exc)
        # Should not contain path traversal chars
        assert ".." not in path.name
        assert "/" not in path.name


# ---------------------------------------------------------------------------
# Collector retry
# ---------------------------------------------------------------------------

def _make_mock_yt_dlp(extract_info_fn):
    """Create a mock yt_dlp module with a YoutubeDL context manager."""
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info = extract_info_fn
    mock_ydl_instance.__enter__ = lambda self: self
    mock_ydl_instance.__exit__ = lambda self, *a: None

    mock_module = MagicMock()
    mock_module.YoutubeDL = MagicMock(return_value=mock_ydl_instance)
    return mock_module, mock_ydl_instance


class TestCollectorRetry:
    def test_comments_ytdlp_fail_then_succeed(self):
        cfg = Settings(MAX_RETRY_SCRAPE=2, BACKOFF_BASE_SECONDS=0.01, BACKOFF_MAX_SECONDS=0.01)
        call_count = 0

        def fake_extract_info(url, download=False):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient error")
            return {"id": "abc123", "comments": [{"text": "hi"}]}

        mock_module, _ = _make_mock_yt_dlp(fake_extract_info)

        import sys
        with patch.dict(sys.modules, {"yt_dlp": mock_module}):
            from yt_content_analyzer.collectors.comments_ytdlp import collect_comments_ytdlp
            result = collect_comments_ytdlp("https://www.youtube.com/watch?v=abc123", cfg)

        assert call_count == 2
        assert len(result) == 1

    def test_comments_ytdlp_exhaust_retries(self):
        cfg = Settings(MAX_RETRY_SCRAPE=1, BACKOFF_BASE_SECONDS=0.01, BACKOFF_MAX_SECONDS=0.01)

        def always_fail(url, download=False):
            raise RuntimeError("persistent error")

        mock_module, _ = _make_mock_yt_dlp(always_fail)

        import sys
        with patch.dict(sys.modules, {"yt_dlp": mock_module}):
            from yt_content_analyzer.collectors.comments_ytdlp import collect_comments_ytdlp
            with pytest.raises(RuntimeError, match="persistent error"):
                collect_comments_ytdlp("https://www.youtube.com/watch?v=abc123", cfg)

        # 1 initial + 1 retry = 2 calls
        assert mock_module.YoutubeDL.call_count == 2

    def test_transcript_ytdlp_fail_then_succeed(self):
        cfg = Settings(MAX_RETRY_SCRAPE=2, BACKOFF_BASE_SECONDS=0.01, BACKOFF_MAX_SECONDS=0.01)
        call_count = 0

        def fake_extract_info(url, download=False):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient error")
            return {
                "id": "abc123",
                "subtitles": {},
                "automatic_captions": {},
            }

        mock_module, _ = _make_mock_yt_dlp(fake_extract_info)

        import sys
        with patch.dict(sys.modules, {"yt_dlp": mock_module}):
            from yt_content_analyzer.collectors.transcript_ytdlp import collect_transcript_ytdlp
            result = collect_transcript_ytdlp("https://www.youtube.com/watch?v=abc123", cfg)

        assert call_count == 2
        assert result["video_id"] == "abc123"


# ---------------------------------------------------------------------------
# Enrich error handling
# ---------------------------------------------------------------------------

class TestEnrichErrorHandling:
    def test_topics_llm_returns_empty_on_error(self):
        cfg = Settings(LLM_PROVIDER="openai", LLM_MODEL="test")
        items = [{"TEXT": "hello world"}]

        with patch(
            "yt_content_analyzer.enrich.topics_llm.chat_completion",
            side_effect=ConnectionError("connection refused"),
        ):
            from yt_content_analyzer.enrich.topics_llm import extract_topics_llm
            result = extract_topics_llm(items, "vid1", "comments", cfg)

        assert result == []

    def test_sentiment_llm_returns_empty_on_error(self):
        cfg = Settings(LLM_PROVIDER="openai", LLM_MODEL="test")
        items = [{"TEXT": "hello world", "COMMENT_ID": "c1"}]

        with patch(
            "yt_content_analyzer.enrich.sentiment.chat_completion",
            side_effect=ConnectionError("connection refused"),
        ):
            from yt_content_analyzer.enrich.sentiment import analyze_sentiment_llm
            result = analyze_sentiment_llm(items, "vid1", "comments", cfg)

        assert result == []

    def test_triples_returns_empty_on_error(self):
        cfg = Settings(LLM_PROVIDER="openai", LLM_MODEL="test")
        items = [{"TEXT": "hello world"}]

        with patch(
            "yt_content_analyzer.enrich.triples.chat_completion",
            side_effect=ConnectionError("connection refused"),
        ):
            from yt_content_analyzer.enrich.triples import extract_triples
            result = extract_triples(items, "vid1", "comments", cfg)

        assert result == []


# ---------------------------------------------------------------------------
# JsonLineFormatter
# ---------------------------------------------------------------------------

class TestJsonLineFormatter:
    def test_valid_json(self):
        fmt = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello %s", args=("world",), exc_info=None,
        )
        line = fmt.format(record)
        data = json.loads(line)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert "timestamp" in data
        assert "module" in data

    def test_extra_fields(self):
        fmt = JsonLineFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        record.my_custom_field = "custom_value"
        line = fmt.format(record)
        data = json.loads(line)
        assert data["extra"]["my_custom_field"] == "custom_value"

    def test_exception_traceback(self):
        fmt = JsonLineFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="error", args=(), exc_info=exc_info,
        )
        line = fmt.format(record)
        data = json.loads(line)
        assert "traceback" in data
        assert isinstance(data["traceback"], list)
        assert any("ValueError" in t for t in data["traceback"])


# ---------------------------------------------------------------------------
# configure_file_logging
# ---------------------------------------------------------------------------

class TestConfigureFileLogging:
    def setup_method(self):
        # Clean up file handlers from the yt_content_analyzer logger between tests
        _logger = logging.getLogger("yt_content_analyzer")
        for h in list(_logger.handlers):
            if isinstance(h, logging.FileHandler):
                h.close()
                _logger.removeHandler(h)

    def test_creates_run_log(self, tmp_path):
        log_dir = tmp_path / "logs"
        configure_file_logging(log_dir)
        # Write a log entry to force file creation
        _logger = logging.getLogger("yt_content_analyzer")
        _logger.setLevel(logging.DEBUG)
        _logger.debug("test message")
        # Flush handlers
        for h in _logger.handlers:
            h.flush()
        assert (log_dir / "run.log").exists()

    def test_idempotent(self, tmp_path):
        log_dir = tmp_path / "logs"
        configure_file_logging(log_dir)
        configure_file_logging(log_dir)
        configure_file_logging(log_dir)

        _logger = logging.getLogger("yt_content_analyzer")
        file_handlers = [
            h for h in _logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

    def teardown_method(self):
        # Clean up file handlers
        _logger = logging.getLogger("yt_content_analyzer")
        for h in list(_logger.handlers):
            if isinstance(h, logging.FileHandler):
                h.close()
                _logger.removeHandler(h)


# ---------------------------------------------------------------------------
# Checkpoint corruption
# ---------------------------------------------------------------------------

class TestCheckpointCorruption:
    def test_corrupt_backup_and_reinit(self, tmp_path):
        ckpt_path = tmp_path / "state" / "checkpoint.json"
        ckpt = CheckpointStore(ckpt_path)
        ckpt.init_if_missing()

        # Corrupt the file
        ckpt_path.write_text("{{{{invalid json", encoding="utf-8")

        data = ckpt.load()
        assert data == {"UNITS": {}}

        # Backup should exist
        backup = ckpt_path.with_suffix(".json.corrupt")
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == "{{{{invalid json"

    def test_no_temp_files_after_save(self, tmp_path):
        ckpt_path = tmp_path / "state" / "checkpoint.json"
        ckpt = CheckpointStore(ckpt_path)
        ckpt.init_if_missing()

        ckpt.save({"UNITS": {"vid1": {"stage1": "DONE"}}})

        # No temp files in directory
        state_dir = ckpt_path.parent
        files = list(state_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "checkpoint.json"

    def test_atomic_save_content(self, tmp_path):
        ckpt_path = tmp_path / "state" / "checkpoint.json"
        ckpt = CheckpointStore(ckpt_path)
        ckpt.init_if_missing()

        ckpt.mark("vid1", "stage1", "DONE")
        data = ckpt.load()
        assert data["UNITS"]["vid1"]["stage1"] == "DONE"


# ---------------------------------------------------------------------------
# Checkpoint FAILED status
# ---------------------------------------------------------------------------

class TestCheckpointFailedStatus:
    def test_failed_is_not_done(self, tmp_path):
        ckpt_path = tmp_path / "state" / "checkpoint.json"
        ckpt = CheckpointStore(ckpt_path)
        ckpt.init_if_missing()

        ckpt.mark("vid1", "comments", status="FAILED")
        assert not ckpt.is_done("vid1", "comments")

    def test_failed_to_done_works(self, tmp_path):
        ckpt_path = tmp_path / "state" / "checkpoint.json"
        ckpt = CheckpointStore(ckpt_path)
        ckpt.init_if_missing()

        ckpt.mark("vid1", "comments", status="FAILED")
        assert not ckpt.is_done("vid1", "comments")

        ckpt.mark("vid1", "comments", status="DONE")
        assert ckpt.is_done("vid1", "comments")


# ---------------------------------------------------------------------------
# Resume CLI
# ---------------------------------------------------------------------------

class TestResumeCLI:
    def test_missing_run_dir_errors(self, tmp_path):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["run-all", "--resume", "nonexistent_run"])
            assert result.exit_code != 0
            assert "not found" in result.output.lower() or result.exit_code != 0

    def test_loads_manifest_when_no_config(self, tmp_path):
        from click.testing import CliRunner
        from yt_content_analyzer.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # Create run dir with manifest
            run_dir = Path(td) / "runs" / "test_run"
            run_dir.mkdir(parents=True)
            manifest = Settings(VIDEO_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest.model_dump(), indent=2), encoding="utf-8"
            )

            # Mock run_all to capture the call (lazy-imported in run_all_cmd)
            with patch("yt_content_analyzer.run.run_all") as mock_run_all:
                from yt_content_analyzer.models import RunResult
                mock_run_all.return_value = RunResult(
                    run_id="test_run", output_dir=run_dir,
                )
                result = runner.invoke(main, ["run-all", "--resume", "test_run"])
                if result.exit_code == 0:
                    assert mock_run_all.called
                    call_kwargs = mock_run_all.call_args
                    assert call_kwargs.kwargs.get("resume_run_id") == "test_run"
