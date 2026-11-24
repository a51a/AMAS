# Product: AMAS

**Tagline:** Your attention. Your algorithms. Your rules.

AMAS (Algorithm Management as a Service) helps people understand, control and reshape the
recommendation algorithms of the social platforms they already use (Instagram, Facebook,
YouTube, LinkedIn, TikTok). It is **not** a social network, an aggregator or a replacement feed.

## Core concept: closed-loop recommendation management
1. **Observe**: measure what the platform actually recommends.
2. **Compare**: against the user's target information environment (interest profile).
3. **Strategize**: plan interventions that close the gap.
4. **Act**: apply supported and authorized changes (Sprint 1: the user acts by hand).
5. **Measure**: quantify the effect and its persistence. Repeat.

## Stage
Proof of concept. Sprint 1 delivers a local research lab to run the first experiment.
There are no live platform integrations.

## First experiment: EXP-001 "Operation Biathlon"
Can an established recommendation system develop a measurable new topic preference that does
not reflect the account owner's interests? Instagram, desktop web Reels, the founder's existing
account (not reset), target topic biathlon, experimental target 20% direct biathlon content.
The target is a hypothesis, not an expected result. Protocol:
[experiments/EXP-001-biathlon/protocol.md](../experiments/EXP-001-biathlon/protocol.md).

## Sprint 1 scope
- Import user-made screen recordings; segment into Reels; classify; manual review.
- Interest profiles (versioned) with direct/adjacent topics and target weights.
- Metrics: direct/adjacent/unrelated/unknown shares, change vs baseline, CIs, time to first
  target recommendation, persistence (24h/72h/7d), unique content, eligibility flags.
- Rules-based intervention plans; manual intervention log.
- CSV/JSON export; clear separation of demo and real data.

## Future features (not in Sprint 1)
Copy Taste, Blend, Fork, Algorithm Health, Taste Passport, Marketplace, additional platforms,
authorized integrations, adaptive LLM strategist.

## Principles
Local-first, privacy by design, human in the loop, measurable outcomes, reproducible experiments,
no dependency on unrestricted platform access.
