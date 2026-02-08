# yt-content-analyzer

Scrape-first YouTube **comments + transcripts** collection and analysis for moderate academic research scale.

Given a YouTube URL or a set of search terms, `yt-content-analyzer` discovers top videos, collects comments (in both Top and Newest sort orders) and transcripts (manual captions preferred, auto-generated allowed as fallback), enriches the text through configurable NLP pipelines, and produces structured datasets alongside human-readable reports.

> **Note:** This tool is intended for research-scale analysis (10-20 search terms, up to 500 videos total), not massive dataset harvesting.

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

Runs are checkpointed automatically. If a run is interrupted, re-running the same command resumes from the last completed stage per video. Checkpoint state is stored in `runs/<RUN_ID>/state/checkpoint.json`.

## Output structure

Each run produces a self-contained directory under `runs/`:

```
runs/<RUN_ID>/
  manifest.json              # Resolved config snapshot for reproducibility
  logs/
    run.log                  # Full execution log
  discovery/                 # Resolved video list with metadata
  comments/                  # Collected comments (JSONL + CSV)
  transcripts/               # Transcript segments + time-chunks (JSONL + CSV)
  enrich/                    # Enrichment outputs
    topics/                  #   Topic modeling results
    sentiment/               #   Sentiment analysis results
    triples.jsonl            #   Extracted relation triples
  failures/                  # Per-video failure logs and debug artifacts
  reports/                   # Human-readable Markdown reports
    preflight_<RUN_ID>.md    #   Preflight diagnostics
    report_*_all.md          #   Aggregate report across all videos
    report_*_by-term.md      #   Grouped by search term
    report_*_by-vid.md       #   Per-video breakdown
  state/
    checkpoint.json          # Resume state
```

### Working with the data

**JSONL files** contain one JSON object per line. Load with pandas:

```python
import pandas as pd
comments = pd.read_json("runs/<RUN_ID>/comments/comments.jsonl", lines=True)
```

**CSV files** mirror the JSONL data in tabular form for spreadsheet tools.

**Markdown reports** provide human-readable summaries including:
- Themes from Top-sorted comments
- Timeline analysis from Newest-sorted comments
- Transcript themes, timeline, and key claims
- Transcript availability and coverage statistics

### Report variants

Control which reports are generated via `REPORT_VARIANTS` in config:
- `all` -- aggregate report across every video in the run
- `by-term` -- one report per search term
- `by-vid` -- one report per individual video

## Pipeline overview

```
Search terms / URL
  --> Discovery (scrape YouTube search, apply filters)
    --> Collection
        Comments: Playwright UI -> yt-dlp -> API v3 fallback
        Transcripts: extractor lib -> yt-dlp subs -> Playwright UI fallback
      --> Parse (normalize, chunk transcripts, optional PII strip, optional translate)
        --> Enrich (embeddings, topic modeling, sentiment, triples)
          --> Report (Jinja2 Markdown templates)
```

Each stage is checkpointed per `(VIDEO_ID, ASSET_TYPE, SORT_MODE, STAGE)` so interrupted runs resume without re-collecting already-completed work.

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
