# Memory Index

**Before this index, read `docs/STATE.md` (what is running) and `docs/CONSTRAINTS.md` (what binds
the next step, indexed by when it bites). This file is the third stop, not the first.**


This directory is the single source of truth for this project's agent memory, version-controlled so
it travels between machines. Write new memories here — not to `~/.claude/projects/<slug>/memory/`,
which has been retired for this project. See `CLAUDE.md` for the contract.
- [Artifact locality](artifact-locality.md) — user directive: all run artifacts under <repo>/.artifacts/, never ~ or other drives
- [Always ruff --fix](ruff-always-fix.md) — user directive: never bare `ruff check`; use `uvx ruff check --fix`
- [Opus expanded role](opus-expanded-role.md) — user directive: Opus subagents orchestrate+verify+audit whole phases, not just final audits
- [Databento OHLCV buckets by ts_recv](databento-ohlcv-buckets-by-ts-recv.md) — aggregating trades by ts_event silently mismatches vendor bars at minute boundaries
