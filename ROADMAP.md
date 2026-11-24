# Roadmap

## Sprint 1 (this release): local MVP
Observer (recording import, frames, segmentation, mock + pluggable vision classifier, manual review),
Taste Engine (versioned profiles, EXP-001), Evaluation Engine, rules-based Strategist,
Manual/Mock actuators, Instagram manual adapter, Control Center, CSV/JSON export.

## Next
1. **Run EXP-001 for real**: T0 × 2 baseline recordings, labelling, intervention, T2-T5.
   Tune segmentation thresholds on real desktop recordings (`AMAS_SEGMENT_*`).
2. **Faster labelling**: keyboard-driven review queue, bulk label, label propagation across
   near-duplicate fingerprints, inter-rater check (two labelling passes on a subset).
3. **Classifier evaluation**: hold-out set of human labels, confusion matrix per classifier version,
   cost per session for the vision LLM.
4. **EXP-002 design**: Instagram native preference controls vs. behavioural intervention
   (separate account or separate time window to avoid confounding).
5. **Screenshot import** (capture method already modelled).
6. **Background jobs** for long recordings (currently synchronous).

## Later (not started; require product and compliance decisions)
- Additional platforms: YouTube, TikTok, LinkedIn, Facebook (manual adapters first).
- Authorized integrations via official APIs only, after a platform permissions review.
- Adaptive LLM strategist.
- Algorithm Health (drift monitoring), Taste Passport, Copy Taste, Blend, Fork, Marketplace.
