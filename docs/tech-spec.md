# yt-content-analyzer — Tech Spec (v0.2)
_Adds transcript download/extraction/analysis as a first-class asset type alongside comments._

## 1) Implementation ideas incorporated from the older design
From the older PRD, we incorporate:
- Click-based CLI + Rich progress integration (`utils/logger.py`, progress bars) fileciteturn1file0L21-L75
- Jinja2 templating for reports + a dedicated visualization module fileciteturn1file0L61-L67
- Explicit Knowledge Graph module scaffold (RDFLib/NetworkX/PyVis), kept optional/future fileciteturn1file0L53-L56
- A “clean modular file layout” and “plugin architecture” pattern for analyzers fileciteturn1file1L76-L83

---

## 2) Conventions

### 2.1 Global config naming
All configuration keys are **ALL_CAPS** (including CLI flag mappings).

### 2.2 Config precedence
Defaults → CONFIG_FILE → environment overrides (optional) → CLI overrides.  
Persist resolved config snapshot to `manifest.json`.

### 2.3 Resumability & idempotence
- Checkpoint per (VIDEO_ID, ASSET_TYPE, SORT_MODE?, STAGE).
- Every external request (translation/embeddings/LLM) is checkpointed and resumable from last completed call.

---

## 3) Hard caps & guardrails

### 3.1 Video caps (hard fail)
- `MAX_VIDEOS_PER_TERM=10`
- `MAX_TOTAL_VIDEOS=500`
If exceeded: abort before scraping with an informative error.

### 3.2 Request throttling and API hammer protections
Global knobs:
- `API_MAX_CONCURRENT_CALLS`
- `API_RATE_LIMIT_RPS`, `API_RATE_LIMIT_BURST`
- `API_COOLDOWN_ON_ERROR_S`
- `API_JITTER_MS_MIN`, `API_JITTER_MS_MAX`
- `API_TIMEOUT_S`, `API_MAX_RETRIES`

### 3.3 Comments safeguards
- `MAX_COMMENTS_PER_VIDEO` (default 200_000)
- `MAX_SCROLLS_WITHOUT_GROWTH` (preset-driven)
- If cap hit: mark `COMPLETED_WITH_CAP`.

### 3.4 Transcript safeguards
- `MAX_TRANSCRIPT_CHARS_PER_VIDEO` (default 2_000_000)
- If cap hit: mark `TRANSCRIPT_TRUNCATED=True`.

---

## 4) Configuration schema (ALL_CAPS)

### 4.1 Inputs
- `VIDEO_URL: str | None`
- `SEARCH_TERMS: list[str] | None`
- `MAX_VIDEOS_PER_TERM: int = 10`
- `MAX_TOTAL_VIDEOS: int = 500`

### 4.2 Discovery filters
- `VIDEO_LANG: list[str] = ['en']`
- `VIDEO_LANG_MAIN: str = 'en'`
- `VIDEO_REGION: list[str] = ['us']`
- `VIDEO_UPLOAD_DATE: str = 'last_year'`
- `MIN_VIEWS: int = 1000`
Optional defaults:
- `EXCLUDE_LIVE=True`, `INCLUDE_SHORTS=False`, `MAX_VIDEO_DURATION_S=None`
- `CHANNEL_ALLOWLIST=[]`, `CHANNEL_BLOCKLIST=[]`
- `KEYWORDS_INCLUDE=[]`, `KEYWORDS_EXCLUDE=[]`
- `MAX_RESULTS_PER_CHANNEL=None`

### 4.3 Collection controls
- `ROBUST_OVER_SPEED=True`
- `MAX_COMMENT_THREAD_DEPTH=5`
- `MAX_RETRY_SCRAPE=3`
- `COLLECT_SORT_MODES=['top','newest']`
- `CAPTURE_ARTIFACTS_ON_ERROR=True`
- `CAPTURE_ARTIFACTS_ALWAYS=False`

### 4.4 Transcripts (locked defaults)
- `TRANSCRIPTS_ENABLE=True`
- `TRANSCRIPTS_PREFER_MANUAL=True`
- `TRANSCRIPTS_ALLOW_AUTO=True`
- `TRANSCRIPTS_LANG_PREFERENCE=['en']`
- `TRANSCRIPTS_UI_FALLBACK=True`
- `TRANSCRIPTS_YTDLP_FALLBACK=True`
- `MAX_TRANSCRIPT_CHARS_PER_VIDEO=2_000_000`
- `TRANSCRIPT_CHUNK_MODE='time'`
- `TRANSCRIPT_CHUNK_SECONDS=60`
- `TRANSCRIPT_CHUNK_OVERLAP_SECONDS=10`

