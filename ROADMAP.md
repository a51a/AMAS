# Roadmap

## Shared status · 2026-11-26

- Collaboration: Claude Code works in the cloud from GitHub; Codex keeps private research
  in the local lab/AMAS folder. Shared code/tasks/test reports travel through branches and PRs.
  [Testing report index](testing-reports/README.md): local relocation verified, 26 tests passed;
  Git history, working changes, and original recording were preserved.

- PR #1 was merged before independent review. Reviewed head: `b086496`; merged tree:
  `e4bca44`. No product implementation changes were made in the onboarding review.
- Existing suite: 26 passed on macOS / Python 3.14.6 with FFmpeg available. This does not
  establish accuracy on Instagram content. Live external providers remain untested.
- BASELINE-001 / EXP-001 / T0: original preserved; local import, provisional exposure
  segmentation, on-device evidence, and exports exist. Not an accepted baseline; topic,
  boundaries, and eligibility need review. No intervention/post-intervention result exists.
- Founder requires all baseline images on-device. Private local paths and detailed results
  are in ignored `data/research/BASELINE-001/manifest.json` and `analysis.json`.
- Cloud handoff ref: `codex/cto-review-exp001`. Start with
  [CLOUD-HANDOFF.md](testing-reports/2026-11-26/CLOUD-HANDOFF.md) on that branch.
  The review is not an implementation fix. Founder approval is required for merges.
- Full findings, reproduction, priorities, and acceptance criteria:
  [PR-001 review and handoff](testing-reports/2026-11-26/PR-001.md).

## Sprint 1 (this release): local MVP
Observer (recording import, frames, segmentation, mock + pluggable vision classifier, manual review),
Taste Engine (versioned profiles, EXP-001), Evaluation Engine, rules-based Strategist,
Manual/Mock actuators, Instagram manual adapter, Control Center, CSV/JSON export.

## Next
1. **Measurement integrity before T1**: resolve R1–R4 in the review (destructive boundary
   edits, unsafe topic heuristics, eligibility conflicts, and incomplete-baseline gating).
2. **Accept the real baseline**: review local BASELINE-001 boundaries and labels; preserve
   capture/analysis provenance; obtain the remaining protocol baseline samples. Establish
   a human boundary reference before tuning the detector (R9). Keep current data provisional.
3. **Research reproducibility and correction**: R5–R8 (nullable corrections, confidence,
   time validation, snapshot deletion, and profile-version provenance). Then run documented
   T1 and T2–T5 measurements; never infer recommendation change from the current baseline.
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
