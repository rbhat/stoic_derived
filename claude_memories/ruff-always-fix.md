---
name: ruff-always-fix
description: "User directive: always run ruff with --fix, never bare `ruff check`"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0ad49c37-6721-49a5-a623-de107f0caade
  modified: 2026-07-26T02:59:55.309Z
---

User directive (2026-07-25): always run ruff with the `--fix` option.

**Why:** A bare `ruff check` just reports and leaves the work undone; the user
wants the auto-fixable subset applied in the same pass rather than reported
back for a second round trip.

**How to apply:** Use `ruff check --fix <paths>` (in this repo:
`uvx ruff check --fix ...`, since ruff is not a declared dev dependency and
`uv run` from the wrong cwd destroys the training venv — see
[[eval-comparison-wp-progress]]). The repo carries a standing backlog of
pre-existing ruff errors in older files (66 at the 2026-07-26 check, up from 46
the day before — the count drifts, so measure it, don't quote this). **Scope
`--fix` to the files being worked on** unless the user asks for the backlog
itself; a repo-wide `--fix` would bury a real change in unrelated churn.
Line-length is 100.
