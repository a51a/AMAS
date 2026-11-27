# Roadmap

## Shared status · 2026-11-27

- Claude Code works in the cloud from GitHub; Codex keeps private research in local lab/AMAS.
  [Testing report index](testing-reports/README.md) is the shared entry point.
- PRs #1–#7 are merged. PR #7 merged during independent review. Tested head `b6aa451`
  is tree-identical to main `e87bfb8`: **132 passed, 0 skipped** on macOS / Python 3.14.6.
- **N1 verified; C1–C4 remain verified.** Original R5/R6 symptoms are improved, but two
  P2 cases remain: V1, confirming an existing UNKNOWN retains machine confidence; V2,
  a legacy observation's timezone assumption is omitted from warnings/time-to-first provenance.
  Evidence and acceptance criteria: [PR-007](testing-reports/2026-11-27/PR-007.md), branch
  `codex/pr7-independent-review`. R5/R6 are not fully closed; R7–R9 remain open.
- The `pr1_review` adaptation is accepted: it records new-input rejection and still exercises
  a synthetic legacy row. N1's UI/API gate is covered in all three requested states.
- Schema v1→v4 and v3→v4 were checked on private copies: old observation data and source
  hashes preserved; reopening consistent. Original database is unchanged. Local MOV
  metadata is readable, but metadata alone does not prove exact recording/exposure start time.
- BASELINE-001 / EXP-001 / T0 remains provisional. Source/export checks pass. No human
  label validation, real intervention or post-intervention result is claimed. Images and all
  private evidence remain on-device and Git-ignored.
- Review changes are reports/research tooling only. Codex did not implement product fixes,
  merge PRs, migrate the original database, enable external classification or deploy the app.
- Historical findings and decisions remain in PR-001/PR-003/PR-005 and docs/DECISIONS.md.

## Sprint 1 (this release): local MVP
Observer (recording import, frames, segmentation, mock + pluggable vision classifier, manual review),
Taste Engine (versioned profiles, EXP-001), Evaluation Engine, rules-based Strategist,
Manual/Mock actuators, Instagram manual adapter, Control Center, CSV/JSON export.

## Next
1. **Finish R5/R6 (Claude cloud)**: fix V1/V2 from PR-007 in a small new PR from current
   main, add regression assertions and request independent verification. N1 and C1–C4 need
   no further implementation cycle without new regression evidence.
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
