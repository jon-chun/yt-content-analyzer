from __future__ import annotations
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml  # type: ignore[import-untyped]
from pathlib import Path
from typing import Any, Optional

# Canonical env var names per provider — code resolves API keys at runtime,
# so users only need standard env vars (OPENAI_API_KEY, etc.)
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "together": "TOGETHER_API_KEY",
}

def resolve_api_key(provider: str) -> str | None:
    """Resolve API key from canonical environment variable for a given provider."""
    if provider in ("local", "ollama", "none", ""):
        return None
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var:
        return os.environ.get(env_var)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Inputs
    VIDEO_URL: Optional[str] = None
    SEARCH_TERMS: Optional[list[str]] = None
    YT_SUBSCRIPTIONS: Optional[list[dict[str, Any]]] = None
    MAX_SUB_VIDEOS: int = 3
    MAX_VIDEOS_PER_TERM: int = 10
    MAX_TOTAL_VIDEOS: int = 500

    # Filters
    VIDEO_LANG: list[str] = ["en"]
    VIDEO_LANG_MAIN: str = "en"
    VIDEO_REGION: list[str] = ["us"]
    VIDEO_UPLOAD_DATE: str = "last_year"
    MIN_VIEWS: int = 1000
    EXCLUDE_LIVE: bool = True
    INCLUDE_SHORTS: bool = False

    # Collection
    MAX_COMMENT_THREAD_DEPTH: int = 5
    MAX_RETRY_SCRAPE: int = 3
    COLLECT_SORT_MODES: list[str] = ["top", "newest"]
    MAX_COMMENTS_PER_VIDEO: int = 200_000
    CAPTURE_ARTIFACTS_ON_ERROR: bool = True
    CAPTURE_ARTIFACTS_ALWAYS: bool = False
    ON_VIDEO_FAILURE: str = "skip"

    @field_validator("ON_VIDEO_FAILURE")
    @classmethod
    def _validate_on_video_failure(cls, v: str) -> str:
        if v not in ("skip", "abort"):
            raise ValueError(f"ON_VIDEO_FAILURE must be 'skip' or 'abort', got {v!r}")
        return v

    @field_validator("YT_SUBSCRIPTIONS")
    @classmethod
    def _validate_yt_subscriptions(
        cls, v: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        if v is None:
            return None
        for i, entry in enumerate(v):
            if "CHANNEL" not in entry:
                raise ValueError(
                    f"YT_SUBSCRIPTIONS[{i}] missing required key 'CHANNEL'"
                )
            entry.setdefault("MAX_SUB_VIDEOS", 3)
        return v

    # Transcripts
    TRANSCRIPTS_ENABLE: bool = True
    TRANSCRIPTS_PREFER_MANUAL: bool = True
    TRANSCRIPTS_ALLOW_AUTO: bool = True
    TRANSCRIPTS_LANG_PREFERENCE: list[str] = ["en"]
    TRANSCRIPTS_UI_FALLBACK: bool = True
    TRANSCRIPTS_YTDLP_FALLBACK: bool = True
    MAX_TRANSCRIPT_CHARS_PER_VIDEO: int = 2_000_000
    TRANSCRIPT_CHUNK_MODE: str = "time"
    TRANSCRIPT_CHUNK_SECONDS: int = 60
    TRANSCRIPT_CHUNK_OVERLAP_SECONDS: int = 10

    # Rate limiting / API safeguards
    API_MAX_CONCURRENT_CALLS: int = 2
    API_RATE_LIMIT_RPS: float = 2.0
    API_RATE_LIMIT_BURST: int = 4
    API_COOLDOWN_ON_ERROR_S: int = 10
    API_JITTER_MS_MIN: int = 250
    API_JITTER_MS_MAX: int = 900
    API_TIMEOUT_S: int = 30
    API_MAX_RETRIES: int = 3
    BACKOFF_BASE_SECONDS: float = 2.0
    BACKOFF_MAX_SECONDS: float = 60.0

    # Translation — provider-based auth (API key resolved from env)
    AUTO_TRANSLATE: bool = False
    TRANSLATE_PROVIDER: str = "local"       # openai|anthropic|google|deepseek|local
    TRANSLATE_MODEL: Optional[str] = None
    TRANSLATE_ENDPOINT: str = "http://localhost:1234/v1"   # for local provider
    TRANSLATE_TIMEOUT_S: int = 30
    TRANSLATE_MAX_RETRIES: int = 3

    # Embeddings — provider-based auth (API key resolved from env)
    EMBEDDINGS_ENABLE: bool = True
    EMBEDDINGS_PROVIDER: str = "local"      # openai|google|local
    EMBEDDINGS_MODEL: Optional[str] = None
    EMBEDDINGS_ENDPOINT: str = "http://localhost:1234/v1"  # for local provider
    EMBEDDINGS_TIMEOUT_S: int = 30
    EMBEDDINGS_MAX_RETRIES: int = 3

    EMBEDDINGS_FALLBACK_TO_SAMPLING: bool = True
    TOPIC_SAMPLING_MAX_COMMENTS_PER_VIDEO: int = 5000
    TOPIC_SAMPLING_MAX_TRANSCRIPT_CHUNKS_PER_VIDEO: int = 200
    TOPIC_SAMPLING_STRATEGY: str = "stratified_time"
    TOPIC_FALLBACK_PER_VIDEO_SUMMARY: bool = True
    TOPIC_FALLBACK_SUMMARY_MODE: str = "heuristic"

    # LLM — for topic extraction via LLM, triples, etc.
    LLM_PROVIDER: Optional[str] = None      # openai|anthropic|google|xai|deepseek|local
    LLM_MODEL: Optional[str] = None
    LLM_ENDPOINT: Optional[str] = None      # for local provider

    # YouTube Data API (rare fallback for discovery)
    YOUTUBE_API_KEY: Optional[str] = None

    # NLP toggles
    TM_CLUSTERING: str = "nlp"
    SA_GRANULARITY: list[str] = ["polarity"]
    STRIP_PII: bool = False

    # Summarization
    SUMMARY_ENABLE: bool = True
    SUMMARY_MAX_ITEMS: int = 200
    SUMMARY_MAX_RESPONSE_TOKENS: int = 1024

    # URL extraction
    URL_EXTRACTION_ENABLE: bool = True

    # Output structure
    OUTPUT_PER_VIDEO: bool = True       # True → per-video subdirs; False → flat

    # Reporting
    REPORT_VARIANTS: list[str] = ["all", "by-term", "by-vid"]
    RUN_DESC_4WORDS: str = "run_desc"

    # Pricing — USD per 1M tokens, for cost estimation in preflight / dry-run.
    # Follows config-ref.yml pattern: provider → model → {input, output}.
    # Use "_default" as fallback when a specific model isn't listed.
    PRICING_USD_PER_1M_TOKENS: dict[str, Any] = {
        "openai": {
            "gpt-5-mini":               {"input": 0.25, "output": 2.00},
            "gpt-4o-mini":              {"input": 0.15, "output": 0.60},
            "gpt-4o":                   {"input": 2.50, "output": 10.00},
            "text-embedding-3-small":   {"input": 0.02, "output": 0.0},
            "text-embedding-3-large":   {"input": 0.13, "output": 0.0},
            "_default":                 {"input": 1.25, "output": 10.00},
        },
        "anthropic": {
            "claude-haiku-4-5":   {"input": 1.00, "output": 5.00},
            "claude-sonnet-4-5":  {"input": 3.00, "output": 15.00},
            "_default":           {"input": 3.00, "output": 15.00},
        },
        "google": {
            "gemini-3-flash-preview":  {"input": 0.50, "output": 3.00},
            "gemini-3-pro-preview":    {"input": 2.00, "output": 12.00},
            "text-embedding-004":      {"input": 0.006, "output": 0.0},
            "_default":                {"input": 2.00, "output": 12.00},
        },
        "xai": {
            "grok-4-1-fast-non-reasoning":  {"input": 0.20, "output": 0.50},
            "_default":       {"input": 0.20, "output": 0.50},
        },
        "deepseek": {
            "deepseek-chat":  {"input": 0.14, "output": 0.28},
            "_default":       {"input": 0.14, "output": 0.28},
        },
        "fireworks": {
            "deepseek-v3p2":  {"input": 0.56, "output": 1.68},
            "_default":       {"input": 1.00, "output": 5.00},
        },
        "together": {
            "_default": {"input": 0.15, "output": 0.60},
        },
        "local": {
            "_default": {"input": 0.0, "output": 0.0},
        },
        "ollama": {
            "_default": {"input": 0.0, "output": 0.0},
        },
    }


def resolve_pricing(cfg: Settings, provider: str, model: str | None) -> dict[str, float]:
    """Look up per-token pricing for a provider/model pair. Returns {input, output}."""
    provider_prices = cfg.PRICING_USD_PER_1M_TOKENS.get(provider, {})
    if model and model in provider_prices:
        result: dict[str, float] = provider_prices[model]
        return result
    fallback: dict[str, float] = provider_prices.get("_default", {"input": 0.0, "output": 0.0})
    return fallback


def load_settings(config_path: str | Path | None) -> Settings:
    if config_path is None:
        return Settings()
    p = Path(config_path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Settings(**data)
