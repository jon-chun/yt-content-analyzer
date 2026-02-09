# yt-content-analyzer — PRD (v0.2)
_Adds YouTube transcript download/extraction/analysis alongside comment scraping._

## Clarifications locked in
- `TRANSCRIPTS_ALLOW_AUTO=True` (default): auto captions permitted if manual captions are unavailable.
- Transcript analysis units: **both** native segments and derived time-chunks.
- Translation: when `AUTO_TRANSLATE=True`, translate **both** comments and transcripts to `VIDEO_LANG_MAIN`.

---

## 1) Overview
**Product:** `yt-content-analyzer` (Python OSS library + CLI)  
**Primary value:** Scrape-first YouTube **comments + transcripts** for a given URL or a set of search terms → top videos, then produce:
- **Machine-friendly datasets:** JSONL + CSV
- **Human-readable reports:** Markdown (`reports/`), plus optional HTML report assets

**Target scale:** 10–20 search terms × up to 10 videos/term, with `MAX_TOTAL_VIDEOS=500` hard cap (informative error on exceed).  
**Intent:** Moderate academic research, not massive dataset harvesting.

---

## 2) Goals & Success Criteria

### Goals
1. **Scrape-first discovery and collection** with robust fallback mechanisms.
2. **Collect both perspectives** per video:
   - Comments: `TOP` and `NEWEST`
   - Transcripts: best available (manual preferred, auto allowed when manual missing)
3. **Best-effort completeness**:
   - Comments: scroll/expand until “no growth after N scroll cycles”
   - Transcripts: retrieve full caption text where available
4. **Unified enrichment pipeline** across comments and transcripts:
   - Optional translation to `VIDEO_LANG_MAIN='en'`
   - Topic modeling (NLP default; LLM optional)
   - Sentiment analysis (polarity default)
   - Triples extraction → `triples.jsonl`
   - **(Optional / future)** Knowledge graph construction + visualization
5. **Interruptible + resumable** runs with checkpointing at safe boundaries (including API calls).
6. **Pre-flight validation** with detailed diagnostics saved to `reports/` and printed to terminal.

### v0.2 Success Criteria (DoD)
- From `run-all`, for each video produce:
  - `comments.*` (JSONL+CSV) with `SORT_MODE in ['top','newest']`
  - `transcripts.*` (JSONL+CSV) with timestamped segments + derived chunks
- Enrichment produces:
  - topics/sentiment/triples outputs that incorporate both comment and transcript corpora (configurable)
- Reports include:
  - “Themes from Top comments”
  - “Timeline from Newest comments”
  - “Transcript themes + timeline + key claims”
  - Transcript availability coverage + failures
- Resume works:
  - stop mid-run; resume continues from last completed (video, asset_type, sort_mode, stage)
- Preflight detects:
  - missing/invalid endpoints for translation/embeddings/LLM
  - transcript provider misconfiguration
  - Playwright/browser readiness

---

## 3) Personas & User Stories
### Personas
- **PM / Researcher:** wants what people say (comments) + what the video says (transcript), with themes, sentiment, representative excerpts.
- **Data Scientist:** wants clean structured datasets and reproducible pipelines.
- **Analyst:** wants provenance, logs, and transparent failure reporting.

### Key user stories
1. **URL-based:** “Given a YouTube URL, collect all comments + transcript and generate datasets + report.”
2. **Search-based:** “Given search terms, collect top N videos (capped), then comments + transcript for each.”
3. **Transcript fallback:** “If transcript isn’t available via extractor, attempt yt-dlp subtitles; else UI extraction; else report unavailability.”
4. **Robust mode:** “Run slower but reduce blocking and account risk.”
5. **Resume:** “Interrupt and resume without duplication.”
6. **Preflight assurance:** “Tell me before a long run if my endpoints/keys/config are wrong.”

---

## 4) Scope

