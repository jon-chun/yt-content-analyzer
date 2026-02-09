from __future__ import annotations

import json
import io
from unittest.mock import patch, MagicMock

import pytest

from yt_content_analyzer.config import Settings
from yt_content_analyzer.enrich.llm_client import (
    chat_completion,
    get_embeddings,
    parse_json_response,
    _resolve_base_url,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(**overrides) -> Settings:
    """Create a Settings instance with sensible defaults for testing."""
    defaults = {
        "LLM_PROVIDER": None,
        "LLM_MODEL": None,
        "LLM_ENDPOINT": None,
        "EMBEDDINGS_ENABLE": True,
        "EMBEDDINGS_PROVIDER": "local",
        "EMBEDDINGS_MODEL": None,
        "EMBEDDINGS_ENDPOINT": "http://localhost:1234/v1",
        "EMBEDDINGS_TIMEOUT_S": 5,
        "EMBEDDINGS_FALLBACK_TO_SAMPLING": True,
        "API_MAX_RETRIES": 2,
        "BACKOFF_BASE_SECONDS": 0.01,
        "BACKOFF_MAX_SECONDS": 0.1,
        "API_TIMEOUT_S": 5,
        "TM_CLUSTERING": "nlp",
        "TOPIC_SAMPLING_MAX_COMMENTS_PER_VIDEO": 100,
        "TOPIC_SAMPLING_MAX_TRANSCRIPT_CHUNKS_PER_VIDEO": 50,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_urlopen_response(data: dict, status: int = 200):
    """Create a mock response for urllib.request.urlopen."""
    body = json.dumps(data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.status = status
    return resp


def _sample_items(n: int = 30, asset_type: str = "comments") -> list[dict]:
    """Generate sample items for testing."""
    items = []
    for i in range(n):
        item = {"TEXT": f"This is sample text number {i} about artificial intelligence and technology."}
        if asset_type == "comments":
            item["COMMENT_ID"] = f"comment_{i}"
        else:
            item["CHUNK_INDEX"] = i
        items.append(item)
    return items


# ===========================================================================
# LLM Client Tests
# ===========================================================================

class TestChatCompletion:
    def test_chat_completion_success(self):
        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        resp_data = {
            "choices": [{"message": {"content": "Hello, world!"}}]
        }
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            result = chat_completion(cfg, [{"role": "user", "content": "Hi"}])
            assert result == "Hello, world!"

    def test_chat_completion_retry_on_429(self):
        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")

        # First call raises 429, second succeeds
        import urllib.error
        error_429 = urllib.error.HTTPError(
            url="http://localhost:1234/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"rate limited"),
        )
        resp_data = {"choices": [{"message": {"content": "Success after retry"}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch(
            "yt_content_analyzer.enrich.llm_client.urllib.request.urlopen",
            side_effect=[error_429, mock_resp],
        ):
            result = chat_completion(cfg, [{"role": "user", "content": "Hi"}])
            assert result == "Success after retry"


class TestGetEmbeddings:
    def test_get_embeddings_success(self):
        cfg = _make_cfg()
        resp_data = {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                {"index": 1, "embedding": [0.4, 0.5, 0.6]},
            ]
        }
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            result = get_embeddings(cfg, ["hello", "world"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2, 0.3]
            assert result[1] == [0.4, 0.5, 0.6]


class TestParseJsonResponse:
    def test_parse_json_response_strips_fences(self):
        text = '```json\n{"topics": [{"label": "AI"}]}\n```'
        result = parse_json_response(text)
        assert result == {"topics": [{"label": "AI"}]}

    def test_parse_json_response_plain(self):
        text = '{"key": "value"}'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_parse_json_response_with_preamble(self):
        text = 'Here is the result:\n{"key": "value"}\nDone.'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_parse_json_response_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            parse_json_response("not json at all")


class TestProviderUrlResolution:
    def test_known_providers(self):
        assert _resolve_base_url("openai", None) == "https://api.openai.com/v1"
        assert _resolve_base_url("deepseek", None) == "https://api.deepseek.com/v1"
        assert _resolve_base_url("xai", None) == "https://api.x.ai/v1"
        assert _resolve_base_url("together", None) == "https://api.together.xyz/v1"
        assert _resolve_base_url("fireworks", None) == "https://api.fireworks.ai/inference/v1"

    def test_local_with_endpoint(self):
        assert _resolve_base_url("local", "http://localhost:8080/v1") == "http://localhost:8080/v1"

    def test_ollama_with_endpoint(self):
        assert _resolve_base_url("ollama", "http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_custom_endpoint_overrides(self):
        assert _resolve_base_url("openai", "http://custom:9999/v1") == "http://custom:9999/v1"


# ===========================================================================
# Topics Tests
# ===========================================================================

class TestTopicsNlp:
    def test_extract_topics_nlp_tfidf_fallback(self):
        from yt_content_analyzer.enrich.topics_nlp import extract_topics_nlp

        cfg = _make_cfg()
        items = _sample_items(30)
        results = extract_topics_nlp(items, "vid123", "comments", cfg)

        assert len(results) > 0
        for r in results:
            assert "VIDEO_ID" in r
            assert "ASSET_TYPE" in r
            assert "TOPIC_ID" in r
            assert "LABEL" in r
            assert "KEYWORDS" in r
            assert "REPRESENTATIVE_TEXTS" in r
            assert "SCORE" in r
            assert r["VIDEO_ID"] == "vid123"
            assert r["ASSET_TYPE"] == "comments"

    def test_extract_topics_nlp_with_embeddings(self):
        from yt_content_analyzer.enrich.topics_nlp import extract_topics_nlp
        import numpy as np

        cfg = _make_cfg()
        items = _sample_items(30)
        # Create fake embeddings with some structure (2 clusters)
        rng = np.random.RandomState(42)
        embeddings = []
        for i in range(30):
            if i < 15:
                embeddings.append((rng.randn(10) + [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]).tolist())
            else:
                embeddings.append((rng.randn(10) + [0, 0, 0, 0, 0, 0, 0, 0, 0, 1]).tolist())

        results = extract_topics_nlp(items, "vid456", "transcripts", cfg, embeddings)

        assert len(results) > 0
        for r in results:
            assert r["VIDEO_ID"] == "vid456"
            assert r["ASSET_TYPE"] == "transcripts"
            assert isinstance(r["KEYWORDS"], list)
            assert isinstance(r["SCORE"], float)

    def test_extract_topics_empty_input(self):
        from yt_content_analyzer.enrich.topics_nlp import extract_topics_nlp

        cfg = _make_cfg()
        assert extract_topics_nlp([], "vid", "comments", cfg) == []


class TestTopicsLlm:
    def test_extract_topics_llm(self):
        from yt_content_analyzer.enrich.topics_llm import extract_topics_llm

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        items = _sample_items(10)

        llm_response = json.dumps({
            "topics": [
                {
                    "label": "AI Technology",
                    "keywords": ["ai", "technology", "artificial"],
                    "representative_indices": [0, 1, 2],
                    "score": 0.7,
                },
                {
                    "label": "Sample Content",
                    "keywords": ["sample", "text", "content"],
                    "representative_indices": [3, 4],
                    "score": 0.3,
                },
            ]
        })

        resp_data = {"choices": [{"message": {"content": llm_response}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            results = extract_topics_llm(items, "vid789", "comments", cfg)

        assert len(results) == 2
        assert results[0]["LABEL"] == "AI Technology"
        assert results[0]["VIDEO_ID"] == "vid789"
        assert results[1]["SCORE"] == 0.3


# ===========================================================================
# Sentiment Tests
# ===========================================================================

class TestSentimentNlp:
    def test_analyze_sentiment_nlp_positive(self):
        from yt_content_analyzer.enrich.sentiment import analyze_sentiment_nlp

        cfg = _make_cfg()
        items = [{"TEXT": "This is absolutely wonderful and amazing!", "COMMENT_ID": "c1"}]
        results = analyze_sentiment_nlp(items, "vid1", "comments", cfg)

        assert len(results) == 1
        assert results[0]["POLARITY"] == "positive"
        assert results[0]["SCORE"] > 0.1

    def test_analyze_sentiment_nlp_negative(self):
        from yt_content_analyzer.enrich.sentiment import analyze_sentiment_nlp

        cfg = _make_cfg()
        items = [{"TEXT": "This is terrible, horrible, and disgusting.", "COMMENT_ID": "c2"}]
        results = analyze_sentiment_nlp(items, "vid1", "comments", cfg)

        assert len(results) == 1
        assert results[0]["POLARITY"] == "negative"
        assert results[0]["SCORE"] < -0.1

    def test_analyze_sentiment_nlp_schema(self):
        from yt_content_analyzer.enrich.sentiment import analyze_sentiment_nlp

        cfg = _make_cfg()
        items = [{"TEXT": "Some neutral text here.", "COMMENT_ID": "c3"}]
        results = analyze_sentiment_nlp(items, "vid1", "comments", cfg)

        assert len(results) == 1
        required_keys = {"VIDEO_ID", "ASSET_TYPE", "ITEM_ID", "POLARITY", "SCORE", "TEXT_EXCERPT"}
        assert required_keys == set(results[0].keys())

    def test_analyze_sentiment_dispatch_no_llm(self):
        from yt_content_analyzer.enrich.sentiment import analyze_sentiment

        cfg = _make_cfg(LLM_PROVIDER=None)
        items = [{"TEXT": "Great video!", "COMMENT_ID": "c4"}]

        # Should use NLP path (no LLM provider)
        results = analyze_sentiment(items, "vid1", "comments", cfg)
        assert len(results) == 1
        assert results[0]["POLARITY"] in ("positive", "negative", "neutral")


class TestSentimentLlm:
    def test_analyze_sentiment_llm(self):
        from yt_content_analyzer.enrich.sentiment import analyze_sentiment_llm

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        items = [
            {"TEXT": "Great stuff!", "COMMENT_ID": "c1"},
            {"TEXT": "Terrible video.", "COMMENT_ID": "c2"},
        ]

        llm_response = json.dumps({
            "results": [
                {"id": "c1", "polarity": "positive", "score": 0.85},
                {"id": "c2", "polarity": "negative", "score": -0.75},
            ]
        })
        resp_data = {"choices": [{"message": {"content": llm_response}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            results = analyze_sentiment_llm(items, "vid1", "comments", cfg)

        assert len(results) == 2
        assert results[0]["POLARITY"] == "positive"
        assert results[0]["SCORE"] == 0.85
        assert results[1]["POLARITY"] == "negative"


# ===========================================================================
# Triples Tests
# ===========================================================================

class TestTriples:
    def test_extract_triples_no_llm(self):
        from yt_content_analyzer.enrich.triples import extract_triples

        cfg = _make_cfg(LLM_PROVIDER=None)
        items = _sample_items(5)
        results = extract_triples(items, "vid1", "comments", cfg)
        assert results == []

    def test_extract_triples_with_llm(self):
        from yt_content_analyzer.enrich.triples import extract_triples

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        items = [
            {"TEXT": "Python is a programming language created by Guido van Rossum.", "COMMENT_ID": "c1"},
        ]

        llm_response = json.dumps({
            "triples": [
                {
                    "subject": "Python",
                    "predicate": "is",
                    "object": "programming language",
                    "confidence": 0.95,
                    "source_index": 0,
                },
                {
                    "subject": "Guido van Rossum",
                    "predicate": "created",
                    "object": "Python",
                    "confidence": 0.9,
                    "source_index": 0,
                },
            ]
        })
        resp_data = {"choices": [{"message": {"content": llm_response}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            results = extract_triples(items, "vid1", "comments", cfg)

        assert len(results) == 2
        required_keys = {"VIDEO_ID", "ASSET_TYPE", "SUBJECT", "PREDICATE", "OBJECT", "CONFIDENCE", "SOURCE_TEXT"}
        for r in results:
            assert required_keys == set(r.keys())
        assert results[0]["SUBJECT"] == "Python"
        assert results[1]["PREDICATE"] == "created"

    def test_extract_triples_empty_input(self):
        from yt_content_analyzer.enrich.triples import extract_triples

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        assert extract_triples([], "vid1", "comments", cfg) == []


# ===========================================================================
# Embeddings Client Tests
# ===========================================================================

class TestEmbeddingsClient:
    def test_compute_embeddings_disabled(self):
        from yt_content_analyzer.enrich.embeddings_client import compute_embeddings

        cfg = _make_cfg(EMBEDDINGS_ENABLE=False)
        result = compute_embeddings(["hello"], cfg)
        assert result is None

    def test_compute_embeddings_empty(self):
        from yt_content_analyzer.enrich.embeddings_client import compute_embeddings

        cfg = _make_cfg()
        result = compute_embeddings([], cfg)
        assert result == []

    def test_compute_embeddings_fallback_on_error(self):
        from yt_content_analyzer.enrich.embeddings_client import compute_embeddings

        cfg = _make_cfg(EMBEDDINGS_FALLBACK_TO_SAMPLING=True)

        with patch(
            "yt_content_analyzer.enrich.embeddings_client.get_embeddings",
            side_effect=RuntimeError("connection refused"),
        ):
            result = compute_embeddings(["hello"], cfg)
            assert result is None


# ===========================================================================
# IO Tests
# ===========================================================================

# ===========================================================================
# URL Extraction Tests
# ===========================================================================

class TestUrlExtraction:
    def test_basic_extraction(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        items = [
            {"TEXT": "Check out https://example.com/page and https://foo.org", "COMMENT_ID": "c1"},
            {"TEXT": "Also https://example.com/page is great", "COMMENT_ID": "c2"},
        ]
        results = extract_urls(items, "vid1", "comments", cfg)

        assert len(results) == 2
        # Most mentioned first
        assert results[0]["URL"] == "https://example.com/page"
        assert results[0]["MENTION_COUNT"] == 2
        assert results[0]["DOMAIN"] == "example.com"
        assert results[0]["FIRST_SEEN_ITEM_ID"] == "c1"
        assert results[1]["URL"] == "https://foo.org"
        assert results[1]["MENTION_COUNT"] == 1

    def test_schema_completeness(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        items = [{"TEXT": "Visit https://example.com", "COMMENT_ID": "c1"}]
        results = extract_urls(items, "vid1", "comments", cfg)

        assert len(results) == 1
        required_keys = {
            "VIDEO_ID", "ASSET_TYPE", "URL", "DOMAIN",
            "MENTION_COUNT", "FIRST_SEEN_ITEM_ID",
        }
        assert required_keys == set(results[0].keys())
        assert results[0]["VIDEO_ID"] == "vid1"
        assert results[0]["ASSET_TYPE"] == "comments"

    def test_empty_input(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        assert extract_urls([], "vid1", "comments", cfg) == []

    def test_no_urls_in_text(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        items = [{"TEXT": "No links here, just plain text!", "COMMENT_ID": "c1"}]
        assert extract_urls(items, "vid1", "comments", cfg) == []

    def test_transcript_chunk_item_id(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        items = [{"TEXT": "See https://docs.python.org", "CHUNK_INDEX": 7}]
        results = extract_urls(items, "vid1", "transcripts", cfg)

        assert len(results) == 1
        assert results[0]["FIRST_SEEN_ITEM_ID"] == "7"

    def test_trailing_punctuation_cleanup(self):
        from yt_content_analyzer.enrich.url_extraction import extract_urls

        cfg = _make_cfg()
        items = [
            {"TEXT": "Visit https://example.com/path.", "COMMENT_ID": "c1"},
            {"TEXT": "(see https://example.com/wiki_(test))", "COMMENT_ID": "c2"},
        ]
        results = extract_urls(items, "vid1", "comments", cfg)

        urls = {r["URL"] for r in results}
        assert "https://example.com/path" in urls
        # Matched parens should be preserved, unmatched trailing ')' stripped
        assert "https://example.com/wiki_(test)" in urls


# ===========================================================================
# Summarization Tests
# ===========================================================================

class TestSummarization:
    def test_no_llm_provider(self):
        from yt_content_analyzer.enrich.summarization import summarize_content

        cfg = _make_cfg(LLM_PROVIDER=None)
        items = _sample_items(10)
        assert summarize_content(items, "vid1", "comments", cfg) == []

    def test_with_mocked_llm(self):
        from yt_content_analyzer.enrich.summarization import summarize_content

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        items = _sample_items(5)

        llm_response = json.dumps({
            "summary": "People discuss AI and technology.",
            "key_themes": ["AI", "technology", "future"],
            "tone": "informative",
        })
        resp_data = {"choices": [{"message": {"content": llm_response}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            results = summarize_content(items, "vid1", "comments", cfg)

        assert len(results) == 1
        required_keys = {
            "VIDEO_ID", "ASSET_TYPE", "SUMMARY", "KEY_THEMES",
            "TONE", "ITEM_COUNT", "ITEM_COUNT_ANALYZED",
        }
        assert required_keys == set(results[0].keys())
        assert results[0]["VIDEO_ID"] == "vid1"
        assert results[0]["ASSET_TYPE"] == "comments"
        assert results[0]["SUMMARY"] == "People discuss AI and technology."
        assert results[0]["KEY_THEMES"] == ["AI", "technology", "future"]
        assert results[0]["TONE"] == "informative"
        assert results[0]["ITEM_COUNT"] == 5
        assert results[0]["ITEM_COUNT_ANALYZED"] == 5

    def test_empty_input(self):
        from yt_content_analyzer.enrich.summarization import summarize_content

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        assert summarize_content([], "vid1", "comments", cfg) == []

    def test_sampling_respects_max_items(self):
        from yt_content_analyzer.enrich.summarization import summarize_content

        cfg = _make_cfg(
            LLM_PROVIDER="local",
            LLM_ENDPOINT="http://localhost:1234/v1",
            SUMMARY_MAX_ITEMS=50,
        )
        items = _sample_items(300)

        llm_response = json.dumps({
            "summary": "Summary of sampled items.",
            "key_themes": ["theme1"],
            "tone": "neutral",
        })
        resp_data = {"choices": [{"message": {"content": llm_response}}]}
        mock_resp = _mock_urlopen_response(resp_data)

        with patch("yt_content_analyzer.enrich.llm_client.urllib.request.urlopen", return_value=mock_resp):
            results = summarize_content(items, "vid1", "comments", cfg)

        assert len(results) == 1
        assert results[0]["ITEM_COUNT"] == 300
        assert results[0]["ITEM_COUNT_ANALYZED"] <= 50

    def test_llm_failure_returns_empty(self):
        from yt_content_analyzer.enrich.summarization import summarize_content

        cfg = _make_cfg(LLM_PROVIDER="local", LLM_ENDPOINT="http://localhost:1234/v1")
        items = _sample_items(5)

        with patch(
            "yt_content_analyzer.enrich.llm_client.urllib.request.urlopen",
            side_effect=RuntimeError("connection refused"),
        ):
            results = summarize_content(items, "vid1", "comments", cfg)

        assert results == []


# ===========================================================================
# IO Tests
# ===========================================================================

class TestReadJsonl:
    def test_read_jsonl_missing_file(self, tmp_path):
        from yt_content_analyzer.utils.io import read_jsonl

        result = read_jsonl(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_read_jsonl_roundtrip(self, tmp_path):
        from yt_content_analyzer.utils.io import read_jsonl, write_jsonl

        path = tmp_path / "test.jsonl"
        rows = [{"a": 1, "b": "hello"}, {"a": 2, "b": "world"}]
        write_jsonl(path, rows)
        result = read_jsonl(path)
        assert result == rows
