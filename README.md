# yt-content-analyzer

Scrape-first YouTube **comments + transcripts** collection and analysis for moderate academic research scale.

Given a YouTube URL, a set of search terms, or a list of channel subscriptions, `yt-content-analyzer` discovers videos, collects comments (Top and Newest sort orders) and transcripts (manual captions preferred, auto-generated as fallback), enriches the text through configurable NLP/LLM pipelines, and produces structured JSONL datasets alongside human-readable Markdown reports.

> **Note:** This tool is intended for research-scale analysis (up to 500 videos total), not massive dataset harvesting.

## Current status

| Feature | Status |
|---------|--------|
| Single-video pipeline (URL) | Functional end-to-end |
| Subscription mode (channels) | Functional end-to-end |
| Search-term discovery | Scaffolded |
| Comment collection (Playwright + yt-dlp fallback) | Functional |
| Transcript collection (yt-dlp) | Functional |
| Enrichment (topics, sentiment, triples) | Functional |
| Checkpointing and resume | Functional |
| Markdown reports | Scaffolded |
| Knowledge graph | Scaffolded |

## Requirements

- Python 3.10+
- [Playwright](https://playwright.dev/python/) browsers (installed via `playwright install`)
- Optional: a local embeddings/translation endpoint (e.g., LM Studio at `localhost:1234`)

## Installation

### From PyPI (once published)

```bash
pip install yt-content-analyzer[scrape,reports,nlp]
playwright install
```

### From source

```bash
git clone https://github.com/<org>/yt-content-analyzer
cd yt-content-analyzer
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,scrape,reports,nlp]"
playwright install
```

Optional dependency groups:

| Group     | What it adds                               |
|-----------|--------------------------------------------|
| `scrape`  | Playwright, yt-dlp (browser + CLI scraping)|
| `nlp`     | NumPy, pandas, scikit-learn, TextBlob      |
| `reports` | Jinja2 (Markdown report generation)        |
| `kg`      | rdflib, NetworkX, PyVis (knowledge graphs) |
| `dev`     | pytest, ruff, mypy, build, twine           |

## Setup

### 1. Configuration file

Copy and edit the example config:

```bash
cp config.example.yml config.yml
```

The config file uses **ALL_CAPS** keys organized into sections:

| Section              | Key settings                                                                         |
|----------------------|--------------------------------------------------------------------------------------|
| **Inputs**           | `VIDEO_URL`, `SEARCH_TERMS`, or `YT_SUBSCRIPTIONS` (mutually exclusive)              |
| **Subscriptions**    | `YT_SUBSCRIPTIONS` (list of channels), `MAX_SUB_VIDEOS` (per-channel default)        |
| **Discovery filters**| `VIDEO_LANG`, `VIDEO_REGION`, `VIDEO_UPLOAD_DATE`, `MIN_VIEWS`                       |
| **Collection**       | `COLLECT_SORT_MODES`, `MAX_COMMENTS_PER_VIDEO`, `MAX_COMMENT_THREAD_DEPTH`           |
| **Transcripts**      | `TRANSCRIPTS_ENABLE`, `TRANSCRIPTS_PREFER_MANUAL`, `TRANSCRIPT_CHUNK_*`              |
| **Rate limiting**    | `API_RATE_LIMIT_RPS`, `API_MAX_CONCURRENT_CALLS`, `API_JITTER_MS_*`                  |
| **Translation**      | `AUTO_TRANSLATE`, `TRANSLATE_PROVIDER`, `TRANSLATE_MODEL`                             |
| **Embeddings**       | `EMBEDDINGS_ENABLE`, `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_MODEL`                       |
| **NLP**              | `TM_CLUSTERING` (nlp or llm), `SA_GRANULARITY`, `STRIP_PII`                         |
| **Error handling**   | `ON_VIDEO_FAILURE` (`skip` or `abort`), `MAX_RETRY_SCRAPE`                           |
| **Reporting**        | `REPORT_VARIANTS`, `RUN_DESC_4WORDS`                                                 |

See `config.example.yml` for all available keys with defaults.

**Important constraints:**
- `VIDEO_URL`, `SEARCH_TERMS`, and `YT_SUBSCRIPTIONS` are mutually exclusive. Provide exactly one.
- `MAX_VIDEOS_PER_TERM` must be <= 10; `MAX_TOTAL_VIDEOS` must be <= 500.
- Subscription mode: total videos across all channels must not exceed `MAX_TOTAL_VIDEOS`.

### 2. Secrets (environment variables)

```bash
cp .env.example .env
# Edit .env with your values
```

Use canonical API key names. The code resolves the correct key at runtime based on the `TRANSLATE_PROVIDER` / `EMBEDDINGS_PROVIDER` / `LLM_PROVIDER` setting in your config:

| Variable              | Purpose                                        |
|-----------------------|------------------------------------------------|
| `OPENAI_API_KEY`      | OpenAI (translation, embeddings, LLM)          |
| `ANTHROPIC_API_KEY`   | Anthropic (translation, LLM)                   |
| `GOOGLE_API_KEY`      | Google (translation, embeddings, LLM)          |
| `XAI_API_KEY`         | xAI / Grok (LLM)                              |
| `DEEPSEEK_API_KEY`    | DeepSeek (translation, LLM)                    |
| `FIREWORKS_API_KEY`   | Fireworks hosted inference                     |
| `TOGETHER_API_KEY`    | Together hosted inference                      |
| `YOUTUBE_API_KEY`     | YouTube Data API (rare fallback for discovery) |

**Do not commit `.env` to version control.** It is gitignored by default.

### 3. Validate your setup

Run preflight checks before starting a long collection job:

```bash
ytca preflight --config config.yml
```

Preflight validates config invariants (including input mutual exclusivity and subscription video caps), checks local environment readiness, probes remote endpoints, and verifies transcript provider availability. Results are printed to the terminal and saved as a Markdown report.

## Usage

### Input modes

`yt-content-analyzer` supports three mutually exclusive input modes:

#### 1. Single video URL

Set `VIDEO_URL` in your config or pass it on the command line:

```bash
ytca run-all --config config.yml --video-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

#### 2. Channel subscriptions

Define channels in your config file and use the `--subscriptions` flag:

```yaml
# config.yml
YT_SUBSCRIPTIONS:
  - CHANNEL: "@engineerprompt"
    MAX_SUB_VIDEOS: 3
  - CHANNEL: "@firaborova"
    MAX_SUB_VIDEOS: 5
MAX_SUB_VIDEOS: 3   # global default when not specified per channel
```

```bash
ytca run-all --config config.yml --subscriptions
```

The subscription resolver uses yt-dlp to fetch the latest N videos from each channel's `/videos` page. Discovered videos are written to `discovery/discovered_videos.jsonl` in the run directory. Channel handles (`@handle`), channel IDs (`UC...`), and full URLs are all accepted.

#### 3. Search terms

```bash
ytca run-all --config config.yml --terms "AI agents 2026" --terms "robotics policy"
```

The `--terms` flag overrides `SEARCH_TERMS` in the config file. Pass multiple `--terms` for multi-topic collection. *(Search-term discovery is scaffolded but not yet implemented.)*

### Resuming an interrupted run

Runs are checkpointed automatically. If a run is interrupted, resume it by RUN_ID:

```bash
ytca run-all --resume 20260208T235833Z
```

Resume mode reloads config from the run's `manifest.json` and skips preflight. You can optionally pass `--config` to override settings:

```bash
ytca run-all --resume 20260208T235833Z --config updated_config.yml
```

### CLI reference

**Global options:**

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Increase verbosity (repeat for DEBUG) |
| `-q`, `--quiet` | Suppress all but warnings |

**`ytca run-all` options:**

| Flag | Description |
|------|-------------|
| `--config` | Path to YAML config file (required for new runs) |
| `--video-url` | Single YouTube video URL (overrides config) |
| `--terms` | Search terms (repeatable, overrides config) |
| `--subscriptions` | Run in subscription mode using `YT_SUBSCRIPTIONS` from config |
| `--output-dir` | Base directory for run outputs (default: `./runs`) |
| `--resume` | Resume a previous run by RUN_ID |
| `--sort-modes` | Comma-separated sort modes, e.g. `top,newest` |
| `--max-comments` | Override `MAX_COMMENTS_PER_VIDEO` |
| `--no-transcripts` | Disable transcript collection |
| `--llm-provider` | Override `LLM_PROVIDER` |
| `--llm-model` | Override `LLM_MODEL` |
| `--on-failure` | Override `ON_VIDEO_FAILURE` (`skip` or `abort`) |

### Error handling

By default, `ON_VIDEO_FAILURE` is set to `skip`: if a collection or enrichment stage fails for a video, the error is logged to `failures/`, the checkpoint is marked `FAILED`, and the pipeline continues to the next stage or video. Set `ON_VIDEO_FAILURE: "abort"` to halt on the first error instead.

Collection stages (Playwright and yt-dlp calls) use a fallback chain and retry automatically with exponential backoff up to `MAX_RETRY_SCRAPE` times. Enrichment stages (embeddings, topics, sentiment, triples) each run independently -- a failure in one does not block the others.

## Pipeline overview

```
Input (URL / Subscriptions / Search terms)
  --> Preflight (config validation, endpoint probes)
    --> Discovery (resolve channels via yt-dlp, or scrape YouTube search)
      --> For each video:
            Collection
              Comments: Playwright UI --> yt-dlp fallback
              Transcripts: yt-dlp subtitles (manual preferred, auto fallback)
            Parse (normalize, chunk transcripts by time windows)
            Enrich (embeddings, topic modeling, sentiment, triples)
      --> Report (Jinja2 Markdown templates)
```

Each stage is checkpointed per `(VIDEO_ID, STAGE)` so interrupted runs resume without re-collecting already-completed work. Failed stages are recorded with full tracebacks in `failures/` and marked in the checkpoint so they can be retried on resume.

## Output structure

Each run produces a self-contained directory under `runs/`. Every output is append-safe JSONL or standalone JSON, so a crashed run leaves valid partial data that a resume can build on.

```
runs/<RUN_ID>/
  manifest.json                  # Resolved config snapshot (JSON, for reproducibility)
  logs/
    run.log                      # Full execution log (JSON-lines, one object per entry)
  discovery/
    discovered_videos.jsonl      # Videos resolved from subscriptions (subscription mode only)
  transcripts/
    transcript_segments.jsonl    # Raw normalized segments (one per caption line)
    transcript_chunks.jsonl      # Time-windowed chunks (60s window, 10s overlap)
  comments/
    comments_top.jsonl           # Per-sort-mode raw comments
    comments_newest.jsonl
    comments.jsonl               # Deduplicated merged comments (flat, with reply threading)
  enrich/
    topics.jsonl                 # Topic clusters per asset type (NLP or LLM)
    sentiment.jsonl              # Per-item polarity + score
    triples.jsonl                # Subject-predicate-object triples (LLM only)
  failures/                      # Per-stage failure records (JSON, created on error)
    <stage>_<video_id>.json      #   e.g. comments_abc123.json
  reports/
    preflight_<RUN_ID>.md        # Preflight diagnostics
    preflight_<RUN_ID>.json      # Machine-readable preflight results
  state/
    checkpoint.json              # Resume state (per-video, per-stage)
```

**Format conventions:**

- **JSONL** (`.jsonl`) for all multi-record datasets. One JSON object per line, append-mode safe. Load with pandas: `pd.read_json("file.jsonl", lines=True)`.
- **JSON** (`.json`) for single-document records: manifest, checkpoint, failure records, preflight results.
- **Markdown** (`.md`) for human-readable reports.
- **JSON-lines logging** (`run.log`): each line is a JSON object with `timestamp`, `level`, `message`, `module`, `extra`, and optional `traceback`.

### File format reference

| File | Format | Schema |
|------|--------|--------|
| `discovered_videos.jsonl` | JSONL | `VIDEO_URL`, `VIDEO_ID`, `TITLE` |
| `transcript_segments.jsonl` | JSONL | `VIDEO_ID`, `SEGMENT_INDEX`, `START_S`, `END_S`, `TEXT`, `SPEAKER`, `SOURCE`, `LANG` |
| `transcript_chunks.jsonl` | JSONL | `VIDEO_ID`, `CHUNK_INDEX`, `START_S`, `END_S`, `TEXT`, `SEGMENT_INDICES`, `OVERLAP_S` |
| `comments.jsonl` | JSONL | `VIDEO_ID`, `COMMENT_ID`, `PARENT_ID`, `AUTHOR`, `TEXT`, `LIKE_COUNT`, `REPLY_COUNT`, `PUBLISHED_AT`, `SORT_MODE`, `THREAD_DEPTH` |
| `topics.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `TOPIC_ID`, `LABEL`, `KEYWORDS`, `REPRESENTATIVE_TEXTS`, `SCORE` |
| `sentiment.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `ITEM_ID`, `POLARITY`, `SCORE`, `TEXT_EXCERPT` |
| `triples.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `SUBJECT`, `PREDICATE`, `OBJECT`, `CONFIDENCE`, `SOURCE_TEXT` |
| `failures/*.json` | JSON | `stage`, `video_id`, `error_type`, `error_message`, `traceback`, `timestamp` |
| `checkpoint.json` | JSON | `UNITS: { <video_id>: { <stage>: "DONE"\|"FAILED" } }` |

### Working with the data

```python
import pandas as pd

# Load comments
comments = pd.read_json("runs/<RUN_ID>/comments/comments.jsonl", lines=True)

# Load transcript chunks
chunks = pd.read_json("runs/<RUN_ID>/transcripts/transcript_chunks.jsonl", lines=True)

# Load enrichment results
topics = pd.read_json("runs/<RUN_ID>/enrich/topics.jsonl", lines=True)
sentiment = pd.read_json("runs/<RUN_ID>/enrich/sentiment.jsonl", lines=True)
```

## Python API

The package exports a public API for use from scripts and notebooks:

```python
from yt_content_analyzer import (
    run_all, run_preflight, extract_video_id,
    Settings, load_settings, resolve_api_key, resolve_pricing,
    RunResult, PreflightResult, CheckpointStore,
    YTCAError, PreflightError, ConfigError, CollectionError, EnrichmentError,
)

# Single video
cfg = load_settings("config.yml")
cfg.VIDEO_URL = "https://www.youtube.com/watch?v=abc12345678"
result = run_all(cfg, output_dir="/tmp/analysis")

# Subscription mode
cfg = load_settings("config.yml")
cfg.YT_SUBSCRIPTIONS = [{"CHANNEL": "@engineerprompt", "MAX_SUB_VIDEOS": 3}]
cfg.VIDEO_URL = None
result = run_all(cfg, output_dir="/tmp/sub-analysis")

print(f"Processed {result.videos_processed} videos, {result.comments_collected} comments")
```

**Exception hierarchy:**

```
YTCAError (base)
  +-- ConfigError        # invalid or inconsistent configuration
  +-- PreflightError     # preflight checks failed (carries .results list)
  +-- CollectionError    # comment/transcript collection failure
  +-- EnrichmentError    # enrichment pipeline failure
```

## Development

```bash
# Run the full test suite
pytest

# Lint
ruff check src/ tests/

# Auto-fix lint
ruff check --fix src/ tests/

# Type check
mypy src/

# Build distribution
python -m build
twine check dist/*
```

### Test suites

| Test file | Scope |
|-----------|-------|
| `test_smoke.py` | Basic import verification |
| `test_priority1.py` | Error handling, logging, checkpoints, CLI resume |
| `test_collection.py` | Collection pipeline integration |
| `test_comments_playwright.py` | Playwright comment collector (heavily mocked) |
| `test_enrichment.py` | Enrichment pipeline (topics, sentiment, triples) |
| `test_subscriptions.py` | Subscription mode: config parsing, channel resolver, preflight, CLI |
| `test_api_connectivity.py` | Live API probes (skipped if keys missing) |

## License

MIT. See [LICENSE](LICENSE).