### In scope (v0.2)
- Transcript acquisition (scrape-first) with provider fallback:
  1) Transcript extractor library (no Google API key) when possible
  2) `yt-dlp` subtitles / auto-subs fallback
  3) Playwright UI extraction fallback (open transcript panel, scrape timestamped text)
- Transcript normalization to structured, timestamped schema
- Transcript derived chunking (time windows with overlap)
- Unified enrichment on combined corpora (comments + transcript), with per-corpus toggles
- Report sections for transcript coverage, insights, and key excerpts
- Logging + progress reporting; robust/fast presets

### Out of scope (v0.2)
- Guaranteed transcript retrieval (some videos have no transcript, or region/age gating)
- Full RDF/Turtle graph export (architected for future)
- Massive-scale distributed crawling

---

## 5) Functional requirements (high-level)
- Inputs & caps: enforce `MAX_VIDEOS_PER_TERM<=10`, `MAX_TOTAL_VIDEOS<=500`
- Discovery & filters: language/region/date/min-views filters with sensible defaults
- Comments collection: dual sort-mode + reply expansion to `MAX_COMMENT_THREAD_DEPTH=5`
- Transcript collection: prefer manual; allow auto if missing; normalize segments + chunks
- Enrichment:
  - translation optional via configurable local/remote API
  - embeddings optional via configurable local/remote API + sampling fallback
  - sentiment and triples extraction
  - optional future knowledge graph stage
- Preflight: multi-level diagnostics report and fail-fast behavior
- Outputs: JSONL+CSV+MD reports; logs + manifest + failure logs

---

## 6) Deliverables
- GitHub repo `yt-content-analyzer`
- CLI + Python API
- Example config files with ALL_CAPS keys
- Documentation: quickstart, config guide, troubleshooting, safe scraping guidance

---

## 7) Future Features TODO

Functionality gaps identified in the v0.2 PRD, ranked by decreasing usefulness. Each item includes a concrete solution to guide implementation.

### 7.1 Cross-term video deduplication [Usefulness: 92]

**Gap:** The same video can appear in results for multiple search terms. Without deduplication, it gets scraped N times, wasting hours of collection time and double-counting in aggregate reports.

**Solution:** Deduplicate at the discovery stage. Maintain a global `seen_video_ids: set` across all search terms within a run. When a VIDEO_ID is already seen, skip collection and log it as `DEDUP_SKIPPED` in the manifest. In reports, attribute deduplicated videos to all matching search terms but only count them once in aggregate statistics. Add a `DEDUP_STRATEGY` config key (`skip` default, `re-attribute` to link to all terms).

### 7.2 Output schema documentation [Usefulness: 88]

**Gap:** JSONL and CSV outputs are referenced throughout the PRD but no field names, types, or semantics are ever specified. Researchers cannot build downstream analyses without knowing the schema.

**Solution:** Define and publish canonical schemas for each output file:
- `comments.jsonl`: `VIDEO_ID`, `COMMENT_ID`, `PARENT_ID`, `AUTHOR`, `TEXT`, `LIKE_COUNT`, `REPLY_COUNT`, `PUBLISHED_AT`, `SORT_MODE`, `THREAD_DEPTH`
- `transcript_segments.jsonl`: `VIDEO_ID`, `SEGMENT_INDEX`, `START_S`, `END_S`, `TEXT`, `SPEAKER` (if available), `SOURCE` (manual/auto), `LANG`
- `transcript_chunks.jsonl`: `VIDEO_ID`, `CHUNK_INDEX`, `START_S`, `END_S`, `TEXT`, `SEGMENT_INDICES`, `OVERLAP_S`
- `topics.jsonl`: `VIDEO_ID`, `ASSET_TYPE`, `TOPIC_ID`, `LABEL`, `KEYWORDS`, `REPRESENTATIVE_TEXTS`, `SCORE`
- `sentiment.jsonl`: `VIDEO_ID`, `ASSET_TYPE`, `ITEM_ID`, `POLARITY`, `SCORE`, `TEXT_EXCERPT`
- `triples.jsonl`: `VIDEO_ID`, `ASSET_TYPE`, `SUBJECT`, `PREDICATE`, `OBJECT`, `CONFIDENCE`, `SOURCE_TEXT`

