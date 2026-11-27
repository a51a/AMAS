# AMAS testing reports

Claude Code and Codex: start here before engineering work. Claude Code works in the cloud
from the GitHub repository; Codex performs private research in the founder's local lab/AMAS
folder. Shared reports live on GitHub branches. Read AGENTS.md and preserve uncommitted work.
PRs #1–#5 are merged. Start with the independent PR #5 verification below; the next
handoff is on `codex/pr5-independent-review`. ROADMAP.md remains the shared backlog.

| Date | Report | Use |
|---|---|---|
| 2026-11-27 | [PR #5 independent verification and next tasks](2026-11-27/PR-005.md) | Latest: 98 tests passed; C1–C4 verified; N1 UI follow-up; next R5/R6 task |
| 2026-11-26 | [C1–C4 fixes, Claude Code cloud run](2026-11-26/CLAUDE-C1-C4.md) | Historical implementation report for merged PR #5; independent verification above |
| 2026-11-26 | [PR #3 independent review and next tasks](2026-11-26/PR-003.md) | Historical C1–C4 findings and their reproductions; disposition is in PR-005 |
| 2026-11-26 | [R1–R4 fixes, Claude Code cloud run](2026-11-26/CLAUDE-R1-R4.md) | Historical implementation report for merged PR #3; independent follow-up above |
| 2026-11-26 | [Cloud engineering handoff](2026-11-26/CLOUD-HANDOFF.md) | Historical first cloud assignment; superseded for next work by PR-003 |
| 2026-11-26 | [PR #1 independent review and engineering handoff](2026-11-26/PR-001.md) | Original R1–R9 findings; R5–R9 remain open, latest status in PR-005 |
| 2026-11-26 | [Verification after relocation](2026-11-26/VERIFICATION.md) | Historical relocation verification |
| 2026-11-26 | Local-only: `private/2026-11-26/BASELINE-001.md` | Private measured results; deliberately unavailable to cloud agents |

R1–R4 core reproductions remain improved and C1–C4 are independently verified in PR #5.
R5–R9 and the N1 UI/API parity follow-up remain open. Next cloud batch: R5/R6/N1.
Passing tests does not mean real-data validation. The baseline remains provisional and
all images must stay on-device.
See [ROADMAP.md](../ROADMAP.md) for the shared backlog.

## Report convention

- Put public-safe reviews/test summaries in `YYYY-MM-DD/` and update this index.
- Put private logs and per-account results in `private/YYYY-MM-DD/` (Git-ignored).
- Preserve prior reports; use a new dated/run-specific filename for subsequent runs.
- Record the commit, dirty-tree status, command, exit code, test counts/skips, actual
  environment, limitations, and actionable findings. Distinguish synthetic tests from real data.
- Keep recordings, frames and databases in the existing ignored data directories; link to
  evidence rather than making conflicting copies. Never include private artifacts in commits.
