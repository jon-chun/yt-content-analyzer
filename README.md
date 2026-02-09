<p align="center">
  <img src="docs/logo.svg" alt="TubeSift" width="480"/>
</p>

<p align="center">
  <strong>Research-scale YouTube content analysis &mdash; from collection to insight.</strong>
</p>

<p align="center">
  <code>pip install yt-content-analyzer[scrape,nlp]</code>
</p>

---

TubeSift (`yt-content-analyzer`) discovers YouTube videos by URL, channel, or search term, collects their comments and transcripts, and enriches the text through configurable NLP and LLM pipelines. It produces structured JSONL datasets ready for pandas, notebooks, or downstream analysis.

Built for academic researchers working at moderate scale (10--500 videos), not massive dataset harvesting.

## Status

| Capability | Status |
|------------|--------|
| Single-video pipeline (URL or bare video ID) | Functional |
| Channel subscription mode | Functional |
| Search-term discovery | Functional |
| Comment collection (Playwright + yt-dlp fallback) | Functional |
| Transcript collection (yt-dlp, manual + auto) | Functional |
| Enrichment (topics, sentiment, triples, summaries, URLs) | Functional |
| Checkpointing and resume | Functional |
| Per-video output directories | Functional |
| Markdown reports | Scaffolded |
| Knowledge graph (RDF + NetworkX) | Scaffolded |

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/jon-chun/yt-content-analyzer && cd yt-content-analyzer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,scrape,reports,nlp]"
playwright install

# 2. Create your config
cp config.example.yml config.yml          # edit as needed

# 3. Set API keys (optional, for LLM-based enrichment)
cp .env.example .env                      # add your keys

# 4. Validate
ytca preflight --config config.yml

# 5. Run
ytca run-all --config config.yml --video-url "dQw4w9WgXcQ"
```

Your results appear in `runs/<RUN_ID>/videos/<VIDEO_ID>/` with comments, transcripts, and enrichment data as JSONL files.

---

## Table of contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Single video](#1-single-video)
  - [Channel subscriptions](#2-channel-subscriptions)
  - [Search terms](#3-search-terms)
  - [Resuming a run](#resuming-an-interrupted-run)
- [CLI reference](#cli-reference)
- [Output structure](#output-structure)
- [Working with the data](#working-with-the-data)
- [Python API](#python-api)
- [Architecture](#architecture)
- [Development](#development)
- [License](#license)

---

## Installation

### Requirements

- Python 3.10+
- [Playwright](https://playwright.dev/python/) browsers for comment scraping
- Optional: API keys for LLM-based enrichment (OpenAI, Anthropic, xAI, etc.)

### From source (recommended)

```bash
git clone https://github.com/jon-chun/yt-content-analyzer
cd yt-content-analyzer
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,scrape,reports,nlp]"
playwright install
```

### From PyPI (once published)

```bash
pip install yt-content-analyzer[scrape,reports,nlp]
playwright install
```

### Dependency groups

Install only what you need:

| Group     | Adds                                      | Required for                         |
|-----------|-------------------------------------------|--------------------------------------|
| `scrape`  | Playwright, yt-dlp                        | Comment + transcript collection      |
| `nlp`     | NumPy, pandas, scikit-learn, TextBlob     | Topic modeling, sentiment analysis   |
| `reports` | Jinja2                                    | Markdown report generation           |
| `kg`      | rdflib, NetworkX, PyVis                   | Knowledge graph construction         |
| `dev`     | pytest, ruff, mypy, build, twine          | Development and testing              |

```bash
# Minimal (collection only, no NLP)
pip install -e ".[scrape]"

# Full research stack
pip install -e ".[scrape,nlp,reports,kg]"