Add a `docs/schemas.md` file with these definitions. Validate outputs against schemas in a post-run check.

### 7.3 Per-video error recovery policy [Usefulness: 85]

**Gap:** If a video fails during collection (network error, region block, deleted video), the PRD does not define whether partial data is preserved, the video is skipped, or the entire run aborts.

**Solution:** Add `ON_VIDEO_FAILURE` config key with values:
- `skip` (default): log the failure to `failures/<VIDEO_ID>.json` with error details, preserve any partial data already written, mark checkpoint as `FAILED`, and continue to next video.
- `retry`: retry the failed video up to `MAX_RETRY_SCRAPE` times with backoff, then fall through to `skip` behavior.
- `abort`: halt the run (checkpoint preserved for resume).

In the manifest, record `FAILED_VIDEOS` with reasons. In reports, include a "Collection Failures" section listing each failed video with its error and any partial data available.

### 7.4 Dry-run / preview mode [Usefulness: 82]

**Gap:** A 500-video run can take hours. There is no way to preview what will be collected (how many videos matched, estimated comment counts, transcript availability) before committing to a full scrape.

**Solution:** Add a `ytca dry-run --config config.yml --terms "..."` CLI command that:
1. Runs the discovery stage only (resolve search terms, apply filters).
2. For each discovered video, fetch basic metadata (title, view count, comment count estimate, caption availability).
3. Output a summary: total videos found, estimated comments, transcript availability ratio, estimated run time.
4. Write the plan to `runs/<RUN_ID>/dry-run-plan.json` so the user can review before running `ytca run-all --plan runs/<RUN_ID>/dry-run-plan.json`.

### 7.5 Incremental / differential runs [Usefulness: 80]

**Gap:** Checkpointing supports resuming an interrupted run, but there is no concept of "run this again and only collect new content since last time." Repeated research on the same topic requires full re-collection.

**Solution:** Add `INCREMENTAL_MODE: bool = False` config key. When enabled:
1. Accept a `--baseline-run <RUN_ID>` CLI flag pointing to a previous run.
2. Load the baseline manifest to get the set of already-collected VIDEO_IDs and their latest comment timestamps.
3. During discovery, flag videos as `NEW` (not in baseline) or `UPDATE` (in baseline, collect only newer comments).
4. For `UPDATE` videos, use the Newest sort mode and stop scrolling when reaching comments older than the baseline's latest timestamp.
5. Merge incremental outputs into a new run directory with provenance links to the baseline.

### 7.6 Anti-bot detection and recovery [Usefulness: 78]

**Gap:** Rate-limit config knobs exist, but the PRD never defines what happens when YouTube actively blocks the scraper (HTTP 429, CAPTCHA pages, empty response bodies). `ROBUST_OVER_SPEED=True` is mentioned but its behavior is unspecified.

**Solution:** Define explicit detection and recovery:
- **Detection signals:** HTTP 429, response body containing CAPTCHA markers, consecutive empty comment lists when comments are expected, consent/age-gate interstitials.
- **Recovery behavior:** On detection, pause collection for `API_COOLDOWN_ON_ERROR_S` with exponential backoff (max 5 minutes). After 3 consecutive blocks on the same video, mark it `BLOCKED` and move on. After 5 blocks across any videos within a 10-minute window, pause the entire run for a configurable `GLOBAL_COOLDOWN_S` (default 300s) and notify the user via terminal.
- **`ROBUST_OVER_SPEED` definition:** When `True`, use longer jitter ranges (2x `API_JITTER_MS_*`), lower concurrency (cap `API_MAX_CONCURRENT_CALLS` at 1), and insert page-navigation delays between videos. When `False`, use configured values as-is.

