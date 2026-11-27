# R5, R6 and N1 fixes, Claude Code cloud run

Date: 2026-11-27. Implementer: Claude Code (cloud). Public-safe report; synthetic inputs only.
This is an implementation report, not independent verification. Codex review is requested.

## Provenance

| Item | Value |
|---|---|
| Base branch | `codex/pr5-independent-review` (PR #6 was open, not merged, when work started) |
| Base commit | `d42c3221f79be16073cfc3de755c69191f41ec70` |
| Implementation commit | `87452a5` (branch `claude/project-thread-j3ftn6`); this report is a docs-only commit on top |
| Working tree at verification | Clean (0 changed files) |
| Environment | Linux 6.18 cloud container, Python 3.12.3, FFmpeg 6.1.1, Node 22.23.5 |
| Data | Synthetic fixtures and temporary databases only. No real recordings, frames, observations or `data/` |

## Verification results

| Command | Exit | Observed result |
|---|---|---|
| `.venv/bin/python -m pytest -ra` | 0 | **132 passed**, 0 skipped, 1 Starlette/httpx deprecation warning (98 before + 34 new) |
| `.venv/bin/python -m scripts.research.pr1_review` | 0 | `explicit_null_cannot_clear_ad: null` (now cleared), `unknown_correction_confidence: null`; naive entry rejected; legacy naive row summarised with `timezone_assumed_utc: true`, `capture_time_verified: false`. R7 still reproduces (`deleted_session_retained_in_experiment_snapshot: true`) |
| `.venv/bin/python -m scripts.research.pr3_review` | 0 | C1-C4 probes unchanged: corrected behaviour |
| `.venv/bin/python -m scripts.research.pr5_review` | 0 | ready=true, `review_data`, 409 without override, 200 with override; UI now shows banner, checkbox and reason field |
| `node --check app/web/app.js` | 0 | Syntax passes |
| `git diff --check` | 0 | Clean |

Probe exit 0 means the probe ran. The table quotes the behaviour it printed.

**Probe change to review:** `scripts/research/pr1_review.py` crashed with exit 1 before
printing anything, because its R6 step passes a naive `captured_at` that `create_session`
now refuses. I made one minimal change: it records the refusal under `naive_capture_entry`,
then writes the naive value directly with `update_session` to keep testing the legacy-row path.
No other probe line changed. Please check that this adaptation is acceptable.

## R5 · Corrections and confidence (D-026)

- PATCH passes only the fields the client sent (`exclude_unset`). An omitted field is unchanged.
  An explicit `null` clears `topic_label`, `is_ad`, `caption_text`, `creator_handle` or `confidence`.
  `null` on `target_match`, `recommendation_status`, `hashtags` or `notes` returns 422 and changes nothing.
- `is_ad: null` returns the Reel to "not identified". It is still not a verified non-ad.
- A correction no longer sets `confidence = 1.0`. It keeps the reviewer's explicit value or null.
  UNKNOWN never carries a confidence (400 if one is sent). Review status (`corrected`/`confirmed`)
  is kept as human provenance. The machine confidence stays in `machine_label_json`.
- Manual entries no longer get an automatic 1.0.
- Tests use the exact Save payload the session screen sends: unchanged form, "not identified" ad
  with empty caption, change to UNKNOWN. JSON and CSV exports round-trip the cleared values as
  null or empty.

Confidence does not feed any metric. Taxonomy, eligibility and denominator are unchanged.

## R6 · Capture time and time zones (D-027)

- `captured_at`, `observed_at`, `completed_at` (API), the demo actuator and CLI `--captured-at`
  require ISO 8601 with an offset. Naive and malformed values are rejected (422 / 400 /
  argparse error, before a session is created). Accepted values are stored in UTC.
- Schema v4 adds `captured_at_source`, `imported_at` and `recording_created_at` to sessions,
  additively. Existing values are not rewritten.
- Capture time is chosen in this order: the owner's explicit value, then recording metadata
  (`com.apple.quicktime.creationdate`, then `creation_time`; epoch, implausible or naive tags are
  ignored), then the session creation time, flagged `session_created`. Import time is stored separately
  and never used as capture time. A legacy (pre-v4) session keeps its value on re-import.
- Legacy naive values are read as UTC so summary and strategist no longer crash. A warning lists
  them. Legacy rows report `captured_at_source: not_recorded`. Chronology sorts by instant, not string.
- Every post-intervention session reports `hours_after_intervention` and `capture_time_verified`.
  T3-T5 persistence adds `nominal_hours`, `actual_hours_after_intervention`, `hours_from_nominal`,
  `captured_before_intervention` and the source. Warnings flag unknown, negative or unverified
  elapsed time. The UI shows actual hours next to the planned horizon. No timing tolerance was
  added, so whether a 30 h sample counts as "24 h persistence" remains the founder's protocol call.
- Synthetic MP4s with and without `creation_time` cover: an old recording imported today,
  missing metadata, an explicit time beating metadata, the CLI option, and v3→v4 migration with a
  naive legacy value.

## N1 · Intervention gate in the UI (D-028)

- `GET /plan` returns `intervention_gate`, the same function the intervention API enforces.
- The intervention screen lists those problems, including open review items outside T0. Create
  (and strategist "Plan this") stays disabled until the exception box is ticked and a non-empty
  reason is entered. Clicking without both sends no request.
- The API gate is unchanged: 409 without override, 400 with an empty reason.
- Tests cover three states (baseline unready, baseline ready with an ADHOC pending item, fully
  ready) through the API and through Node rendering of the real `viewInterventions` code with real
  API responses.

## Limitations

- No full-browser smoke test. The UI check renders one function with a minimal DOM stub in Node.
- Recording metadata was tested on FFmpeg-made MP4s only, not on real macOS QuickTime screen
  recordings. Whether `creationdate` marks the start or the end of a recording is not verified.
  The value is labelled as provenance, not as exact exposure time.
- Python 3.12.3 on Linux; the founder's Mac runs Python 3.14.6. No real database was migrated here.
- `eval-v2` is kept: the formula is unchanged. Results with mixed offsets can now order sessions
  differently from before, because they are sorted by actual time.

## Still open

- **R7** (experiment snapshots keep deleted sessions): still reproduces in `pr1_review`. Not touched.
- **R8** (classification profile version provenance): not touched.
- **R9** (human boundary reference, on-device): not touched.
- BASELINE-001 stays provisional. No experimental intervention was started. Nothing was merged.
