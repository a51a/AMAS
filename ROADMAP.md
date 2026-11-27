# Roadmap

## Shared status · 2026-11-27

- Claude Code works in the cloud from GitHub; Codex keeps private research in local lab/AMAS.
  [Testing report index](testing-reports/README.md) is the shared entry point.
- PRs #1–#5 are merged. Codex independently verified main `1f12f98`, including PR #5 fix
  head `06193ed`: **98 passed, 0 skipped** on macOS / Python 3.14.6 with FFmpeg.
- **C1–C4 verified** in original reproductions and the regression suite. R1/R2/R4 original
  symptoms remain fixed. Latest evidence/task: [PR-005](testing-reports/2026-11-27/PR-005.md),
  branch `codex/pr5-independent-review`. One P2 UI/API parity follow-up N1 remains;
  it does not bypass backend protection. R5–R9 remained open at that review (see the R5/R6/N1 entry below).
- Schema v1→v3 and v2→v3 were independently checked on separate local database copies:
  existing observation data preserved, source hashes unchanged, reopening consistent.
  The original database has not been migrated in this review. Previously accepted samples
  require renewed acceptance once migrated because schema v3 tracks a data revision.
- BASELINE-001 / EXP-001 / T0 remains provisional. Source/export checks pass, but this is
  not human boundary/topic validation. Images stay on-device and all private artifacts
  remain Git-ignored. No real intervention or post-intervention result is claimed.
- This review changes reports/research tooling only. No product implementation changes,
  automatic merges, real-data edits, external classification or deployment are performed.
- **R5/R6/N1 implemented (Claude cloud, 2026-11-27), not yet independently verified:**
  [CLAUDE-R5-R6-N1](testing-reports/2026-11-27/CLAUDE-R5-R6-N1.md), D-026–D-028, schema v4.
  132 synthetic tests passed on Linux / Python 3.12.3. Awaits Codex review; R7–R9 stay open.
- Original acceptance criteria remain in [PR-001](testing-reports/2026-11-26/PR-001.md);
  the C1–C4 history remains in [PR-003](testing-reports/2026-11-26/PR-003.md).

## Sprint 1 (this release): local MVP
Observer (recording import, frames, segmentation, mock + pluggable vision classifier, manual review),
Taste Engine (versioned profiles, EXP-001), Evaluation Engine, rules-based Strategist,
Manual/Mock actuators, Instagram manual adapter, Control Center, CSV/JSON export.

## Next
1. **Correction/import workflow (Codex verification)**: R5/R6/N1 are implemented on the
   R5/R6/N1 PR; independently verify them, including the minimal `pr1_review` adaptation and
   capture-time metadata on a real QuickTime recording on-device. C1–C4 do not need another
   implementation cycle unless new evidence demonstrates a regression.
2. **Reproducibility (Claude cloud)**: R7/R8 (derived snapshot deletion and recording the
   profile version used for classification). Keep original recordings and user-owned exports.
3. **Accept a defensible baseline before T1 (local)**: establish human boundary reference
   R9, review labels/eligibility on-device, complete the two 50-exposure T0 samples, and
   decide primary analysis membership. Current metrics pool all T0 sessions, including
   pilots/provisional samples; acceptance does not exclude them. Keep data provisional
   until validated, and record founder-approved deviations explicitly.
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
