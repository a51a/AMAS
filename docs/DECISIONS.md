# Decision log

## D-001 · Start from scratch
The GitHub repository was empty and no AMAS Lab v0.1 HTML/JS files were available, so nothing was
ported. Concepts carried over from the handoff description: manual classification, target
profiles, before/after comparison, JSON import/export.

## D-002 · Stack: FastAPI + SQLite + vanilla JS
As suggested in the handoff. No React, PostgreSQL or Docker: a single local process is enough and
keeps setup to `pip install`. The UI is static files served by FastAPI, no build step.

## D-003 · sqlite3 without an ORM
Six tables, simple queries. Plain SQL in one repository module is easier to read and debug than an
ORM layer. One shared connection guarded by an `RLock` because FastAPI runs sync endpoints in a
thread pool (a smoke test found concurrent frame requests failing without it).

## D-004 · Eligibility model
`recommendation_status` ∈ {recommended, followed_account, search_result, undetermined} plus a
nullable `is_ad`. New segments start as `undetermined`, because AMAS cannot know where a Reel came
from. The user confirms per session ("Mark undetermined → recommended") or per Reel. Primary
metric uses `recommended` and not ad; `undetermined` is excluded, flagged, and reported in the
all-exposure metric.

## D-005 · Statistics
Wilson score interval for proportions; Newcombe hybrid score interval for the change vs baseline.
Both assume independence, which feed data violates; the UI and exports carry this caveat.
Baseline = pooled T0 sessions. Persistence = lift at T3/T4/T5 as a fraction of the T2 lift.
Time to first target = first eligible direct item in sessions after the first completed
intervention; wall-clock time is bounded by sampling times.

## D-006 · Segmentation heuristic
Frames at 1 fps; transitions detected as the mean absolute difference between 16×16 grayscale
thumbnails of the centred 40% of the frame (desktop Reels sit in a centre column; side UI is static).
Adaptive threshold `max(28, median + 4·MAD)`, multi-frame scroll animations collapse to one
boundary, minimum segment 3 s. It is a suggestion; merge/split/manual boundaries are first-class.
Tuning on real recordings is the first task of Sprint 2. No ML model, no OpenCV dependency.

## D-007 · Content fingerprint
64-bit average hash of the representative frame (`ahash:<hex>`), near-duplicates within Hamming
distance 6 count as one unique item. Manual entries may use any exact-match fingerprint.

## D-008 · Classifiers
`MockClassifier` matches profile keywords in available text only (caption, hashtags, optional local
OCR via `tesseract`) and returns `unknown` when there is no text: it never guesses from pixels.
`VisionLLMClassifier` wraps a pluggable `VisionProvider`; Sprint 1 ships `AnthropicVisionProvider`
using the official `anthropic` SDK with structured output (`messages.parse`), default model
`claude-opus-5-5` (configurable via `AMAS_ANTHROPIC_MODEL`). A refusal or empty output becomes
`unknown`. Server-side model fallbacks are not enabled. The prompt forbids inventing captions,
handles or topics.

## D-009 · Review workflow
Confidence ≥ 0.7 and not unknown → `auto_accepted`, else `needs_review`. Human changes →
`corrected` (machine label kept in `machine_label_json`); confirmation → `confirmed`. Re-running a
classifier never overwrites human-reviewed rows. Re-segmenting resets labels for that session.

## D-010 · Demo data separation
Demo lives in its own experiment (`DEMO-001`, platform `mock`, `is_demo=1`) with its own profile;
every row inherits `is_demo`. SIMULATED banner on every demo screen and a `data_label` in exports.
`MockActuator` is allowed only on demo experiments.

## D-011 · Synchronous import
Import, frame extraction and segmentation run inside the request. Fine for 10-15 minute recordings
at 1 fps; background jobs are on the roadmap if real recordings prove slow.

## D-012 · Python 3.12 target
`pyproject.toml` requires ≥3.12 and tests ran on 3.12. Uses `enum.StrEnum`.