### 7.7 Progress reporting / ETA [Usefulness: 72]

**Gap:** Rich and tqdm are listed as dependencies, but the PRD specifies no progress UX for runs that can last hours. Users have no visibility into how far along collection is or when it will finish.

**Solution:** Implement a three-level progress display:
1. **Overall run:** progress bar showing `completed_videos / total_videos` with estimated time remaining based on rolling average per-video time.
2. **Per-video:** status line showing current video title, current stage (collecting comments / transcript / enriching), and item counts.
3. **Log file:** structured JSON log entries per stage completion for headless/scripted monitoring.

Add `PROGRESS_MODE` config key: `rich` (default, interactive terminal), `plain` (simple line-by-line for CI/logs), `quiet` (errors only).

### 7.8 Programmatic Python API [Usefulness: 70]

**Gap:** Section 6 lists "CLI + Python API" as a deliverable, but only CLI commands are defined. There is no specified public API for users who want to call the tool from notebooks or scripts.

**Solution:** Define a minimal public API in `yt_content_analyzer`:
```python
from yt_content_analyzer import run_all, load_settings
from yt_content_analyzer.config import Settings

cfg = load_settings("config.yml")
run_all(cfg)  # already exists

# Add granular entry points:
from yt_content_analyzer.discovery import discover_videos
from yt_content_analyzer.collectors import collect_video
from yt_content_analyzer.enrich import enrich_run
from yt_content_analyzer.reporting import generate_reports

videos = discover_videos(cfg)
for v in videos:
    collect_video(v, cfg, run_dir)
enrich_run(run_dir, cfg)
generate_reports(run_dir, cfg)
```
Document these entry points in a `docs/python-api.md` guide with notebook examples.

### 7.9 Multi-language NLP support [Usefulness: 65]

**Gap:** When `AUTO_TRANSLATE=False` and collected content is not in `VIDEO_LANG_MAIN`, the enrichment pipeline (sentiment, topic modeling) will produce unreliable results since the NLP models assume English input.

**Solution:** Add `NLP_LANGUAGE: str = "auto"` config key. Behavior:
- `"auto"`: detect language per text item. Route English text through default models. For non-English text, either skip enrichment (log as `ENRICH_SKIPPED_LANG`) or use multilingual model variants if available.
- Explicit language code (e.g., `"en"`): only enrich items matching that language; skip others.
- In reports, include a "Language Coverage" section showing the distribution of detected languages and enrichment coverage per language.

### 7.10 Cross-run comparative analysis [Usefulness: 62]

**Gap:** Each run is fully isolated. Researchers studying topic evolution or sentiment trends over time have no built-in way to compare results across runs.

**Solution:** Add a `ytca compare --runs <RUN_ID_1> <RUN_ID_2> [...]` CLI command that:
1. Loads topic and sentiment outputs from each run.
2. Produces a comparison report: new/disappeared topics, sentiment polarity shifts, comment volume changes, top differentiating keywords.
3. Outputs to `reports/compare_<RUN_IDs>.md` and a structured `compare.jsonl`.

### 7.11 Output data validation [Usefulness: 58]

**Gap:** No post-run verification that output files are well-formed, row counts are consistent across JSONL/CSV pairs, or enrichment outputs cover all collected items.

**Solution:** Add a post-run validation stage (runs automatically unless `SKIP_VALIDATION=True`):
1. Parse every JSONL file and verify each line is valid JSON.
2. Compare row counts between `.jsonl` and `.csv` pairs.
3. Verify enrichment coverage: every `VIDEO_ID` in comments/transcripts should appear in topics/sentiment outputs (or be logged as intentionally skipped).
4. Write a `validation_summary.json` to the run directory with pass/fail per check.
5. Print a summary to terminal. Non-fatal: validation failures produce warnings, not run aborts.