### 4.5 Translation (provider-based auth)
- `AUTO_TRANSLATE=False`
- `TRANSLATE_PROVIDER='local'`  # openai|anthropic|google|deepseek|local
- `TRANSLATE_MODEL=None`
- `TRANSLATE_ENDPOINT='http://localhost:1234/v1'`  # for local provider only
- `TRANSLATE_TIMEOUT_S=30`, `TRANSLATE_MAX_RETRIES=3`
If `AUTO_TRANSLATE=True`, translate **comments and transcripts** to `VIDEO_LANG_MAIN`.
API key is resolved at runtime from canonical env var (e.g. `OPENAI_API_KEY`) based on `TRANSLATE_PROVIDER`.

### 4.6 Embeddings (provider-based auth with fallback)
- `EMBEDDINGS_ENABLE=True`
- `EMBEDDINGS_PROVIDER='local'`  # openai|google|local
- `EMBEDDINGS_MODEL=None`
- `EMBEDDINGS_ENDPOINT='http://localhost:1234/v1'`  # for local provider only
- `EMBEDDINGS_TIMEOUT_S=30`, `EMBEDDINGS_MAX_RETRIES=3`
API key is resolved at runtime from canonical env var based on `EMBEDDINGS_PROVIDER`.
Fallback:
- `EMBEDDINGS_FALLBACK_TO_SAMPLING=True`
- `TOPIC_SAMPLING_MAX_COMMENTS_PER_VIDEO=5000`
- `TOPIC_SAMPLING_MAX_TRANSCRIPT_CHUNKS_PER_VIDEO=200`
- `TOPIC_SAMPLING_STRATEGY='stratified_time'`
- `TOPIC_FALLBACK_PER_VIDEO_SUMMARY=True`
- `TOPIC_FALLBACK_SUMMARY_MODE='heuristic'`

### 4.7 NLP toggles
- `TM_CLUSTERING='nlp'`  # nlp|llm
- `SA_GRANULARITY=['polarity']`  # polarity|emotions|absa
- `STRIP_PII=False`

### 4.8 Reporting
- `REPORT_VARIANTS=['all','by-term','by-vid']`
- `REPORTS_DIR='reports/'`
- `RUN_SEQ` (000–999), `RUN_DESC_4WORDS`
- Naming: `report_{RUN_SEQ:03d}_{RUN_DESC_4WORDS}_{VARIANT}.md`
- Preflight: `preflight_{RUN_ID}.md`

---

## 5) Architecture

### 5.1 Asset types
`ASSET_TYPE in {'comments','transcript'}`

### 5.2 Stages (checkpointed)
Checkpoint granularity: (VIDEO_ID, ASSET_TYPE, SORT_MODE?, STAGE)

Stages:
- `DISCOVERED`
- `COLLECTING_COMMENTS_TOP`, `COLLECTED_COMMENTS_TOP`
- `COLLECTING_COMMENTS_NEWEST`, `COLLECTED_COMMENTS_NEWEST`
- `COLLECTING_TRANSCRIPT`, `COLLECTED_TRANSCRIPT`
- `ENRICH_TRANSLATED`, `ENRICH_TOPICS`, `ENRICH_SENTIMENT`, `ENRICH_TRIPLES`
- `REPORTED`

### 5.3 Repo layout (revised)
```
yt_content_analyzer/
  __init__.py
  cli.py
  config.py
  run.py

  preflight/
    checks.py
    report.py

  state/
    checkpoint.py

  discovery/
    resolver.py
    filters.py

  collectors/
    base.py

    comments_playwright_ui.py
    comments_ytdlp.py
    comments_api_v3.py  # optional

    transcript_base.py
    transcript_extractor.py   # wrapper for transcript libraries (no key)
    transcript_ytdlp.py
    transcript_playwright_ui.py

  parse/
    normalize_comments.py
    normalize_transcripts.py
    chunk_transcripts.py
    pii.py
    translate.py

  enrich/
    embeddings_client.py
    topics_nlp.py
    topics_llm.py
    sentiment.py
    triples.py

  knowledge_graph/            # optional/future
    build.py
    visualize.py

  reporting/
    generator.py
    templates/
      report_all.md.j2
      report_by_term.md.j2
      report_by_vid.md.j2
    visualizations.py

  utils/
    logger.py
    io.py

tests/
docs/
```
---

## 6) Transcript collection

Provider order (unless disabled):
1. `TRANSCRIPT_EXTRACTOR_PROVIDER` (manual preferred; allow auto)  
2. `YTDLP_SUBTITLES_PROVIDER`  
3. `PLAYWRIGHT_UI_PROVIDER`  

Normalize to:
- `transcripts/transcript_segments.(jsonl|csv)`
- `transcripts/transcript_chunks.(jsonl|csv)`
- `transcripts/transcript_status.(jsonl|csv)`

---

## 7) Reporting
Use Jinja2 templates for MD reports and a visualization module for charts/assets. fileciteturn1file1L27-L39

---

## 8) Preflight
Multi-level preflight produces `reports/preflight_<RUN_ID>.md` and prints summary to terminal. Blocks execution on critical misconfig (strict by default).

