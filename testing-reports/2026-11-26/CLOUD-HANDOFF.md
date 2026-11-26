# Claude Code cloud handoff · measurement integrity

Repository: `a51a/AMAS`. Handoff branch: `codex/cto-review-exp001`.
Role: Lead Engineer. Work in your cloud checkout; no access to the founder's local computer
is required or authorized. This file is an engineering task, not a report of completed fixes.

## Start

1. Fetch/check out the handoff branch and read `AGENTS.md`, `CLAUDE.md`,
   `testing-reports/README.md`, and `testing-reports/2026-11-26/PR-001.md`.
2. Inspect Git status. Create your implementation branch from the handoff commit; preserve
   other work and keep the handoff branch intact. Do not merge any PR without founder approval.
3. Set up Python >=3.12, the project's dev dependencies, and FFmpeg. Run the existing suite
   and the synthetic review probes before changes. Record the actual environment.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -ra
.venv/bin/python -m scripts.research.pr1_review
```

The probe script reports existing behavior; exit 0 is not a claim that defects are fixed.
Its inputs/databases are synthetic and temporary. No real recording or external model is used.

## Implement R1–R4 first

| Finding | Required behavior | Meaningful regression coverage |
|---|---|---|
| R1: merge/split deletes unrelated review work | Unchanged intervals keep IDs, labels, eligibility, ad state and provenance. Changed intervals require explicit review; mutation is atomic. | Merge/split a three-item session with confirmed labels; the untouched item must survive. Cover rollback/failure. |
| R2: generic keywords fabricate topic evidence | DIRECT requires explicit biathlon context. UI-only/incomplete text remains UNKNOWN. | Police pursuit and cycling mass-start are not DIRECT; bare Follow is UNKNOWN; explicit biathlon and adjacent winter sports remain supported. |
| R3: followed-account evidence ignored after bulk marking | Track/resolve conflicting eligibility evidence without silently overriding explicit human review. | Classify-before-bulk and bulk-before-classify; followed marker must not silently stay eligible. |
| R4: incomplete baselines unlock intervention | Gate T1 suggestions on the existing baseline protocol and review readiness; make deviations explicit. | Empty, undersized, unresolved and unreviewed T0 samples do not unlock T1; accepted complete baseline does. |

Full evidence and acceptance criteria are in [PR-001.md](PR-001.md). Update README instructions
to the corrected workflow. Add targeted regression tests. Avoid unrelated product expansion.
Do not change the taxonomy, target, denominator or baseline sample requirements silently.

## Cloud/local boundary

- Cloud: code review, implementation, synthetic fixtures, tests, public-safe reports and PRs.
- Local Codex: raw recording analysis, real-image review, private observations and metrics.
- `data/`, `instagram captures/`, and `testing-reports/private/` are intentionally absent from
  GitHub. Their absence does not block these engineering tasks. Do not request an upload,
  enable provider consent, or run the local baseline scripts in the cloud.
- Local-only scripts: `import_baseline.py`, `analyze_baseline.py`, `local_vision.swift`, and
  `verify_baseline.py`. They are research tooling, not validated production classifiers.
- No Instagram credentials, scraping, automated interactions, algorithm reset, or synthetic
  observations in the real EXP-001 dataset.

## Delivery

Save a new public-safe report under `testing-reports/YYYY-MM-DD/` with commit/base, actual
commands and exit codes, test counts/skips, resolved findings, and remaining limitations.
Update `testing-reports/README.md` and the existing ROADMAP; do not overwrite prior evidence.

Open an implementation PR. While the handoff PR is unmerged, target `codex/cto-review-exp001`
so the implementation diff contains the fixes only; state that dependency in the PR body.
After the handoff is merged by the founder, the implementation PR can target main.
Do not claim real-data validation from synthetic tests. Codex will independently review the
implementation and validate the local pipeline. Do not merge automatically.
