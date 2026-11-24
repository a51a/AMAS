# CLAUDE.md

Guidance for AI coding agents working in this repository.

## Project
AMAS (Algorithm Management as a Service): local-first lab for measuring and steering
recommendation feeds. Current stage: Sprint 1 local MVP. Read `docs/ARCHITECTURE.md` and
`docs/DECISIONS.md` before larger changes; add a new `D-xxx` entry for every non-trivial decision.

## Commands
- Setup: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'`
- Tests: `pytest` (pipeline tests need `ffmpeg`; they are skipped without it)
- Run: `python -m app.cli serve` → http://127.0.0.1:8000
- Demo data: `python -m app.cli seed-demo`

## Hard rules
- Compliance (docs/PLATFORM_COMPLIANCE.md) is non-negotiable: no Instagram login automation, no
  credential/cookie/token handling, no scraping, no automated playback or engagement, no rate-limit
  or bot-detection bypass. New platform capabilities need a compliance review first.
- Never fabricate captions, creators or labels. Missing evidence → `unknown` / null.
- Keep topic classification separate from eligibility (`recommendation_status`, `is_ad`).
- Unknown classifications stay in the primary-metric denominator.
- Demo data must stay flagged `is_demo` and labelled SIMULATED in UI and exports.
- Frames may go to an external provider only through `assert_external_allowed`.
- Never commit `.env`, `data/`, recordings or personal datasets.

## Style
- Python 3.12, FastAPI, sqlite3 (no ORM), Pydantic v2. Engines (evaluator, strategist) are pure
  functions over dicts; keep DB access in `app/storage/repository.py`.
- Frontend is vanilla JS in `app/web/`; no build step, no frameworks.
- Code, comments and docs in English.
