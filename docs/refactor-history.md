# Refactor: PyPI Library Best Practices

**Version:** 0.2.1 &rarr; 0.3.0
**Date:** 2026-02-08
**Commits:** `1d86aab`, `4f7b150`
**Scope:** 35 files changed, +1,401 / -167 lines

---

## 1. Motivation

Before this refactoring, `yt-content-analyzer` worked only as a CLI tool. It could not be imported as a Python library&mdash;`from yt_content_analyzer import run_all` failed because:

- There was no public API surface (the top-level `__init__.py` was nearly empty).
- 7 of 8 subpackages were missing `__init__.py` files.
- The orchestrator (`run.py`) hard-coded `Path("runs")` as the output directory.
- Preflight failures raised `SystemExit` instead of a catchable exception.
- Logging used a global singleton, making it impossible to control from library code.
- The CLI had only 2 switches (`--config` and `--terms`), with no way to override common settings from the command line.

The goal was to make the package **dual-use**: importable as a Python library with structured return types and proper exceptions, while remaining fully functional as a CLI with rich command-line customization.

---

## 2. Summary of Changes

### 2.1 New Files

| File | Purpose |
|------|---------|
| `src/yt_content_analyzer/exceptions.py` | Exception hierarchy for library consumers |
| `src/yt_content_analyzer/models.py` | Structured result dataclasses (`RunResult`, `PreflightResult`) |
| `src/yt_content_analyzer/collectors/__init__.py` | Re-exports `collect_comments_ytdlp`, `collect_transcript_ytdlp` |
| `src/yt_content_analyzer/parse/__init__.py` | Re-exports `normalize_comments`, `normalize_transcripts`, `chunk_transcripts` |
| `src/yt_content_analyzer/enrich/__init__.py` | Re-exports `analyze_sentiment`, `extract_topics_llm`, `extract_topics_nlp`, `extract_triples`, `compute_embeddings` |
| `src/yt_content_analyzer/preflight/__init__.py` | Re-exports `run_preflight` |
| `src/yt_content_analyzer/state/__init__.py` | Re-exports `CheckpointStore` |
| `src/yt_content_analyzer/utils/__init__.py` | Re-exports `read_jsonl`, `write_jsonl`, `write_csv`, `write_failure` |
| `src/yt_content_analyzer/discovery/__init__.py` | Empty (scaffold subpackage) |
| `src/yt_content_analyzer/reporting/__init__.py` | Empty (scaffold subpackage) |
| `src/yt_content_analyzer/knowledge_graph/__init__.py` | Empty (scaffold subpackage) |
| `tests/test_priority1.py` | 441-line test suite covering error handling, logging, checkpoints, CLI resume |
| `tests/test_api_connectivity.py` | Live API probes for all configured providers |

### 2.2 Modified Files

| File | Change Summary |
|------|----------------|
| `src/yt_content_analyzer/__init__.py` | Full public API surface with `__all__` and version `0.3.0` |
| `src/yt_content_analyzer/run.py` | `run_all()` returns `RunResult`, accepts `output_dir`, raises `PreflightError` |
| `src/yt_content_analyzer/cli.py` | Full rewrite with global options and 10 new CLI switches |
| `src/yt_content_analyzer/utils/logger.py` | Removed singleton, added `setup_cli_logging()` and `setup_file_handler()` |
| `src/yt_content_analyzer/utils/io.py` | Added `mode` parameter to `write_jsonl()` and `write_csv()` |
| `src/yt_content_analyzer/preflight/checks.py` | Returns `PreflightResult` instead of `bool` |
| `src/yt_content_analyzer/config.py` | Added `ON_VIDEO_FAILURE` validator, updated pricing keys |
| `src/yt_content_analyzer/collectors/comments_playwright_ui.py` | Added `artifact_dir` kwarg |
| `src/yt_content_analyzer/enrich/llm_client.py` | Added `User-Agent` header to HTTP requests |
| 12 modules (collectors, enrich, utils, state) | Replaced `get_logger()` with `logging.getLogger(__name__)` |
| `pyproject.toml` | Version 0.2.1 &rarr; 0.3.0 |
| `CLAUDE.md` | Added new CLI switches and library usage examples |
| `README.md` | Pipeline status, resume docs, error handling, output format reference |
| `config.example.yml` | Added `ON_VIDEO_FAILURE`, fixed xAI model name |
| `tests/test_comments_playwright.py` | Updated to new function signatures |

---

## 3. Phase-by-Phase Details

### Phase 1: Exception Hierarchy and Result Types

**Problem:** `run_all()` called `raise SystemExit(2)` on preflight failure. Library consumers could not catch this cleanly&mdash;`SystemExit` is derived from `BaseException`, not `Exception`, so a bare `except Exception` block would miss it entirely.

