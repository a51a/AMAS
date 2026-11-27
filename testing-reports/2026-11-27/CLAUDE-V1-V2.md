# V1 and V2 fixes, Claude Code cloud run

Date: 2026-11-27. Implementer: Claude Code (cloud). Public-safe; synthetic inputs only.
Implementation report, not independent verification. Findings come from Codex's PR #7 review
(`testing-reports/2026-11-27/PR-007.md` on branch `codex/pr7-independent-review`, not yet in main).

## Provenance

| Item | Value |
|---|---|
| Base | `main` at `e87bfb8da2f76a6bc21c9517fb7a05b6c5630423` |
| Implementation commit | `e640cfc` (branch `claude/pr7-v1-v2-fixes`); this report is a docs-only commit on top |
| Review probe used | `scripts/research/pr7_review.py` from `codex/pr7-independent-review` at `67200f9`, run from an untracked copy; not committed here |
| Working tree at verification | Clean apart from that untracked probe copy |
| Environment | Linux 6.18 cloud container, Python 3.12.3, FFmpeg 6.1.1, Node 22.23.5 |

## Reproduction before the fix (main `e87bfb8`)

`pr7_review` printed: V1 `after_confidence: 0.3`, `export_confidence: 0.3`, explicit same-value
PATCH 400; V2 `hours_after_intervention: 1.08`, `has_timezone_warning: false`,
`ttf_has_timezone_provenance: false`. Both findings reproduced as described.

## Fixes (D-029)

- **V1:** `{confirm: true}` on an UNKNOWN label now sets the exposed `confidence` to null, the same
  as a correction to UNKNOWN. `machine_label_json.confidence` is kept (copied there first if an
  older row lacks it). Edits that neither change the label nor confirm it keep omitted-field
  semantics. Confirming a known label keeps its confidence.
- **V2:** `time_to_first_target` now reports `exposure_time_used`, `exposure_time_source`
  (`observed_at`, or session capture time plus video offset), `exposure_timezone_assumed_utc`,
  `intervention_timezone_assumed_utc` and `time_verified`. If either time relies on a legacy naive
  value read as UTC, a warning says so. The UI marks such a result as an unverified time.
  Stored values are not rewritten and no timezone is inferred.

## Verification after the fix

| Command | Exit | Observed result |
|---|---|---|
| `.venv/bin/python -m pytest -ra` | 0 | **141 passed**, 0 skipped, 1 Starlette/httpx deprecation warning (132 + 9 new in `tests/test_v1_v2.py`) |
| `python -m scripts.research.pr7_review` | 0 | V1: `after_confidence: null`, `export_confidence: null`, `machine_confidence: 0.3`, explicit PATCH still 400. V2: 1.08 h, `has_timezone_warning: true`, `ttf_has_timezone_provenance: true` |
| `python -m scripts.research.pr1_review` | 0 | Unchanged from the R5/R6 report; R7 still reproduces |
| `python -m scripts.research.pr3_review` | 0 | C1–C4 probes remain corrected |
| `python -m scripts.research.pr5_review` | 0 | N1: banner, checkbox and reason rendered; 409 without override |
| `node --check app/web/app.js`, `git diff --check` | 0 | Clean |

New regression cases: local classifier → Confirm → API, JSON and CSV export; known topic changed
to UNKNOWN; non-null confidence on UNKNOWN rejected; unrelated edit keeps confidence; confirming a
known label keeps it; machine value saved when it was missing; an isolated naive `observed_at`
with valid session and intervention times; an all-aware case with no assumption warning; a naive
intervention anchor; the session-time fallback with and without a naive value.

## Limitations and open items

- Cloud tests only, on Python 3.12.3. No real database or recording was touched.
- The UI change (an "unverified time" tag on time-to-first-target) is covered by `node --check`
  only, not by a render test.
- Taxonomy, denominator, sampling protocol and the `eval-v2` formula are unchanged.
- **R7, R8, R9 remain the next tasks.** Nothing was merged; no intervention was started.
