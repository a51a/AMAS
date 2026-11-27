# AMAS shared working agreement

The repository is the shared source of truth for the founder, Claude Code, and Codex.
Read this file, `CLAUDE.md`, `ROADMAP.md`, and the relevant experiment protocol at the
start of work. Read `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` before larger changes.
Do not infer decisions or access from previous chats.

## Responsibilities

- Founder: product intent, account actions, experiment participation, approval of major
  scope/architecture changes, publication, and PR merges.
- Claude Code: Lead Engineer, working in the cloud from the GitHub repository; implementation,
  regression tests, delivery, and maintenance. Do not require access to the founder's local disk.
- Codex: CTO, Product Architect, Research Lead; independent reviews, technical research,
  experiment design, data analysis, QA, and concrete engineering tasks. Implement product
  code only when explicitly requested; research scripts are allowed when necessary.
- Review findings are proposals until implemented and verified. A passing synthetic test
  is not evidence of platform behavior or experimental success.

## Current priority and state

Prove the Observe → Compare → Strategize → Act → Measure → Repeat loop on EXP-001.
Do not expand into SaaS, multi-platform automation, or a marketplace before measurement
is trustworthy. PRs #1–#7 are merged; the latest independent review and next engineering
handoff are in `testing-reports/2026-11-27/PR-007.md`. `ROADMAP.md` is the canonical shared status/backlog;
reuse it rather than creating a competing state file.

## Collaboration and changes

- Inspect Git status, current branch, and relevant docs before modifying anything.
- Preserve uncommitted work. Use separate branches or worktrees for concurrent changes;
  coordinate ownership of shared files. Never overwrite another agent's changes.
- Keep product implementation separate from research tooling. Describe assumptions,
  verification commands, unresolved findings, and exact reviewed commits in handoffs.
- Update existing product/architecture/protocol docs and add numbered decisions when
  needed. Do not silently change the experiment taxonomy or metric denominator.
- Do not merge PRs without founder approval. Do not publish private data or send messages
  to collaborators without authorization. A local branch is not a remote delivery.

## Measurement and privacy

- Follow `docs/PLATFORM_COMPLIANCE.md`. No Instagram credentials, scraping, unauthorized
  interactions, algorithm reset, or automated engagement. The founder acts manually.
- Count individual Reel exposures. Keep frame counts, proposed boundaries, confirmed
  exposures, duplicate-content candidates, topic confidence, ads, and eligibility separate.
- DIRECT means explicit biathlon context; ADJACENT means cross-country skiing or other
  winter sports; UNRELATED requires identifiable other content; otherwise UNKNOWN.
- UNKNOWN stays in the eligible-exposure denominator. Unknown ad status is not a verified
  non-ad. Report unresolved eligibility and ad status separately from topic uncertainty.
- Repeated content remains repeated exposure in the primary metric. A perceptual hash is
  only a duplicate candidate, not a confirmed content ID.
- Preserve original recordings and source provenance. Capture time is not import time.
- Raw recordings, frames, OCR, handles, personal observations, research sidecars, and
  detailed metrics belong under ignored `data/` or an explicitly designated local source
  directory. Check `git check-ignore` and staged paths before committing. The repo is public.
- For BASELINE-001 the founder explicitly chose **all images on-device** on 2026-11-26.
  No frame display to a remote model, external vision API, or upload is authorized.
  Do not enable experiment external-provider consent. Local OCR/image models can suggest
  labels; uncertainty must stay visible and unsupported labels remain UNKNOWN.
- Keep real EXP-001 observations separate from synthetic fixtures and DEMO-001. A lack
  of detected biathlon is not proof of absence when substantial content is UNKNOWN.

## Verification

Use `.venv/bin/python -m pytest` for the existing suite. FFmpeg is required for the
synthetic pipeline tests. The target is Python >=3.12; report the actual tested version.
Research instructions and reproducible review probes are linked from the review document.
Never claim real-data validation, human review, remote publication, or merge without evidence.

## Testing reports and artifact location

The founder designated lab/AMAS as the canonical LOCAL project location for Codex and
private research on 2026-11-26. Claude Code works in the cloud from `a51a/AMAS`; its working
directory is its own repository checkout, not a path on the founder's computer. GitHub
branches and PRs carry shared code, instructions, public-safe reports, and engineering tasks.
See the latest entry in `testing-reports/README.md` for the current cloud task;
`CLOUD-HANDOFF.md` is the historical first assignment.
Read `testing-reports/README.md` before starting engineering work; follow its latest review
and test report. Public-safe reports go in `testing-reports/YYYY-MM-DD/`. Private logs,
per-account summaries, and export links go in ignored `testing-reports/private/YYYY-MM-DD/`;
raw recordings, frames, and observation databases remain in ignored `data/` or the existing
`instagram captures/` directory. Add a dated report and update the index after verification.
Do not overwrite earlier run evidence or copy private artifacts into Git. Cloud work must
use synthetic fixtures and the public-safe review; local-only artifacts are unavailable there
and must not be requested as a prerequisite for the engineering fixes. Codex keeps raw-data
validation on-device. Publish cloud test summaries and implementation branches through PRs;
do not merge without founder approval. ROADMAP.md remains the shared backlog;
testing-reports is the canonical location for review/test evidence.
