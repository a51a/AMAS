# AMAS: Algorithm Management as a Service

> Your attention. Your algorithms. Your rules.

AMAS is an experimental control layer over existing recommendation systems. Sprint 1 is a
**local-first research lab**: you record your own Instagram Reels feed, AMAS segments the
recording into individual Reels, helps you classify them, and measures how the
recommendation mix changes after documented interventions.

Closed loop: **Observe → Compare → Strategize → Act → Measure → Repeat.**

Sprint 1 has **no platform integration**. AMAS never logs in to Instagram, never stores
credentials, cookies or tokens, never scrapes and never automates views, likes or follows.
See [docs/PLATFORM_COMPLIANCE.md](docs/PLATFORM_COMPLIANCE.md).

## Quick start (macOS)

```bash
brew install python@3.12 ffmpeg          # tesseract is optional: brew install tesseract
git clone https://github.com/a51a/AMAS.git && cd AMAS
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'                   # add ,llm for the optional vision LLM classifier
cp .env.example .env

python -m app.cli init                    # creates data/amas.sqlite and EXP-001
python -m app.cli seed-demo               # optional: SIMULATED DEMO-001 experiment
python -m app.cli serve                   # http://127.0.0.1:8000
```

Run tests: `pytest`

No API key is needed. The default classifier is a local keyword-based mock; manual labelling
always works.

## Import your first real baseline recording (EXP-001, T0)

1. Open Instagram in your desktop browser, go to **Reels**. Do not search, do not open profiles.
2. Start a screen recording (`⌘ Shift 5` → *Record Selected Portion*, select the browser window).
3. Scroll through **50 Reels** as you normally would. Stop the recording.
4. In AMAS: **EXP-001 → Import recording**, checkpoint `T0`, label `Baseline A`, choose the
   `.mov` file (or paste its path, faster for big files). AMAS copies it to `data/recordings/`,
   extracts frames with FFmpeg and proposes Reel boundaries.
5. On the review screen:
   - check the boundaries: **Merge with next**, **Split…** or **Manual boundaries…**;
   - click **Mark undetermined → recommended** (only if everything came from the Reels feed);
   - label each Reel `direct / adjacent / unrelated / unknown`, mark ads and followed accounts;
   - optional: **Classify (local mock)** or, after enabling it, **Classify with vision LLM…**.
6. Repeat for `Baseline B` (second T0 session). The experiment page then shows the baseline share.

CLI alternative: `python -m app.cli import ~/Movies/rec.mov --checkpoint T0 --label "Baseline A"`.

No recording? Create a **manual session** and log each Reel with the keys `D`, `A`, `U`, `?`.

Full protocol: [experiments/EXP-001-biathlon/protocol.md](experiments/EXP-001-biathlon/protocol.md).

## Optional: vision LLM classifier

Frames leave your computer, so this is off by default and gated twice:

1. `.env`: `AMAS_ALLOW_EXTERNAL_PROVIDERS=true` and `ANTHROPIC_API_KEY=...`; `pip install -e '.[llm]'`.
2. In the UI, accept the per-experiment privacy notice on first use.

The provider interface (`app/observer/classifiers/vision_llm.py`) is pluggable.

## Data

Everything lives in `data/` (git-ignored): SQLite database, recordings, frames, exports.
Delete a recording (keeps labels) or a whole session (and all derived data) from the review
screen. Export CSV/JSON from the experiment page or `python -m app.cli export --format csv`.

Demo data (`DEMO-001`) is a separate experiment flagged `is_demo`, shown with a
**SIMULATED** banner and labelled in exports. It is never a research finding.

## Repository layout

```
app/
  models/        Pydantic schemas and enums (taxonomy, eligibility, review status)
  storage/       SQLite schema + repository
  taste_engine/  interest profiles (versioned), EXP-001 loader
  observer/      FFmpeg import, frame extraction, segmentation, classifiers, pipeline
  evaluator/     metrics (pure functions) and statistics
  strategist/    deterministic rules-based planner
  actuator/      Manual / Mock / FutureAuthorized actuators
  adapters/      InstagramManualAdapter, MockPlatformAdapter
  api/           FastAPI routes
  web/           Control Center (vanilla HTML/CSS/JS, no build step)
  cli.py, main.py, demo.py, services.py
experiments/EXP-001-biathlon/   protocol.md, config.json
docs/            PRODUCT, ARCHITECTURE, PLATFORM_COMPLIANCE, DECISIONS
tests/           unit, pipeline (synthetic FFmpeg video) and API tests
```

See [ROADMAP.md](ROADMAP.md) for what comes next.
