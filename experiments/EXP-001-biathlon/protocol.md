# EXP-001 · Operation Biathlon · Protocol

**Research question.** Can a previously established recommendation system develop a measurable new
topic preference that does not reflect the account owner's existing interests?

| Field | Value |
|---|---|
| Platform / surface | Instagram, desktop web Reels |
| Subject | Founder's existing personal account; recommendation history **not** reset |
| Target interest | Biathlon (no prior interest reported) |
| Experimental target | 20% direct biathlon content (hypothesis, not an expected result) |
| Primary metric | direct biathlon Reels / eligible recommendation exposures |

## Taxonomy
- **DIRECT**: biathlon competitions; biathlon athletes in a biathlon context; biathlon skiing and
  shooting; Biathlon World Cup and IBU content.
- **ADJACENT**: cross-country skiing; winter sports; Winter Olympics without a biathlon focus.
- **UNRELATED**: any other identifiable topic.
- **UNKNOWN**: insufficient evidence.

Eligibility is recorded separately: recommended / followed account / search result / undetermined,
plus ad yes/no. Ads, followed-account content and search results are excluded from the primary
metric; unknown topics remain in the denominator.

## Checkpoints
| Checkpoint | What | Sample |
|---|---|---|
| T0 | Baseline, two sessions (different times of day recommended) | 2 × 50 Reels |
| T1 | Documented intervention, logged in AMAS (time, actions, counts) | none |
| T2 | Immediately after the intervention | 50 Reels |
| T3 | +24 h | 50 Reels |
| T4 | +72 h | 50 Reels |
| T5 | +7 days | 50 Reels |

## Observation procedure (every sample)
1. Desktop browser, logged in as usual, open **Reels** directly. No search, no profile visits.
2. Start a screen recording of the browser window (`⌘ Shift 5`). Do not record DMs or other private
   content.
3. Scroll naturally through 50 Reels. Avoid lingering differently on biathlon content during
   observation sessions (that would be an intervention).
4. Stop, import into AMAS with the right checkpoint, review segments and labels, confirm eligibility.

## Intervention (T1)
Log every action in AMAS before doing it, perform it by hand, then mark it completed with evidence
notes (counts, handles). Suggested starting point: search "biathlon" and watch 10 biathlon Reels
fully; like/save the ones you genuinely would. Instagram's native "Interested / Not interested"
controls are **excluded** here and reserved for a separate experiment (EXP-002).

## Analysis
Baseline share (pooled T0), change in percentage points with 95% CI per checkpoint, time to first
unsolicited biathlon recommendation, persistence at 24 h / 72 h / 7 d, adjacent spill-over,
unknown and undetermined rates. Exposures are autocorrelated; intervals are indicative.

## Threats to validity
Seasonality (biathlon season runs November-March), concurrent trends, observer behaviour during
sampling, single account, labelling subjectivity, ads and followed content mixed into the feed.

## BASELINE-001 analysis status

On 2026-11-26 the first real recording was imported as BASELINE-001 / T0. It remains a
**provisional sample**, not an accepted baseline or a test of the 20% intervention target.
No algorithm reset, platform interaction, or intervention was performed by the analyst.
All images remain on-device by the founder's explicit instruction.

Local state uses the existing schema: `data/amas.sqlite`, `content_observations`,
`recording_frames`, and `experiment_metrics`. Private evidence and results are in
`data/research/BASELINE-001/` (ignored by Git):

| Artifact | Purpose |
|---|---|
| `manifest.json` | Original path, source checksum, media metadata, capture time, session ID, preservation check |
| `stock-import.json`, `stock-frames.json` | Unmodified pipeline proposal and original frame metadata before research refinement |
| `frames-2fps/`, `local-vision.jsonl` | Local sampled frames, OCR boxes/scores, and image-label scores |
| `anchor-runs.json`, `evidence.json` | Proposed individual exposure intervals, boundary brackets, representative samples, flags, uncertainties |
| `analysis.json` | Provisional metrics, unknown-topic sensitivity bounds, ad uncertainty, duplicate candidates, acceptance gaps |
| `amas-export.json`, `observations.csv` | Existing AMAS export formats; real data, never synthetic |
| `review.html` | Local-only visual review sheet, without scripts or external resources |

The local report is an immutable analysis snapshot. Corrections in AMAS require a new
dated export/report; do not silently overwrite the original snapshot. Research sidecars
are separate from session storage and must be handled explicitly if deleting local data.

### Interpretation and review

- A frame sample is not a Reel. Group by persistent creator-overlay transitions, retain
  boundary uncertainty, inspect start/end censoring, and confirm on the local original.
  The research detector is tailored to this recording's layout and is not production-ready.
- Local image tags identify only a small set of content cues; generic people/outdoor tags
  do not establish a topic. All suggested labels require review. No keyword match is not
  evidence of UNRELATED, and no detected DIRECT is not proof of a zero underlying share.
- Keep `is_ad=null` distinct from `false`; absence of an ad marker is not a verified non-ad.
  The existing eval-v1 convention includes recommended items with unknown ad status. Report
  its unknown-ad count explicitly and, separately, a verified-non-ad sensitivity denominator.
- Duplicate-content candidates do not reduce exposure counts. aHash unique-content counts
  are heuristic; review candidates before interpreting them as actual distinct content.
- Conditional unknown-topic bounds are `[D/N, (D+U)/N]` for the chosen eligible exposures.
  They are not confidence intervals and do not account for boundary, eligibility, or
  classifier error. Wilson intervals likewise do not resolve missing classifications.
- Confirm exposure boundaries and eligibility, review content, and complete the planned
  baseline sampling before T1. Preserve the existing two-session protocol; label deviations.
- Subsequent checkpoints need consistent observation behavior and actual capture timestamps.
  Log manual interventions with counts/times, then measure immediate and delayed results.
  This single-account before/after design establishes association, not general causal proof.

Reproduction and engineering tasks: [PR-001 review](../../testing-reports/2026-11-26/PR-001.md).
