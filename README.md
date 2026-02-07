# yt-content-analyzer

Scrape-first YouTube **comments + transcripts** collection and analysis for **moderate academic research scale**.

This project is designed to:
- Resolve **search terms → top-N videos** (scrape-first; optional rare API fallback)
- Collect:
  - **Comments** in both *Top* (themes) and *Newest* (timeline) modes
  - **Transcripts** (manual captions preferred; **auto captions allowed** if manual unavailable)
- Enrich text via configurable local/remote services:
  - **Translation** (optional; `AUTO_TRANSLATE`)
  - **Embeddings** for topic modeling (local/remote; with sampling fallback)
  - **Sentiment** (polarity default; extensible to emotions/ABSA)
  - **Relation triples** → `triples.jsonl`
- Produce:
  - **Machine-friendly outputs**: JSONL + CSV
  - **Human-readable reports**: Markdown in `reports/`
- Support **interrupt/resume** with checkpointing.

> **Important:** This is intended for research-scale analysis, **not** massive dataset scraping/training.

---

## Installation

### From PyPI (once published)
```bash
pip install yt-content-analyzer[scrape,reports,nlp]
playwright install
```

### From source (development)
```bash
git clone https://github.com/<org>/yt-content-analyzer
cd yt-content-analyzer
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,scrape,reports,nlp]"
playwright install
```

---

## Setup

### 1) Configuration file
```bash
cp config.example.yaml config.yaml
```

Run preflight:
```bash
ytca preflight --config config.yaml
```

### 2) Secrets via environment (.env)
```bash
cp .env.example .env
# edit .env
```

**Do not commit `.env`.**

---

## Running

### End-to-end job
```bash
ytca run-all --config config.yaml --terms "AI agents 2026" --terms "robotics policy"
```

### Outputs
```
runs/<RUN_ID>/
  manifest.json
  logs/run.log
  discovery/
  comments/
  transcripts/
  enrich/
  failures/
  reports/
  state/checkpoint.json
```

---

## Publishing to PyPI (maintainers)
```bash
python -m build
twine check dist/*
twine upload dist/*
```

---

## License
MIT. See `LICENSE`.
