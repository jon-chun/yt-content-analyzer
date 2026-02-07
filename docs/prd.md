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
