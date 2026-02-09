# yt-content-analyzer

Scrape-first YouTube **comments + transcripts** collection and analysis for moderate academic research scale.

Given a YouTube URL or a set of search terms, `yt-content-analyzer` discovers top videos, collects comments (in both Top and Newest sort orders) and transcripts (manual captions preferred, auto-generated allowed as fallback), enriches the text through configurable NLP pipelines, and produces structured datasets alongside human-readable reports.

> **Note:** This tool is intended for research-scale analysis (10-20 search terms, up to 500 videos total), not massive dataset harvesting.

## Current status

The single-video pipeline is functional end-to-end: transcript collection, comment collection, and enrichment (topics, sentiment, triples) all work. Discovery-based multi-video pipelines are scaffolded but not yet implemented. Error handling, retry logic, persistent file logging, and run resume are implemented.

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

Optional dependency groups you can include:

| Group     | What it adds                               |
|-----------|--------------------------------------------|
| `scrape`  | Playwright, yt-dlp (browser + CLI scraping)|
| `nlp`     | NumPy, pandas (data analysis)              |
| `reports` | Jinja2 (Markdown report generation)        |
| `kg`      | rdflib, NetworkX, PyVis (knowledge graphs) |
| `dev`     | pytest, ruff, mypy, build, twine           |

## Setup

### 1. Configuration file

Copy and edit the example config:

```bash
cp config.example.yaml config.yaml
```

The config file uses **ALL_CAPS** keys organized into sections:

| Section              | Key settings                                                              |
|----------------------|---------------------------------------------------------------------------|
| **Inputs**           | `VIDEO_URL` or `SEARCH_TERMS`, `MAX_VIDEOS_PER_TERM`, `MAX_TOTAL_VIDEOS` |
| **Discovery filters**| `VIDEO_LANG`, `VIDEO_REGION`, `VIDEO_UPLOAD_DATE`, `MIN_VIEWS`            |
| **Collection**       | `ROBUST_OVER_SPEED`, `COLLECT_SORT_MODES`, `MAX_COMMENTS_PER_VIDEO`       |
| **Transcripts**      | `TRANSCRIPTS_ENABLE`, `TRANSCRIPTS_PREFER_MANUAL`, `TRANSCRIPT_CHUNK_*`   |
| **Rate limiting**    | `API_RATE_LIMIT_RPS`, `API_MAX_CONCURRENT_CALLS`, `API_JITTER_MS_*`       |
| **Translation**      | `AUTO_TRANSLATE`, `TRANSLATE_PROVIDER`, `TRANSLATE_MODEL`                  |
| **Embeddings**       | `EMBEDDINGS_ENABLE`, `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_MODEL`            |
| **NLP**              | `TM_CLUSTERING` (nlp or llm), `SA_GRANULARITY`, `STRIP_PII`              |
| **Error handling**   | `ON_VIDEO_FAILURE` (`skip` or `abort`), `MAX_RETRY_SCRAPE`                |
| **Reporting**        | `REPORT_VARIANTS`, `RUN_DESC_4WORDS`                                      |

See `config.example.yaml` for all available keys with defaults.

**Important constraints:**
- `VIDEO_URL` and `SEARCH_TERMS` are mutually exclusive. Provide one or the other.
- `MAX_VIDEOS_PER_TERM` must be <= 10; `MAX_TOTAL_VIDEOS` must be <= 500.

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
ytca preflight --config config.yaml
```

Preflight validates config invariants, checks local environment readiness (Playwright, browsers), probes remote endpoints, and verifies transcript provider availability. Results are printed to the terminal and saved as a Markdown report.

## Usage

### Collect from search terms

```bash
ytca run-all --config config.yaml --terms "AI agents 2026" --terms "robotics policy"
```

The `--terms` flag overrides `SEARCH_TERMS` in the config file. Pass multiple `--terms` for multi-topic collection.

### Collect from a single video URL

Set `VIDEO_URL` in your `config.yaml` (leave `SEARCH_TERMS` empty), then:

```bash
ytca run-all --config config.yaml
```

### Resuming an interrupted run

Runs are checkpointed automatically. If a run is interrupted, resume it by RUN_ID:

```bash
ytca run-all --resume 20260208T235833Z
```

Resume mode reloads config from the run's `manifest.json` and skips preflight. You can optionally pass `--config` to override settings:

```bash
ytca run-all --resume 20260208T235833Z --config updated_config.yaml
```

### Error handling

By default, `ON_VIDEO_FAILURE` is set to `skip`: if a collection or enrichment stage fails for a video, the error is logged to `failures/`, the checkpoint is marked `FAILED`, and the pipeline continues to the next stage or video. Set `ON_VIDEO_FAILURE: "abort"` to halt on the first error instead.

Collection stages (yt-dlp calls) retry automatically with exponential backoff up to `MAX_RETRY_SCRAPE` times. Enrichment stages (embeddings, topics, sentiment, triples) each run independently -- a failure in one does not block the others.

## Output structure

Each run produces a self-contained directory under `runs/`. Every output is append-safe JSONL or standalone JSON, so a crashed run leaves valid partial data that a resume can build on.

```
runs/<RUN_ID>/
  manifest.json                  # Resolved config snapshot (JSON, for reproducibility)
  logs/
    run.log                      # Full execution log (JSON-lines, one object per entry)
  transcripts/
    transcript_segments.jsonl    # Raw normalized segments (one per caption line)
    transcript_chunks.jsonl      # Time-windowed chunks (60s window, 10s overlap)
  comments/
    comments.jsonl               # Normalized comments (flat, with reply threading)
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

**Design rationale:**

- **JSONL** (`.jsonl`) for all multi-record datasets. One JSON object per line, append-mode safe. This is the primary format for programmatic consumption. Load with pandas: `pd.read_json("file.jsonl", lines=True)`.
- **JSON** (`.json`) for single-document records: manifest, checkpoint, failure records, preflight results. Human-readable with `indent=2`.
- **Markdown** (`.md`) for human-readable reports: preflight diagnostics, and (planned) post-run analysis reports.
- **JSON-lines logging** (`run.log`): each line is a JSON object with `timestamp`, `level`, `message`, `module`, `extra`, and optional `traceback`. Machine-parseable for post-run analysis while remaining human-scannable.

### File format reference

| File | Format | Schema |
|------|--------|--------|
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

## Pipeline overview

```
Search terms / URL
  --> Preflight (config validation, endpoint probes)
    --> Discovery (scrape YouTube search, apply filters)
      --> Collection
          Transcripts: yt-dlp subtitles (manual preferred, auto fallback)
          Comments: yt-dlp comment extraction
        --> Parse (normalize, chunk transcripts by time windows)
          --> Enrich (embeddings, topic modeling, sentiment, triples)
            --> Report (Jinja2 Markdown templates)
```

Each stage is checkpointed per `(VIDEO_ID, STAGE)` so interrupted runs resume without re-collecting already-completed work. Failed stages are recorded with full tracebacks in `failures/` and marked in the checkpoint so they can be retried on resume.

## Development

```bash
# Run the full test suite
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Build distribution
python -m build
twine check dist/*
```

## License

MIT. See [LICENSE](LICENSE).
