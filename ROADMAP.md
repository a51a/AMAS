# Roadmap

## Shared status · 2026-11-26

- Claude Code works in the cloud from GitHub; Codex keeps private research in local lab/AMAS.
  [Testing report index](testing-reports/README.md) is the shared entry point.
- PR #1 was independently reviewed at `b086496` / merged tree `e4bca44`. Original findings
  and acceptance criteria remain in [PR-001](testing-reports/2026-11-26/PR-001.md).
- PRs #2 (handoff) and #3 (R1–R4 implementation) are merged. Codex independently tested
  main `48e44ee`, including fix head `71d1149`: **67 passed, 0 skipped** on macOS,
  Python 3.14.6 with FFmpeg. This is not evidence of Instagram classifier accuracy.
- Latest independent review and cloud task: [PR-003](testing-reports/2026-11-26/PR-003.md),
  branch `codex/pr3-independent-review`. C1/C2 are P1 follow-ups (profile edits lost on
  startup; stale deviations bypass new readiness problems); C3/C4 are P2 (merge history
  lost on classification; zero eligible baseline unlocks intervention). R5–R9 remain open.
- BASELINE-001 / EXP-001 / T0 remains provisional. Source/export consistency checks passed;
  startup migration was tested on a separate local database copy with observation data
  preserved. Original DB and recording were not migrated or altered in this review.
- No human baseline validation, intervention or post-intervention result is claimed.
  All baseline images stay on-device; detailed evidence/backups remain Git-ignored.
- No product code was changed in this follow-up review. New fixes require an implementation
  PR and founder approval for merge; historical handoff/report documents remain intact.

## Sprint 1 (this release): local MVP
Observer (recording import, frames, segmentation, mock + pluggable vision classifier, manual review),
Taste Engine (versioned profiles, EXP-001), Evaluation Engine, rules-based Strategist,
Manual/Mock actuators, Instagram manual adapter, Control Center, CSV/JSON export.

## Next
1. **Close follow-up measurement findings**: Claude fixes C1/C2 first, then C3/C4 from
   [PR-003](testing-reports/2026-11-26/PR-003.md), with regression tests and an independent
   recheck. Do not treat merged code or a green suite as experiment readiness.
2. **Make real corrections/imports reliable**: R5/R6 (nullable fields, confidence, capture
   time and timezone validation), then R7/R8 (snapshot deletion and profile-version provenance).
3. **Accept a defensible baseline before T1**: establish the human boundary reference (R9),
   review labels/eligibility locally and complete the two 50-exposure T0 samples. Decide
   primary analysis membership before pooling pilot/provisional and accepted samples;
   current metrics pool all T0 sessions. Keep real data provisional until verified.
4. **Faster labelling**: keyboard-driven review queue, bulk label, label propagation across
   near-duplicate fingerprints, inter-rater check (two labelling passes on a subset).
5. **Classifier evaluation**: hold-out set of human labels, confusion matrix per classifier version,
   cost per session for the vision LLM.
6. **EXP-002 design**: Instagram native preference controls vs. behavioural intervention
   (separate account or separate time window to avoid confounding).
7. **Screenshot import** (capture method already modelled).
8. **Background jobs** for long recordings (currently synchronous).

## Later (not started; require product and compliance decisions)
- Additional platforms: YouTube, TikTok, LinkedIn, Facebook (manual adapters first).
- Authorized integrations via official APIs only, after a platform permissions review.
- Adaptive LLM strategist.
- Algorithm Health (drift monitoring), Taste Passport, Copy Taste, Blend, Fork, Marketplace.
