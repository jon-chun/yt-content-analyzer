# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

yt-content-analyzer is a scrape-first YouTube comments + transcripts collection and analysis tool for moderate academic research scale (10–500 videos). Given a URL, search terms, or channel subscriptions, it collects comments (Top/Newest sort), transcripts (manual preferred, auto fallback), enriches via NLP/LLM pipelines, and produces JSONL datasets plus Markdown reports. The single-video pipeline, subscription-based multi-video pipeline, and search-term discovery are all functional end-to-end.

## Commands

```bash
# Install (development)
pip install -e ".[dev,scrape,reports,nlp]"
playwright install

# Run full test suite
pytest

# Run a single test file
pytest tests/test_priority1.py

# Run a single test by name
pytest tests/test_priority1.py -k "test_checkpoint_round_trip"

# Lint (check only)
ruff check src/ tests/

# Lint (auto-fix)
ruff check --fix src/ tests/

# Type check
mypy src/

# CLI
ytca preflight --config config.yml
ytca run-all --config config.yml --video-url "https://www.youtube.com/watch?v=VIDEO_ID"
ytca run-all --config config.yml --video-url "4jQChe0rg1c"   # bare video ID
ytca run-all --resume 20260101T120000Z

# Subscription mode (fetch latest videos from channels)
ytca run-all --config config.yml --subscriptions
ytca run-all --config config.yml --channel "@engineerprompt" --channel "@firaborova"

# Search term discovery
ytca run-all --config config.yml --terms "Claude CoWork" --terms "AI agents"
```

## Architecture

**Package layout:** `src/yt_content_analyzer/` — hatchling build, entry point `ytca = yt_content_analyzer.cli:main`.

**Pipeline stages** (checkpointed per `(VIDEO_ID, STAGE)`):
1. **Preflight** (`preflight/`) — multi-level config validation, endpoint probes, fail-fast
2. **Discovery** (`discovery/`) — channel subscriptions or search terms (both via yt-dlp) → video list
3. **Collection** (`collectors/`) — comments + transcripts with provider fallback chains:
   - Comments: Playwright UI → yt-dlp → YouTube Data API v3
   - Transcripts: transcript extractor lib → yt-dlp subtitles → Playwright UI
4. **Parse** (`parse/`) — normalize, chunk transcripts (time windows with overlap), PII strip, translate
5. **Enrich** (`enrich/`) — embeddings, topic modeling (NLP/LLM), sentiment, relation triples
6. **Reporting** (`reporting/`) — Jinja2 Markdown reports *(scaffolded)*
7. **Knowledge Graph** (`knowledge_graph/`) — RDFLib+NetworkX+PyVis *(scaffolded)*

**Orchestrator:** `run.py` — `run_all()` drives the full pipeline, building a video list (single URL, subscriptions, or search terms) and processing each video through collection + enrichment. When `OUTPUT_PER_VIDEO` is true (default), each video's data goes to `runs/<RUN_ID>/videos/<VID>/`; when false, uses flat layout under `runs/<RUN_ID>/`.

**Key modules:**
- `config.py` — Pydantic Settings model with ALL_CAPS keys. Precedence: defaults → YAML → env vars → CLI overrides. Resolved config persisted to `manifest.json`.
- `state/checkpoint.py` — JSON-based checkpoint store for interrupt/resume. Stages marked `"DONE"` or `"FAILED"`.
- `utils/io.py` — append-mode JSONL and CSV writers, failure record writer.
- `utils/logger.py` — `setup_cli_logging()` for Rich console output, `setup_file_handler()` for JSON-lines file logging. Modules use `logging.getLogger(__name__)`.

**Public API** (`__init__.py` exports): `run_all`, `run_preflight`, `extract_video_id`, `Settings`, `load_settings`, `resolve_api_key`, `resolve_pricing`, `RunResult`, `PreflightResult`, `CheckpointStore`, and the exception hierarchy.

**Exception hierarchy:**
```
YTCAError (base)
├── ConfigError        — invalid/inconsistent config
├── PreflightError     — preflight failed (carries .results list)
├── CollectionError    — comment/transcript collection failure
└── EnrichmentError    — enrichment pipeline failure
```

## Configuration

- Config keys are ALL_CAPS everywhere (YAML, Settings model, env vars).
- Env vars use canonical provider names (`OPENAI_API_KEY`, `YOUTUBE_API_KEY`, etc.) resolved at runtime via `resolve_api_key(provider)`.
- Hard caps enforced: `MAX_VIDEOS_PER_TERM <= 10`, `MAX_TOTAL_VIDEOS <= 500`.
- `VIDEO_URL`, `SEARCH_TERMS`, and `YT_SUBSCRIPTIONS` are mutually exclusive inputs.
- `ON_VIDEO_FAILURE`: `"skip"` (default, log + continue) or `"abort"` (halt immediately).
- `OUTPUT_PER_VIDEO`: `true` (default) → per-video subdirs; `false` → flat layout.
- See `config.example.yml` for all available keys with defaults.

## Tests

Tests live in `tests/` using pytest. No conftest or fixtures beyond standard library mocking.

- `test_smoke.py` — basic import and smoke tests
- `test_priority1.py` — core functionality: error handling, logging, checkpoints, CLI resume
- `test_collection.py` — collection pipeline integration
- `test_comments_playwright.py` — Playwright comment collector (heavily mocked)
- `test_enrichment.py` — enrichment pipeline
- `test_api_connectivity.py` — live API probes (skipped if keys missing)
- `test_subscriptions.py` — subscription mode: config, channel resolver, preflight, CLI
- `test_input_modes.py` — bare video IDs, --channel CLI, search discovery, per-video output

## Style

- Ruff with `line-length = 100`.
- Python 3.10+ — uses `from __future__ import annotations` and `list[str]` style annotations.
- mypy: `python_version = "3.10"`, `disallow_untyped_defs = false`.
- Optional dependency groups: `scrape` (playwright, yt-dlp), `nlp` (numpy, pandas, scikit-learn, textblob), `reports` (Jinja2), `kg` (rdflib, networkx, pyvis).
