# C1–C4 follow-up fixes · Claude Code cloud run · 2026-11-26

Data kind: **synthetic inputs only**. No real recordings, frames, OCR, databases, exports or
private reports were available or used. Nothing here validates labels on real content.

## Scope and provenance

| Item | Value |
|---|---|
| Review | [PR-003](PR-003.md) (PR #4), findings C1–C4 |
| Base | `codex/pr3-independent-review` @ `afff986` (main `48e44ee` + review) |
| Branch | `claude/c1-c4-review-followups`; PR targets `codex/pr3-independent-review` |
| Environment | Linux cloud container, Python 3.12.3, FFmpeg 6.1.1, Node (syntax check), Playwright Chromium (UI smoke) |
| External providers | Disabled; no frames sent anywhere |
| Out of scope | R5–R9; the primary-analysis-membership decision raised in PR-003 |

Order of work as requested: C1 and C2 first, then C3 and C4.

## Commands and results

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -q` (before, at `afff986`) | 0 | 67 passed, 0 skipped |
| `.venv/bin/python -m scripts.research.pr3_review` (before) | 0 | all four C1–C4 defects reproduced (table below) |
| `.venv/bin/python -m pytest -rs` (after) | 0 | **98 passed, 0 skipped** (67 existing + 31 new in `tests/test_review_followups.py`) |
| `.venv/bin/python -m scripts.research.pr3_review` (after) | 0 | all four probes show the corrected behavior |
| `.venv/bin/python -m scripts.research.pr1_review` (after) | 0 | runs; R1/R2/R4 stay fixed; R5/R6/R7 still reproduce (out of scope) |
| `node --check app/web/app.js` | 0 | syntax OK |
| Playwright smoke against `python -m app.cli serve` (temp data dir, seeded demo) | 0 | overview, session, interventions pages render; no page or console errors |

One existing test changed deliberately: `test_legacy_exp001_profile_is_upgraded_once` now
simulates the complete Sprint 1 topic list, because only a fully unedited legacy profile is
upgraded (C1).

## Review probe, before → after

| Probe (synthetic) | Before | After |
|---|---|---|
| C1 edited legacy profile after restart: version / custom topic / adjacent edit / description / weight | 2→3 / lost / lost / lost / 0.20 | 2→2 / kept / kept / kept / 0.35 |
| C2 size-deviation sample later gets needs_review + conflict: readiness / `POST /interventions` without override / strategist | true / 200 / `review_data` | false / 409 / `collect_baseline` |
| C3 merge → mock classify: absorbed ID in evidence / boundary history present | false / false | true / true (plus structured `boundary_history`) |
| C4 two accepted samples of 50 ads: readiness / strategist / suggestions | true / `intervene` / 3 | false / `collect_baseline` / 0 |

## Resolved findings

| Finding | Fix | Regression tests |
|---|---|---|
| C1 · P1 · startup overwrites profile edits | Upgrade only when all topics equal the shipped Sprint 1 list ([D-022](../../docs/DECISIONS.md)) | untouched legacy upgraded once and idempotent; adjacent edit, added topic, weight, description, context keywords survive two restarts; observations never relabelled |
| C2 · P1 · old deviation waives new problems | Acceptance stores a data revision and deviation scope; shared `intervention_gate` for strategist and API ([D-023](../../docs/DECISIONS.md)) | unchanged short sample still counts; needs_review, conflict, relabel, add, delete after ordinary and deviation acceptance (10 cases); boundary edit and reclassification; new scope needs new note; API and strategist agree, override recorded; open review item outside T0 blocks both |
| C3 · P2 · classification erases merge history | `boundary_history` column; classification keeps boundary, human and conflict notes ([D-024](../../docs/DECISIONS.md)) | merge → classify ×2 → human correction → include-reviewed classify → JSON and CSV export; chained merges; untouched rows have empty history |
| C4 · P2 · zero-eligible baseline unlocks | Readiness needs ≥1 eligible exposure in counted samples ([D-025](../../docs/DECISIONS.md)) | ads-only, followed-only, search-only blocked; mixed valid baseline unlocks; override still recorded |
| Migration | Additive schema v3 | v2-shaped database opens, rows preserved, `boundary_history = []`, v2 acceptances need renewal |

## Behavior changes to know about

- After updating, **every previously accepted T0 sample must be accepted again** (no stored
  revision). This is deliberate: earlier acceptances cannot prove which data they covered.
- Any edit to an accepted sample, including a harmless label correction, needs re-acceptance.
- Before the first intervention, an open review item in any session (not only T0) now blocks
  `POST /interventions` without an override, matching what the strategist already showed.

## Limitations

- Synthetic inputs only; no real-data validation. BASELINE-001 stays provisional.
- The revision covers review-relevant fields, not captions, hashtags, notes or frames;
  editing a caption alone does not revoke acceptance.
- Edited legacy profiles keep their ambiguous DIRECT keywords in storage; protection relies on
  mock v2 treating those terms as context. A richer classifier must apply the same rule.
- Pooled baseline metrics still include all T0 sessions (D-021); the analysis-membership
  decision from PR-003 is open.
- UI checked in headless Chromium only.