**Solution:** Created a rooted exception hierarchy and structured result dataclasses.

**`exceptions.py`:**

```
YTCAError (base)
  +-- ConfigError          # invalid or inconsistent configuration
  +-- PreflightError       # preflight checks failed (carries .results list)
  +-- CollectionError      # comment/transcript collection failure
  +-- EnrichmentError      # enrichment pipeline failure
```

`PreflightError` stores the full preflight results list and generates a human-readable message listing which checks failed.

**`models.py`:**

```python
@dataclass
class RunResult:
    run_id: str              # e.g. "20260208T235833Z"
    output_dir: Path         # e.g. Path("runs/20260208T235833Z")
    videos_processed: int    # count of videos that completed the pipeline
    comments_collected: int  # total deduplicated comments
    transcript_chunks: int   # total time-windowed transcript chunks
    output_files: list[Path] # all generated output file paths
    failures: list[dict]     # per-stage failure records

@dataclass
class PreflightResult:
    ok: bool                 # True if all checks passed
    results: list[dict]      # individual check results
    report_path: Path | None # path to preflight report, if generated
```

### Phase 2: Logger Refactoring

**Problem:** `utils/logger.py` used a global singleton (`_LOGGER`) accessed via `get_logger()`. Every module in the package called `get_logger()`, which returned the same logger instance regardless of the calling module. This made log filtering impossible and violated Python logging best practices.

**Solution:**

1. **Replaced the singleton** with standard `logging.getLogger(__name__)` in all 13 consumer modules.

2. **Deprecated `get_logger()`** &mdash; it now emits a `DeprecationWarning` and returns `logging.getLogger("yt_content_analyzer")` as a backward-compatible shim.

3. **Added `setup_cli_logging(*, verbosity=0)`** &mdash; attaches a `RichHandler` to the `yt_content_analyzer` logger. Called only from `cli.py`. Verbosity mapping:
   - `-1` (quiet) &rarr; WARNING
   - `0` (default) &rarr; INFO
   - `1+` (verbose) &rarr; DEBUG

4. **Renamed `configure_file_logging`** to `setup_file_handler(logger, log_dir)` with a backward-compatible shim.

5. **Kept `JsonLineFormatter`** unchanged&mdash;it formats log records as one JSON object per line for machine-parseable `run.log` files.

**Modules updated** (13 total):

`run.py`, `preflight/checks.py`, `collectors/comments_ytdlp.py`, `collectors/transcript_ytdlp.py`, `collectors/comments_playwright_ui.py`, `enrich/llm_client.py`, `enrich/embeddings_client.py`, `enrich/topics_nlp.py`, `enrich/topics_llm.py`, `enrich/sentiment.py`, `enrich/triples.py`, `utils/io.py`, `state/checkpoint.py`

### Phase 3: Subpackage `__init__.py` Files

**Problem:** 7 of 8 subpackages had no `__init__.py`, making them non-importable as Python packages. `from yt_content_analyzer.collectors import collect_comments_ytdlp` failed.

**Solution:** Created `__init__.py` for all 8 subpackages. Implemented packages re-export public symbols with `__all__`. Scaffold-only packages (`discovery/`, `reporting/`, `knowledge_graph/`) have empty init files.

| Subpackage | Re-exports |
|-----------|-----------|
| `collectors/` | `collect_comments_ytdlp`, `collect_transcript_ytdlp` |
| `parse/` | `normalize_comments`, `normalize_transcripts`, `chunk_transcripts` |
| `enrich/` | `analyze_sentiment`, `extract_topics_llm`, `extract_topics_nlp`, `extract_triples`, `compute_embeddings` |
| `preflight/` | `run_preflight` |
| `state/` | `CheckpointStore` |
| `utils/` | `read_jsonl`, `write_jsonl`, `write_csv`, `write_failure` |

All optional dependencies (yt-dlp, playwright, numpy, sklearn) are imported lazily inside function bodies, so these re-exports are safe at import time.

### Phase 4: Core API Refactoring

#### `run.py` &mdash; `run_all()` signature change

**Before:**
```python
def run_all(cfg: Settings) -> None:
    out_dir = Path("runs") / run_id
    ...
    if not preflight_ok:
        raise SystemExit(2)
```

**After:**
```python
def run_all(
    cfg: Settings,
    *,
    output_dir: Path | str | None = None,
    resume_run_id: str | None = None,
) -> RunResult:
    base_dir = Path(output_dir) if output_dir is not None else Path("runs")
    ...
    if not preflight_result.ok:
        raise PreflightError(preflight_result.results)
    ...
    return result
```