# Everything including dev tools
pip install -e ".[dev,scrape,reports,nlp,kg]"
```

---

## Configuration

### Step 1: Create your config file

```bash
cp config.example.yml config.yml
```

All config keys use **ALL_CAPS**. The file is organized into sections:

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
| **LLM**              | `LLM_PROVIDER`, `LLM_MODEL` (for topic extraction, triples, summarization)           |
| **NLP**              | `TM_CLUSTERING` (`nlp` or `llm`), `SA_GRANULARITY`, `STRIP_PII`                     |
| **Summarization**    | `SUMMARY_ENABLE`, `SUMMARY_MAX_ITEMS`, `SUMMARY_MAX_RESPONSE_TOKENS`                 |
| **URL extraction**   | `URL_EXTRACTION_ENABLE`                                                               |
| **Output structure** | `OUTPUT_PER_VIDEO` (`true` = per-video subdirs, `false` = flat)                       |
| **Error handling**   | `ON_VIDEO_FAILURE` (`skip` or `abort`), `MAX_RETRY_SCRAPE`                           |
| **Reporting**        | `REPORT_VARIANTS`, `RUN_DESC_4WORDS`                                                 |

See [`config.example.yml`](config.example.yml) for all available keys with defaults and inline documentation.

**Constraints:**

- `VIDEO_URL`, `SEARCH_TERMS`, and `YT_SUBSCRIPTIONS` are mutually exclusive. Provide exactly one.
- `MAX_VIDEOS_PER_TERM` must be &le; 10; `MAX_TOTAL_VIDEOS` must be &le; 500.
- In subscription mode, total videos across all channels must not exceed `MAX_TOTAL_VIDEOS`.

### Step 2: Set API keys

```bash
cp .env.example .env
# Edit .env with your keys
```

The code resolves the correct API key at runtime from standard environment variables based on the provider you configure:

| Variable              | Used by                                        |
|-----------------------|------------------------------------------------|
| `OPENAI_API_KEY`      | Translation, embeddings, LLM enrichment        |
| `ANTHROPIC_API_KEY`   | Translation, LLM enrichment                    |
| `GOOGLE_API_KEY`      | Translation, embeddings, LLM enrichment        |
| `XAI_API_KEY`         | LLM enrichment (Grok)                          |
| `DEEPSEEK_API_KEY`    | Translation, LLM enrichment                    |
| `FIREWORKS_API_KEY`   | Hosted inference                               |
| `TOGETHER_API_KEY`    | Hosted inference                               |
| `YOUTUBE_API_KEY`     | YouTube Data API (rare fallback)               |

> **Do not commit `.env` to version control.** It is gitignored by default.

API keys are optional. Without them, TubeSift still collects comments and transcripts and runs NLP-based enrichment (topic modeling via TF-IDF/clustering, sentiment via TextBlob). LLM-based features (summarization, relation triples, LLM topic extraction) require a configured provider.

### Step 3: Validate your setup

```bash
ytca preflight --config config.yml
```

Preflight validates config invariants (input mutual exclusivity, subscription caps), checks environment readiness, probes remote endpoints, and verifies transcript provider availability. Results are printed to the terminal and saved as a report in the run directory.

---

## Usage

TubeSift supports three mutually exclusive input modes. Choose one per run.

### 1. Single video

Pass a full YouTube URL or a bare 11-character video ID:

```bash
# Full URL
ytca run-all --config config.yml --video-url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Bare video ID (auto-expanded to full URL)
ytca run-all --config config.yml --video-url "dQw4w9WgXcQ"
```

Or set `VIDEO_URL` in your config file and omit the flag.

### 2. Channel subscriptions

Analyze the latest videos from one or more YouTube channels.

**Quick way** -- use the `--channel` CLI flag (repeatable):

```bash
ytca run-all --config config.yml --channel "@engineerprompt" --channel "@firaborova"
```

**Config way** -- define channels in YAML and use `--subscriptions`:

```yaml
# config.yml
YT_SUBSCRIPTIONS:
  - CHANNEL: "@engineerprompt"
    MAX_SUB_VIDEOS: 3               # fetch latest 3 from this channel
  - CHANNEL: "@firaborova"
    MAX_SUB_VIDEOS: 5
  - CHANNEL: "UCxxxxxxxxxxxxxxxxxxxxxx"   # channel IDs also work
MAX_SUB_VIDEOS: 3                   # global default per channel
```

```bash
ytca run-all --config config.yml --subscriptions
```

The resolver uses yt-dlp to fetch the latest N videos from each channel. Discovered videos are logged to `discovery/discovered_videos.jsonl`. Channel handles (`@handle`), channel IDs (`UC...`), and full URLs are all accepted.

### 3. Search terms

Discover videos by keyword search:

```bash
# Single term
ytca run-all --config config.yml --terms "Claude AI tutorial"

