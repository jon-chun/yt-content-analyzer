# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

yt-content-analyzer is a scrape-first YouTube comments + transcripts collection and analysis tool for moderate academic research scale. It resolves search terms to top-N videos, collects comments (Top/Newest sort modes) and transcripts (manual preferred, auto fallback), enriches via translation/embeddings/sentiment/triples, and produces JSONL/CSV datasets plus Markdown reports. The pipeline is early-stage — most modules are scaffolded but not yet implemented.

## Commands

```bash
# Install (development)
pip install -e ".[dev,scrape,reports,nlp]"
playwright install

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/

# CLI entry point
ytca preflight --config config.yaml
ytca run-all --config config.yaml --terms "AI agents 2026"
```

## Architecture

**Package layout:** `src/yt_content_analyzer/` (hatchling build, wheel packages from `src/`).

**Pipeline stages** (checkpointed per `(VIDEO_ID, ASSET_TYPE, SORT_MODE, STAGE)`):
1. **Preflight** (`preflight/`) — multi-level config validation, endpoint probes, fail-fast
2. **Discovery** (`discovery/`) — search terms → video list via scraping (API fallback rare)
3. **Collection** (`collectors/`) — comments + transcripts with provider fallback chains:
   - Comments: Playwright UI → yt-dlp → YouTube Data API v3
   - Transcripts: transcript extractor lib → yt-dlp subtitles → Playwright UI
4. **Parse** (`parse/`) — normalize, chunk transcripts (time windows with overlap), PII strip, translate
5. **Enrich** (`enrich/`) — embeddings (local/remote with sampling fallback), topic modeling (NLP/LLM), sentiment, relation triples
6. **Reporting** (`reporting/`) — Jinja2 Markdown reports in variants: all, by-term, by-vid
7. **Knowledge Graph** (`knowledge_graph/`) — optional/future RDFLib+NetworkX+PyVis

**Key modules:**
- `config.py` — Pydantic Settings model with ALL_CAPS keys. Precedence: defaults → YAML config → env vars → CLI overrides. Resolved config persisted to `runs/<RUN_ID>/manifest.json`.
- `state/checkpoint.py` — JSON-based checkpoint store for interrupt/resume. Keyed by `(VIDEO_ID, ASSET_TYPE, SORT_MODE, STAGE)`.
- `utils/io.py` — append-mode JSONL and CSV writers.
- `utils/logger.py` — singleton Rich-based logger.

**Run output structure:** `runs/<RUN_ID>/` with subdirs: `logs/`, `discovery/`, `comments/`, `transcripts/`, `enrich/`, `failures/`, `reports/`, `state/`.

## Configuration

- Config keys are ALL_CAPS everywhere (YAML, Settings model, env vars).
- Env vars use canonical provider names (`OPENAI_API_KEY`, `YOUTUBE_API_KEY`, etc.) resolved at runtime via `resolve_api_key(provider)` in `config.py`.
- Hard caps enforced: `MAX_VIDEOS_PER_TERM <= 10`, `MAX_TOTAL_VIDEOS <= 500`.
- `VIDEO_URL` and `SEARCH_TERMS` are mutually exclusive inputs.

## Style

- Ruff with `line-length = 100`.
- Python 3.10+ (uses `list[str]` style annotations with `from __future__ import annotations`).
- mypy configured with `python_version = "3.10"`, `disallow_untyped_defs = false`.
- Optional dependency groups: `scrape` (playwright, yt-dlp), `nlp` (numpy, pandas), `reports` (Jinja2), `kg` (rdflib, networkx, pyvis).
