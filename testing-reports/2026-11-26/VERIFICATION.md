# Verification after project relocation

Checked: 2026-11-26T12:09:38+00:00.
Commit: `e4bca449111596bc8bafb6f4bbdb1ab4c412155c`. Branch: `codex/cto-review-exp001`.
Working tree at verification time: uncommitted onboarding changes preserved; product implementation unchanged.

| Check | Result |
|---|---|
| Existing pytest suite | 26 passed; exit 0 |
| Local baseline consistency verifier | Passed; see private evidence |
| Synthetic PR #1 review probes | Exit 0; findings remain open |
| Git whitespace check | Passed |
| Git history and working branch | Preserved |
| Editable import from outside the project | Resolves to the relocated checkout |
| Private artifacts and original recording | Git-ignored; not tracked |

Actual environment: Python 3.14.6, macOS 26.7.3. The existing
FFmpeg-dependent tests ran. One Starlette/httpx deprecation warning is present in the test log.
The virtual environment was recreated at the new location using the original pinned installed
versions. Its previous copy is retained under ignored `data/migration/venv-before-relocation/`.

Commands, run from the repository root:

```bash
.venv/bin/python -m pytest -ra
.venv/bin/python -m scripts.research.verify_baseline
.venv/bin/python -m scripts.research.pr1_review
git diff --check
```

These checks establish relocation integrity and existing-suite behavior. They do not fix
the open findings or establish real-image classification accuracy. Baseline labels and
boundaries still need local review. No external image provider was called. At this verification
checkpoint nothing had been pushed or merged. See [PR #1 review](PR-001.md) for engineering
priorities and [CLOUD-HANDOFF.md](CLOUD-HANDOFF.md) for the later cloud collaboration workflow.

Private local run evidence (not available on GitHub):

- [Pytest output](../private/2026-11-26/pytest.txt)
- [Baseline consistency output](../private/2026-11-26/baseline-consistency.json)
- [Synthetic review probes](../private/2026-11-26/pr1-probes.json)
- [Installed environment](../private/2026-11-26/environment-current.txt)
- [Verification manifest](../private/2026-11-26/verification.json)
- [Migration audit](../private/2026-11-26/migration.json)