Key changes:
- **`output_dir` parameter** (default `None` &rarr; falls back to `Path("runs")` for backward compat).
- **Returns `RunResult`** populated with counts and output file paths throughout the pipeline.
- **`raise PreflightError`** instead of `SystemExit(2)`.
- **Fixed `datetime.utcnow()`** (deprecated in Python 3.12) to `datetime.now(timezone.utc)`.
- Helper functions (`_collect_and_process_comments`, `_collect_and_process_transcript`, `_enrich_video`) accept `result: RunResult` and `failures_dir: Path` to accumulate counts.

#### `preflight/checks.py`

**Before:** Returned `bool`.
**After:** Returns `PreflightResult(ok=bool, results=list[dict], report_path=Path|None)`.

#### `utils/io.py`

Added `mode: str = "a"` parameter to `write_jsonl()` and `write_csv()`. Default stays append for backward compat; API users can pass `mode="w"` to overwrite.

#### `collectors/comments_playwright_ui.py`

Added `artifact_dir: Path | None = None` kwarg to `collect_comments_playwright_ui()`. Replaces hard-coded `Path("failures")` in `_save_artifact()`. When `None`, artifact saving is skipped.

### Phase 5: Public API Surface

**`__init__.py`** now provides a complete public API:

```python
from yt_content_analyzer import (
    # Core pipeline
    run_all, run_preflight, extract_video_id,
    # Configuration
    Settings, load_settings, resolve_api_key, resolve_pricing,
    # Result types
    RunResult, PreflightResult,
    # Exceptions
    YTCAError, PreflightError, ConfigError, CollectionError, EnrichmentError,
    # State
    CheckpointStore,
)
```

**Library usage example:**

```python
from yt_content_analyzer import run_all, Settings, load_settings, PreflightError

cfg = load_settings("config.yml")
cfg.VIDEO_URL = "https://www.youtube.com/watch?v=abc123"

try:
    result = run_all(cfg, output_dir="/tmp/analysis")
    print(f"Collected {result.comments_collected} comments")
    print(f"Generated {len(result.output_files)} output files")
except PreflightError as e:
    print(f"Preflight failed: {e}")
    for check in e.results:
        if not check.get("OK"):
            print(f"  FAIL: {check['NAME']}")
```

### Phase 6: CLI Enrichment

**Before:** 2 switches (`--config`, `--terms`), no global options, no resume support.

**After:** Full Click-based CLI with global options and 10 switches on `run-all`:

**Global options:**
- `-v / --verbose` (count) &mdash; increase verbosity, repeat for DEBUG
- `-q / --quiet` (flag) &mdash; suppress all but warnings

**`preflight` command:**
- `--config` (required) &mdash; path to YAML config
- `--output-dir` &mdash; where to write preflight report

**`run-all` command:**

| Switch | Maps to | Default |
|--------|---------|---------|
| `--config` | `load_settings(path)` | Required for new runs |
| `--video-url` | `cfg.VIDEO_URL` | None |
| `--terms` (multiple) | `cfg.SEARCH_TERMS` | None |
| `--output-dir` | `output_dir` param | `./runs` |
| `--resume` | `resume_run_id` | None |
| `--sort-modes` | `cfg.COLLECT_SORT_MODES` | Comma-separated |
| `--max-comments` | `cfg.MAX_COMMENTS_PER_VIDEO` | None |
| `--no-transcripts` | `cfg.TRANSCRIPTS_ENABLE=False` | False |
| `--llm-provider` | `cfg.LLM_PROVIDER` | None |
| `--llm-model` | `cfg.LLM_MODEL` | None |
| `--on-failure` | `cfg.ON_VIDEO_FAILURE` | skip or abort |

Resume mode reloads config from `manifest.json` and skips preflight. The CLI catches `PreflightError` and converts it to `SystemExit(2)`. On completion, it prints a `RunResult` summary.

### Phase 7: Version Bump, Docs, and Bug Fixes

- **`pyproject.toml`** version: `0.2.1` &rarr; `0.3.0`
- **`__init__.py`** `__version__`: `0.3.0`
- **`CLAUDE.md`** updated with new CLI switches and library usage
- **`README.md`** rewritten with current pipeline status, resume instructions, error handling docs, output file format reference, and data loading examples
- **xAI model name** corrected from `grok-4-1-fast` to `grok-4-1-fast-non-reasoning` across `config.py`, `config.example.yml`, and `test_api_connectivity.py`
- **`User-Agent` header** added to `llm_client._post_json()` to prevent Cloudflare bot protection (error 1010) from blocking Python's default `Python-urllib/3.x` user agent on the xAI API

---

## 4. Test Coverage

### New test suites