# Multiple terms (repeatable)
ytca run-all --config config.yml --terms "AI agents 2026" --terms "robotics policy"
```

Or set `SEARCH_TERMS` in your config:

```yaml
SEARCH_TERMS: ["AI agents 2026", "robotics policy"]
```

The search resolver uses yt-dlp's `ytsearch` to find matching videos. Results are deduplicated by video ID and capped at `MAX_TOTAL_VIDEOS`.

### Common options

These flags work with any input mode:

```bash
# Limit to top-sorted comments only, max 100
ytca run-all --config config.yml --video-url "VIDEO_ID" \
  --sort-modes top --max-comments 100

# Skip transcripts
ytca run-all --config config.yml --video-url "VIDEO_ID" --no-transcripts

# Use a specific LLM for enrichment
ytca run-all --config config.yml --video-url "VIDEO_ID" \
  --llm-provider xai --llm-model grok-4-1-fast-non-reasoning

# Halt on first error instead of skipping
ytca run-all --config config.yml --video-url "VIDEO_ID" --on-failure abort
```

### Resuming an interrupted run

Runs are checkpointed automatically per `(VIDEO_ID, STAGE)`. Resume by RUN_ID:

```bash
ytca run-all --resume 20260208T235833Z
```

Resume reloads config from the run's `manifest.json` and skips preflight. Already-completed stages are not re-run. You can optionally override settings:

```bash
ytca run-all --resume 20260208T235833Z --config updated_config.yml
```

### Error handling

`ON_VIDEO_FAILURE` controls behavior when a stage fails:

| Mode | Behavior |
|------|----------|
| `skip` (default) | Log error to `failures/`, mark checkpoint `FAILED`, continue to next stage/video |
| `abort` | Halt the entire pipeline on the first error |

Collection uses a fallback chain (Playwright &rarr; yt-dlp) with exponential backoff retries. Enrichment stages run independently -- a failure in one does not block the others.

---

## CLI reference

### Global options

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Increase verbosity (repeat for DEBUG) |
| `-q`, `--quiet` | Suppress all but warnings |

### `ytca preflight`

| Flag | Description |
|------|-------------|
| `--config` | Path to YAML config file (required) |
| `--output-dir` | Output directory for preflight report |

### `ytca run-all`

| Flag | Description |
|------|-------------|
| `--config` | Path to YAML config file (required for new runs) |
| `--video-url` | YouTube URL or bare 11-char video ID (overrides config) |
| `--terms` | Search term (repeatable, overrides config) |
| `--channel` | Channel handle or URL (repeatable, shortcut for subscription mode) |
| `--subscriptions` | Use `YT_SUBSCRIPTIONS` from config |
| `--output-dir` | Base directory for run outputs (default: `./runs`) |
| `--resume` | Resume a previous run by RUN_ID |
| `--sort-modes` | Comma-separated comment sort modes, e.g. `top,newest` |
| `--max-comments` | Override `MAX_COMMENTS_PER_VIDEO` |
| `--no-transcripts` | Disable transcript collection |
| `--llm-provider` | Override `LLM_PROVIDER` |
| `--llm-model` | Override `LLM_MODEL` |
| `--on-failure` | Override `ON_VIDEO_FAILURE` (`skip` or `abort`) |

---

## Output structure

Each run produces a self-contained directory. All outputs are append-safe JSONL or standalone JSON, so a crashed run leaves valid partial data that a resume can build on.

### Per-video layout (default)

When `OUTPUT_PER_VIDEO: true` (the default), each video's data lives in its own subdirectory:

```
runs/<RUN_ID>/
  manifest.json                    # resolved config snapshot
  state/
    checkpoint.json                # resume state (per-video, per-stage)
  logs/
    run.log                        # JSON-lines execution log
  discovery/
    discovered_videos.jsonl        # videos found via channel/search discovery
  videos/
    <VIDEO_ID>/
      comments/
        comments_top.jsonl         # per-sort-mode raw comments
        comments_newest.jsonl
        comments.jsonl             # deduplicated merged comments
      transcripts/
        transcript_segments.jsonl  # normalized caption segments
        transcript_chunks.jsonl    # time-windowed chunks (60s, 10s overlap)
      enrich/
        topics.jsonl               # topic clusters (NLP or LLM)
        sentiment.jsonl            # per-item polarity + score
        triples.jsonl              # subject-predicate-object (LLM)
        urls.jsonl                 # aggregated URLs with mention counts
        summary.jsonl              # content summaries (LLM)
      failures/
        <stage>_<video_id>.json    # error records (created on failure)
  reports/
    preflight_<RUN_ID>.md
    preflight_<RUN_ID>.json
