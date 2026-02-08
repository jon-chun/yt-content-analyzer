from __future__ import annotations

import pytest

from yt_content_analyzer.config import Settings
from yt_content_analyzer.run import extract_video_id
from yt_content_analyzer.parse.normalize_transcripts import normalize_transcripts
from yt_content_analyzer.parse.normalize_comments import normalize_comments
from yt_content_analyzer.parse.chunk_transcripts import chunk_transcripts


# ---------------------------------------------------------------------------
# extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    def test_standard_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=qhuS__jC4n8") == "qhuS__jC4n8"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/qhuS__jC4n8") == "qhuS__jC4n8"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/qhuS__jC4n8") == "qhuS__jC4n8"

    def test_v_url(self):
        assert extract_video_id("https://www.youtube.com/v/qhuS__jC4n8") == "qhuS__jC4n8"

    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=qhuS__jC4n8&list=PLxyz&index=3"
        assert extract_video_id(url) == "qhuS__jC4n8"

    def test_no_www(self):
        assert extract_video_id("https://youtube.com/watch?v=qhuS__jC4n8") == "qhuS__jC4n8"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("https://example.com/not-youtube")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("")


# ---------------------------------------------------------------------------
# normalize_transcripts
# ---------------------------------------------------------------------------

def _make_cfg(**overrides) -> Settings:
    return Settings(**overrides)


class TestNormalizeTranscripts:
    def test_basic_schema(self):
        raw = {
            "video_id": "abc123",
            "source": "auto",
            "lang": "en",
            "entries": [
                {"text": "Hello world", "start": 0.0, "duration": 2.5},
                {"text": "Second segment", "start": 2.5, "duration": 3.0},
            ],
        }
        cfg = _make_cfg()
        result = normalize_transcripts(raw, "abc123", cfg)

        assert len(result) == 2
        seg = result[0]
        assert seg["VIDEO_ID"] == "abc123"
        assert seg["SEGMENT_INDEX"] == 0
        assert seg["START_S"] == 0.0
        assert seg["END_S"] == 2.5
        assert seg["TEXT"] == "Hello world"
        assert seg["SPEAKER"] == ""
        assert seg["SOURCE"] == "auto"
        assert seg["LANG"] == "en"

    def test_char_limit_truncation(self):
        raw = {
            "video_id": "vid1",
            "source": "manual",
            "lang": "en",
            "entries": [
                {"text": "A" * 50, "start": 0.0, "duration": 1.0},
                {"text": "B" * 50, "start": 1.0, "duration": 1.0},
                {"text": "C" * 50, "start": 2.0, "duration": 1.0},
            ],
        }
        cfg = _make_cfg(MAX_TRANSCRIPT_CHARS_PER_VIDEO=80)
        result = normalize_transcripts(raw, "vid1", cfg)

        # First segment: 50 chars, total=50
        # Second segment: needs 50 more but only 30 remain -> truncated to 30
        assert len(result) == 2
        assert len(result[0]["TEXT"]) == 50
        assert len(result[1]["TEXT"]) == 30

    def test_empty_input(self):
        raw = {"video_id": "vid1", "source": "none", "lang": "", "entries": []}
        cfg = _make_cfg()
        assert normalize_transcripts(raw, "vid1", cfg) == []


# ---------------------------------------------------------------------------
# normalize_comments
# ---------------------------------------------------------------------------

