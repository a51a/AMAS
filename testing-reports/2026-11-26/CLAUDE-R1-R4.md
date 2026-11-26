# R1–R4 measurement-integrity fixes · Claude Code cloud run · 2026-11-26

Data kind: **synthetic inputs only**. No real recordings, frames, OCR, exports or private
reports were available or used. Nothing here validates accuracy on real Instagram content.

## Scope and provenance

| Item | Value |
|---|---|
| Base | `codex/cto-review-exp001` @ `e170928` |
| Branch | `claude/r1-r4-measurement-integrity` (PR targets `codex/cto-review-exp001`, not main) |
| Environment | Linux cloud container, Python 3.12.3, FFmpeg 6.1.1, Node (syntax check only), Playwright Chromium (UI smoke) |
| External providers | Disabled; no frames sent anywhere; experiment consent not enabled |
| Out of scope | R5–R9 from [PR-001](PR-001.md) remain open |

## Commands and results

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -q` (before changes, at `e170928`) | 0 | 26 passed, 0 skipped |
| `.venv/bin/python -m scripts.research.pr1_review` (before) | 0 | reproduced R1–R4 (table below) |
| `.venv/bin/python -m pytest -rs` (after) | 0 | **67 passed, 0 skipped** (26 existing + 41 new in `tests/test_measurement_integrity.py`) |
| `.venv/bin/python -m scripts.research.pr1_review` (after) | 0 | R1, R2, R4 probes resolved; R3 see note |
| `node --check app/web/app.js` | 0 | syntax OK |
| Playwright smoke against `python -m app.cli serve` with a temp data dir | 0 | overview, session, intervention log and demo pages render; accept flow and 409 gate work; only console error is the expected 409 |

Two existing tests were updated deliberately: `test_strategist_flow` and
`test_api_manual_baseline_compare_and_export` now accept the T0 samples before expecting
`intervene` / planning an intervention (R4). `test_mock_classifier_never_fabricates` now
expects UNKNOWN instead of UNRELATED for "Pasta carbonara recipe" (R2: missing keywords do
not identify other content).

## Review probe, before → after

| Probe (synthetic) | Before | After |
|---|---|---|
| "Police pursuit on the highway" | direct 0.9 | unknown 0.3 (context-only) |
| "Mass start in cycling" | direct 0.9 | unknown 0.3 (context-only) |
| "Follow" | unrelated 0.5 | unknown 0.0 (interface-only) |
| Merge first two of three confirmed Reels: third Reel's ID survives | false | true (labels, eligibility, ad, review status unchanged) |
| Followed marker after "recommended" | status `recommended`, silently eligible | status `recommended` kept, `eligibility_conflict = true`, excluded from primary metric |
| Two single-Reel T0 sessions → strategist | `intervene` | `collect_baseline` |

Note on R3: the probe prints only `recommendation_status`, which stays `recommended` by
design (explicit statuses are not overwritten). The conflict flag was checked separately on
the same synthetic sequence and in `test_bulk_recommended_then_classify`.

Probes unrelated to R1–R4 are unchanged, as expected: explicit null cannot clear `is_ad` and
UNKNOWN corrections get confidence 1.0 (R5), naive capture timestamps raise `TypeError`
(R6), deleted sessions remain in stored snapshots (R7).

## Resolved findings

| Finding | Fix | Regression tests |
|---|---|---|
| R1 · boundary edits wipe the session | Reconciliation plan applied in one transaction ([D-018](../../docs/DECISIONS.md)): unchanged intervals keep everything, changed intervals keep ID but need review, new parts start pending | merge keeps third Reel; split keeps others; invalid split changes nothing; mid-transaction failure rolls back; re-applying same boundaries is lossless; manual entries survive |
| R2 · ambiguous keywords fabricate DIRECT | Explicit `keywords` vs `context_keywords`; mock v2; legacy EXP-001 profile upgraded once as a new version ([D-019](../../docs/DECISIONS.md)) | 5 ambiguous phrases not DIRECT; 4 interface-only strings UNKNOWN; explicit biathlon (EN/RU/hashtag/IBU World Cup) DIRECT; adjacent winter sports still ADJACENT; legacy keywords context-only; upgrade once; user-edited profile untouched |
| R3 · followed marker ignored after bulk | `followed_signal`, `eligibility_source`, `eligibility_conflict`; conflicts excluded from the primary metric and reported; human per-Reel ruling resolves ([D-020](../../docs/DECISIONS.md)) | classify→bulk, bulk→classify, human ruling not overridden and later resolves, API bulk response |
| R4 · undersized baseline unlocks T1 | `baseline_readiness`, explicit acceptance with recorded deviations, strategist and API gate with recorded override ([D-021](../../docs/DECISIONS.md)) | empty, 2×1, auto_accepted, needs_review, undetermined, conflict do not unlock; accepted 2×50 does; unknown ad allowed but reported; edit after acceptance revokes; deviation recorded; API 409/400/override; accept endpoint |
| Migration | Additive schema v2 ([D-017](../../docs/DECISIONS.md)) | v1-shaped database opens, rows preserved, new columns defaulted, idempotent re-open |

## Limitations

- Synthetic inputs only. No real-data validation; BASELINE-001 remains provisional and was
  not touched. Real T0 samples must still be reviewed and explicitly accepted locally.
- Boundary matching uses a ±1 ms tolerance on start/end times. A boundary nudged by a frame
  counts as a changed interval (sent to review), which is conservative.
- After a boundary change, re-running a classifier can move a `needs_review` row to
  `auto_accepted`; readiness still requires human review, so the baseline gate holds.
- The mock classifier now leaves most non-target text UNKNOWN; UNRELATED needs a human or
  a richer classifier. Expect higher unknown rates from mock pre-labelling.
- Rows already labelled by the Sprint 1 mock (e.g. DIRECT from "pursuit") are not relabelled
  automatically; re-run the classifier or review them.
- The UI changes were smoke-tested in headless Chromium only, not on macOS Safari/Chrome.