```

### Flat layout

Set `OUTPUT_PER_VIDEO: false` to use a flat structure (all videos share the same directories):

```
runs/<RUN_ID>/
  manifest.json
  state/checkpoint.json
  logs/run.log
  discovery/discovered_videos.jsonl
  comments/                        # all videos mixed
  transcripts/
  enrich/
  failures/
  reports/
```

### File format reference

| File | Format | Key fields |
|------|--------|------------|
| `discovered_videos.jsonl` | JSONL | `VIDEO_URL`, `VIDEO_ID`, `TITLE`, `SEARCH_TERM` |
| `transcript_segments.jsonl` | JSONL | `VIDEO_ID`, `SEGMENT_INDEX`, `START_S`, `END_S`, `TEXT`, `SPEAKER`, `SOURCE`, `LANG` |
| `transcript_chunks.jsonl` | JSONL | `VIDEO_ID`, `CHUNK_INDEX`, `START_S`, `END_S`, `TEXT`, `SEGMENT_INDICES`, `OVERLAP_S` |
| `comments.jsonl` | JSONL | `VIDEO_ID`, `COMMENT_ID`, `PARENT_ID`, `AUTHOR`, `TEXT`, `LIKE_COUNT`, `REPLY_COUNT`, `PUBLISHED_AT`, `SORT_MODE`, `THREAD_DEPTH` |
| `topics.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `TOPIC_ID`, `LABEL`, `KEYWORDS`, `REPRESENTATIVE_TEXTS`, `SCORE` |
| `sentiment.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `ITEM_ID`, `POLARITY`, `SCORE`, `TEXT_EXCERPT` |
| `triples.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `SUBJECT`, `PREDICATE`, `OBJECT`, `CONFIDENCE`, `SOURCE_TEXT` |
| `urls.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `URL`, `DOMAIN`, `MENTION_COUNT`, `FIRST_SEEN_ITEM_ID` |
| `summary.jsonl` | JSONL | `VIDEO_ID`, `ASSET_TYPE`, `SUMMARY`, `KEY_THEMES`, `TONE`, `ITEM_COUNT`, `ITEM_COUNT_ANALYZED` |
| `failures/*.json` | JSON | `stage`, `video_id`, `error_type`, `error_message`, `traceback`, `timestamp` |
| `checkpoint.json` | JSON | `UNITS: { <video_id>: { <stage>: "DONE" \| "FAILED" } }` |

**Format conventions:**

- **JSONL** (`.jsonl`): one JSON object per line, append-mode safe.
- **JSON** (`.json`): single-document records (manifest, checkpoint, failures).
- **Markdown** (`.md`): human-readable reports.
- **JSON-lines log** (`run.log`): each line has `timestamp`, `level`, `message`, `module`, `extra`, and optional `traceback`.

---

## Working with the data

### pandas

```python
import pandas as pd

run = "runs/20260209T143000Z"
vid = "dQw4w9WgXcQ"

# Per-video layout
comments  = pd.read_json(f"{run}/videos/{vid}/comments/comments.jsonl", lines=True)
chunks    = pd.read_json(f"{run}/videos/{vid}/transcripts/transcript_chunks.jsonl", lines=True)
topics    = pd.read_json(f"{run}/videos/{vid}/enrich/topics.jsonl", lines=True)
sentiment = pd.read_json(f"{run}/videos/{vid}/enrich/sentiment.jsonl", lines=True)
urls      = pd.read_json(f"{run}/videos/{vid}/enrich/urls.jsonl", lines=True)
summary   = pd.read_json(f"{run}/videos/{vid}/enrich/summary.jsonl", lines=True)
```

### Quick analysis examples

```python
# Sentiment distribution
print(sentiment["POLARITY"].value_counts())

# Top mentioned URLs
print(urls.sort_values("MENTION_COUNT", ascending=False).head(10))

# Topic keywords
for _, row in topics.iterrows():
    print(f"Topic {row['TOPIC_ID']}: {row['LABEL']} — {row['KEYWORDS']}")
```

---

## Python API

The package exports a public API for scripts and notebooks:

```python
from yt_content_analyzer import (
    run_all, run_preflight, extract_video_id,
    Settings, load_settings, resolve_api_key, resolve_pricing,
    RunResult, PreflightResult, CheckpointStore,
    YTCAError, PreflightError, ConfigError, CollectionError, EnrichmentError,
)
```

### Examples

```python
# Single video
cfg = load_settings("config.yml")
cfg.VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
result = run_all(cfg, output_dir="runs")

# Bare video ID works too
vid = extract_video_id("dQw4w9WgXcQ")       # returns "dQw4w9WgXcQ"
vid = extract_video_id("https://youtu.be/dQw4w9WgXcQ")  # also works

# Subscription mode
cfg = load_settings("config.yml")
cfg.YT_SUBSCRIPTIONS = [{"CHANNEL": "@engineerprompt", "MAX_SUB_VIDEOS": 3}]
cfg.VIDEO_URL = None
result = run_all(cfg)

# Search mode
cfg = load_settings("config.yml")
cfg.SEARCH_TERMS = ["AI agents 2026"]
cfg.VIDEO_URL = None
result = run_all(cfg)

print(f"Processed {result.videos_processed} videos, {result.comments_collected} comments")
```

### Exception hierarchy

```
YTCAError (base)
  +-- ConfigError        # invalid or inconsistent configuration
  +-- PreflightError     # preflight checks failed (carries .results list)
  +-- CollectionError    # comment/transcript collection failure
  +-- EnrichmentError    # enrichment pipeline failure
```

---

## Architecture

### Pipeline

```
Input (URL / Channel / Search term)
  |
  v
Preflight ---- config validation, endpoint probes, fail-fast
  |
  v
Discovery ---- resolve channels (yt-dlp) or search (yt-dlp ytsearch)
  |
  v
For each video:
  |
  +-- Collection
  |     +-- Comments:    Playwright UI --> yt-dlp fallback
  |     +-- Transcripts: yt-dlp (manual preferred, auto fallback)
  |
  +-- Parse
  |     +-- Normalize comments + transcripts
  |     +-- Chunk transcripts (time windows with overlap)
  |
  +-- Enrich
        +-- Embeddings (OpenAI / Google / local)
        +-- Topic modeling (NLP clustering or LLM)
        +-- Sentiment analysis (TextBlob or LLM)
        +-- Relation triples (LLM)
        +-- URL extraction (regex)
        +-- Summarization (LLM)
```

Every stage is **checkpointed** per `(VIDEO_ID, STAGE)`. Interrupted runs resume from the last completed checkpoint.

### Package layout

```
src/yt_content_analyzer/
  cli.py                    # Click CLI (ytca command)
  config.py                 # Pydantic Settings model
  run.py                    # Pipeline orchestrator
  models.py                 # RunResult, PreflightResult
  exceptions.py             # YTCAError hierarchy
  preflight/                # Config validation + endpoint probes
  discovery/                # Channel resolver, search resolver
  collectors/               # Comments (Playwright, yt-dlp) + transcripts
  parse/                    # Normalization, chunking, PII, translation
  enrich/                   # Embeddings, topics, sentiment, triples, URLs, summaries
  reporting/                # Jinja2 Markdown reports (scaffolded)
  knowledge_graph/          # RDF + NetworkX (scaffolded)
  state/                    # JSON checkpoint store
  utils/                    # JSONL I/O, logging
```

### Config precedence

Defaults &rarr; YAML file &rarr; Environment variables &rarr; CLI flags

---

## Development

```bash
# Run the full test suite
pytest

# Run a single test file
pytest tests/test_priority1.py

# Run a single test by name
pytest tests/test_priority1.py -k "test_checkpoint_round_trip"

# Lint
ruff check src/ tests/

# Auto-fix lint issues
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
| `test_smoke.py` | Import verification |
| `test_priority1.py` | Error handling, logging, checkpoints, CLI resume |
| `test_collection.py` | Collection pipeline integration |
| `test_comments_playwright.py` | Playwright comment collector (heavily mocked) |
| `test_enrichment.py` | Enrichment pipeline (topics, sentiment, triples, URLs, summaries) |
| `test_subscriptions.py` | Subscription mode: config, channel resolver, preflight, CLI |
| `test_input_modes.py` | Bare video IDs, `--channel` CLI, search discovery, per-video output |
| `test_api_connectivity.py` | Live API probes (skipped if keys missing) |

### Code style

- **Formatter/linter:** Ruff, `line-length = 100`
- **Type hints:** Python 3.10+ style (`from __future__ import annotations`, `list[str]`)
- **Type checker:** mypy (`disallow_untyped_defs = false`)

---

## License

MIT. See [LICENSE](LICENSE).