class TestNormalizeComments:
    def test_top_level_comment(self):
        raw = [
            {
                "id": "c1",
                "parent": "root",
                "author": "Alice",
                "text": "Great video!",
                "like_count": 10,
                "timestamp": 1700000000,
            }
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)

        assert len(result) == 1
        c = result[0]
        assert c["VIDEO_ID"] == "vid1"
        assert c["COMMENT_ID"] == "c1"
        assert c["PARENT_ID"] == ""
        assert c["AUTHOR"] == "Alice"
        assert c["TEXT"] == "Great video!"
        assert c["LIKE_COUNT"] == 10
        assert c["REPLY_COUNT"] == 0
        assert c["SORT_MODE"] == "default"
        assert c["THREAD_DEPTH"] == 0
        assert "2023-11-14" in c["PUBLISHED_AT"]

    def test_reply_comment(self):
        raw = [
            {
                "id": "c2",
                "parent": "c1",
                "author": "Bob",
                "text": "I agree!",
                "like_count": 3,
                "timestamp": 1700100000,
            }
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)

        assert result[0]["PARENT_ID"] == "c1"
        assert result[0]["THREAD_DEPTH"] == 1

    def test_missing_timestamp(self):
        raw = [
            {
                "id": "c3",
                "parent": "root",
                "author": "Eve",
                "text": "No timestamp",
                "like_count": 0,
            }
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["PUBLISHED_AT"] == ""

    def test_empty_input(self):
        cfg = _make_cfg()
        assert normalize_comments([], "vid1", cfg) == []

    def test_none_like_count(self):
        raw = [
            {
                "id": "c4",
                "parent": "root",
                "author": "X",
                "text": "test",
                "like_count": None,
                "timestamp": 1700000000,
            }
        ]
        cfg = _make_cfg()
        result = normalize_comments(raw, "vid1", cfg)
        assert result[0]["LIKE_COUNT"] == 0


# ---------------------------------------------------------------------------
# chunk_transcripts
# ---------------------------------------------------------------------------

class TestChunkTranscripts:
    def _make_segments(self, count, duration=5.0):
        return [
            {
                "VIDEO_ID": "vid1",
                "SEGMENT_INDEX": i,
                "START_S": i * duration,
                "END_S": (i + 1) * duration,
                "TEXT": f"Segment {i}",
                "SPEAKER": "",
                "SOURCE": "auto",
                "LANG": "en",
            }
            for i in range(count)
        ]

    def test_basic_chunking(self):
        # 12 segments of 5s each = 60s total
        # Window=30s, overlap=5s, step=25s
        segments = self._make_segments(12)
        cfg = _make_cfg(TRANSCRIPT_CHUNK_SECONDS=30, TRANSCRIPT_CHUNK_OVERLAP_SECONDS=5)
        chunks = chunk_transcripts(segments, cfg)

        assert len(chunks) >= 2
        assert chunks[0]["CHUNK_INDEX"] == 0
        assert chunks[0]["START_S"] == 0.0
        assert chunks[0]["VIDEO_ID"] == "vid1"
        assert chunks[0]["OVERLAP_S"] == 0.0  # first chunk has no overlap
        assert chunks[1]["OVERLAP_S"] == 5.0  # subsequent chunks have overlap

    def test_chunking_with_overlap_segments(self):
        # Verify that overlapping windows share segments
        segments = self._make_segments(12)
        cfg = _make_cfg(TRANSCRIPT_CHUNK_SECONDS=30, TRANSCRIPT_CHUNK_OVERLAP_SECONDS=10)
        chunks = chunk_transcripts(segments, cfg)

        if len(chunks) >= 2:
            # Check overlapping indices between chunk 0 and chunk 1
            idx0 = set(chunks[0]["SEGMENT_INDICES"])
            idx1 = set(chunks[1]["SEGMENT_INDICES"])
            assert idx0 & idx1, "Overlapping chunks should share segment indices"

    def test_empty_segments(self):
        cfg = _make_cfg()
        assert chunk_transcripts([], cfg) == []

    def test_single_segment(self):
        segments = self._make_segments(1)
        cfg = _make_cfg(TRANSCRIPT_CHUNK_SECONDS=60, TRANSCRIPT_CHUNK_OVERLAP_SECONDS=10)
        chunks = chunk_transcripts(segments, cfg)

        assert len(chunks) == 1
        assert chunks[0]["CHUNK_INDEX"] == 0
        assert chunks[0]["TEXT"] == "Segment 0"
        assert chunks[0]["SEGMENT_INDICES"] == [0]

    def test_chunk_text_joins_segments(self):
        segments = self._make_segments(3, duration=10.0)
        # One big window covering all segments
        cfg = _make_cfg(TRANSCRIPT_CHUNK_SECONDS=60, TRANSCRIPT_CHUNK_OVERLAP_SECONDS=0)
        chunks = chunk_transcripts(segments, cfg)

        assert len(chunks) == 1
        assert chunks[0]["TEXT"] == "Segment 0 Segment 1 Segment 2"