**`tests/test_priority1.py`** (441 lines, 22 tests):
- `ON_VIDEO_FAILURE` config validation (skip, abort, invalid values)
- `read_jsonl` hardening (bad lines, empty files, missing files)
- `write_failure` schema, directory creation, video ID sanitization
- Collector retry logic (yt-dlp fail-then-succeed, retry exhaustion)
- Enrichment error handling (topics, sentiment, triples graceful degradation)
- `JsonLineFormatter` output validation (valid JSON, extra fields, exception tracebacks)
- `configure_file_logging` / `setup_file_handler` (creates `run.log`, idempotent)
- Checkpoint corruption recovery (corrupt backup, no temp files, atomic save)
- Checkpoint `FAILED` status (not treated as done, can transition to done)
- CLI resume (missing run dir, loads manifest when no config)

**`tests/test_api_connectivity.py`** (138 lines, 7 tests):
- Live chat completion probes for 6 providers (OpenAI, Anthropic, xAI, DeepSeek, Fireworks, Together)
- Live embedding probe for OpenAI
- Each test skips if the provider's API key is not set in the environment

### Existing test updates

**`tests/test_comments_playwright.py`:**
- Updated `_collect_and_process_comments` calls to new signature (added `result: RunResult`, `failures_dir: Path`)
- Updated mock functions to accept `artifact_dir` kwarg

### Final test results

```
122 passed, 3 skipped in 4.64s
```

The 3 skips are providers without API keys configured (Anthropic, DeepSeek, Together).

---

## 5. Bug Fixes During Refactoring

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `_collect_and_process_comments()` signature mismatch in tests | Refactored helper changed from `(cfg, ..., logger)` to `(cfg, ..., result, failures_dir)` | Updated 2 tests in `test_comments_playwright.py` |
| Logger idempotency test failure | Test referenced removed `_LOGGER` global singleton | Rewrote test to use `logging.getLogger("yt_content_analyzer")` directly |
| CLI resume test mock miss | `run_all` was lazy-imported inside function body, not at module level | Changed mock path from `yt_content_analyzer.cli.run_all` to `yt_content_analyzer.run.run_all` |
| `fake_playwright` missing kwarg | `artifact_dir` parameter added to production function | Added `**kwargs` to mock function |
| xAI API 403 (Cloudflare 1010) | Python's default `Python-urllib/3.x` User-Agent blocked by Cloudflare | Added `User-Agent: yt-content-analyzer` header to `_post_json()` |
| xAI model not found | Wrong model name `grok-4-1-fast` | Corrected to `grok-4-1-fast-non-reasoning` |
| `datetime.utcnow()` deprecation | Python 3.12 deprecation warning | Changed to `datetime.now(timezone.utc)` |

---

## 6. Backward Compatibility

| Area | Compat Status | Notes |
|------|--------------|-------|
| CLI `ytca run-all --config ... --terms ...` | Preserved | Old 2-switch invocation still works |
| `get_logger()` | Deprecated shim | Emits `DeprecationWarning`, returns package logger |
| `configure_file_logging(log_dir)` | Shim | Delegates to `setup_file_handler()` |
| `write_jsonl()` / `write_csv()` default mode | Preserved | Default `mode="a"` unchanged |
| `run_all(cfg)` with no extra kwargs | Works | `output_dir` defaults to `Path("runs")`, returns `RunResult` instead of `None` |
| Config file format | Unchanged | All YAML keys identical, new `ON_VIDEO_FAILURE` key has default |

---

## 7. Architecture Before and After

### Before (v0.2.1)

```
yt_content_analyzer/
  __init__.py          # empty, no public API
  cli.py               # 2 switches
  run.py               # returns None, raises SystemExit
  config.py
  collectors/          # no __init__.py
  parse/               # no __init__.py
  enrich/
    __init__.py        # existed but no re-exports
  preflight/           # no __init__.py
  state/               # no __init__.py
  utils/
    logger.py          # global singleton _LOGGER + get_logger()
    io.py              # no mode parameter
```

### After (v0.3.0)

```
yt_content_analyzer/
  __init__.py          # public API: 15 symbols in __all__
  exceptions.py        # YTCAError hierarchy
  models.py            # RunResult, PreflightResult
  cli.py               # 12 switches + global options
  run.py               # returns RunResult, raises PreflightError
  config.py            # ON_VIDEO_FAILURE validator
  collectors/
    __init__.py        # re-exports
  parse/
    __init__.py        # re-exports
  enrich/
    __init__.py        # re-exports
  preflight/
    __init__.py        # re-exports
  state/
    __init__.py        # re-exports
  utils/
    __init__.py        # re-exports
    logger.py          # setup_cli_logging() + setup_file_handler()
    io.py              # mode="a"|"w" parameter
  discovery/
    __init__.py        # scaffold
  reporting/
    __init__.py        # scaffold
  knowledge_graph/
    __init__.py        # scaffold
```
