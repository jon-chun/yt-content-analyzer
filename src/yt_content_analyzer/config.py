from __future__ import annotations
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path
from typing import Any, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="allow")

    # Inputs
    VIDEO_URL: Optional[str] = None
    SEARCH_TERMS: Optional[list[str]] = None
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
    ROBUST_OVER_SPEED: bool = True
    MAX_COMMENT_THREAD_DEPTH: int = 5
    MAX_RETRY_SCRAPE: int = 3
    COLLECT_SORT_MODES: list[str] = ["top","newest"]
    MAX_COMMENTS_PER_VIDEO: int = 200_000
    CAPTURE_ARTIFACTS_ON_ERROR: bool = True
    CAPTURE_ARTIFACTS_ALWAYS: bool = False

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

    # Rate limiting
    API_MAX_CONCURRENT_CALLS: int = 2
    API_RATE_LIMIT_RPS: float = 2.0
    API_RATE_LIMIT_BURST: int = 4
    API_COOLDOWN_ON_ERROR_S: int = 10
    API_JITTER_MS_MIN: int = 250
    API_JITTER_MS_MAX: int = 900
    API_TIMEOUT_S: int = 30
    API_MAX_RETRIES: int = 3

    # Translation
    AUTO_TRANSLATE: bool = False
    AUTO_TRANSLATE_LOCAL: bool = False
    TRANSLATE_REMOTE_ENDPOINT: Optional[str] = None
    TRANSLATE_REMOTE_AUTH_TYPE: str = "none"
    TRANSLATE_REMOTE_AUTH_VALUE: Optional[str] = None
    TRANSLATE_REMOTE_MODEL: Optional[str] = None
    TRANSLATE_LOCAL_ENDPOINT: str = "http://localhost:1234/v1"
    TRANSLATE_LOCAL_MODEL: Optional[str] = None
    TRANSLATE_TIMEOUT_S: int = 30
    TRANSLATE_MAX_RETRIES: int = 3

    # Embeddings
    EMBEDDINGS_ENABLE: bool = True
    EMBEDDINGS_LOCAL: bool = True
    EMBEDDINGS_REMOTE: bool = False
    EMBEDDINGS_LOCAL_ENDPOINT: str = "http://localhost:1234/v1"
    EMBEDDINGS_LOCAL_MODEL: Optional[str] = None
    EMBEDDINGS_REMOTE_ENDPOINT: Optional[str] = None
    EMBEDDINGS_REMOTE_MODEL: Optional[str] = None
    EMBEDDINGS_REMOTE_AUTH_TYPE: str = "none"
    EMBEDDINGS_REMOTE_AUTH_VALUE: Optional[str] = None
    EMBEDDINGS_TIMEOUT_S: int = 30
    EMBEDDINGS_MAX_RETRIES: int = 3

    EMBEDDINGS_FALLBACK_TO_SAMPLING: bool = True
    TOPIC_SAMPLING_MAX_COMMENTS_PER_VIDEO: int = 5000
    TOPIC_SAMPLING_MAX_TRANSCRIPT_CHUNKS_PER_VIDEO: int = 200
    TOPIC_SAMPLING_STRATEGY: str = "stratified_time"
    TOPIC_FALLBACK_PER_VIDEO_SUMMARY: bool = True
    TOPIC_FALLBACK_SUMMARY_MODE: str = "heuristic"

    # NLP toggles
    TM_CLUSTERING: str = "nlp"
    SA_GRANULARITY: list[str] = ["polarity"]
    STRIP_PII: bool = False

    # Reporting
    REPORT_VARIANTS: list[str] = ["all","by-term","by-vid"]
    RUN_DESC_4WORDS: str = "run_desc"

def load_settings(config_path: str | Path | None) -> Settings:
    if config_path is None:
        return Settings()
    p = Path(config_path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Settings(**data)
