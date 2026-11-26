# AMAS testing reports

Claude Code and Codex: start here before engineering work. Claude Code works in the cloud
from the GitHub repository; Codex performs private research in the founder's local lab/AMAS
folder. Shared reports live on GitHub branches. Read AGENTS.md and preserve uncommitted work.
The current handoff is on `codex/cto-review-exp001`; do not assume it is already on main.

| Date | Report | Use |
|---|---|---|
| 2026-11-26 | [Cloud engineering handoff](2026-11-26/CLOUD-HANDOFF.md) | Start here in Claude Code cloud: branch, scope, commands and deliverables |
| 2026-11-26 | [PR #1 independent review and engineering handoff](2026-11-26/PR-001.md) | Open R1–R9 findings, priority, reproduction and acceptance criteria |
| 2026-11-26 | [Verification after relocation](2026-11-26/VERIFICATION.md) | Current test commands, environment and limitations |
| 2026-11-26 | Local-only: `private/2026-11-26/BASELINE-001.md` | Private measured results; deliberately unavailable to cloud agents |

The review findings remain open. Start with R1–R4; passing existing tests does not mean
those defects are fixed. The baseline remains provisional and all images must stay on-device.
See [ROADMAP.md](../ROADMAP.md) for the shared backlog.

## Report convention

- Put public-safe reviews/test summaries in `YYYY-MM-DD/` and update this index.
- Put private logs and per-account results in `private/YYYY-MM-DD/` (Git-ignored).
- Preserve prior reports; use a new dated/run-specific filename for subsequent runs.
- Record the commit, dirty-tree status, command, exit code, test counts/skips, actual
  environment, limitations, and actionable findings. Distinguish synthetic tests from real data.
- Keep recordings, frames and databases in the existing ignored data directories; link to
  evidence rather than making conflicting copies. Never include private artifacts in commits.
