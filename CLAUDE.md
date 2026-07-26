# stoic_derived — agent entry point

Read these in order before doing anything. This file is a pointer, not a duplicate.

1. **`claude_memories/MEMORY.md`** — the memory index. Read it, then read any entry it points to
   that is relevant to the task. **Read `signal-fidelity-over-edge-revalidation.md` first, always.**
2. **`VISION.md`** — the product and its constraints. **Never modify it**; suggest changes to the
   user instead. Agent behaviour rules live at the bottom of it.
3. **`docs/notes/2026-07-25-case-study-fixture-track.md`** — current work, findings, and the
   resume point. **Start here for what to do next.**
4. **`docs/architecture/adr/`** — binding decisions. ADR-0011 (backtests are observational and
   non-gating), ADR-0021 (every derived number is presumed invalid until adversarially audited),
   ADR-0004 (parameters come from the education with evidence, never from a grid search).

## Memory lives in this repo — `claude_memories/`

**Location: `<repo>/claude_memories/` — index at `claude_memories/MEMORY.md`.**

This is the **single source of truth** for this project's agent memory, version-controlled so it
travels between the Windows box and the Mac. Read the index at the start of every session.

**These files must be present.** If `claude_memories/MEMORY.md` is missing or the directory is
empty, something is wrong — stop and tell the user rather than proceeding without context or
rebuilding it from scratch. `git log -- claude_memories/` will show what should be there.

Expected contents (15 files as of 2026-07-26): `MEMORY.md` plus
`signal-fidelity-over-edge-revalidation`, `case-study-fixture-track`, `red-day-definition`,
`slide-text-not-in-transcripts`, `bars-match-education-not-tradingview`, `slm-model-artifacts`,
`edge-measurement-first-probe`, `eval-comparison-wp-progress`, `audit-derived-numbers`,
`check-dont-relaunch-detached-jobs`, `win-cuda-training-package`, `artifact-locality`,
`ruff-always-fix`, `opus-expanded-role`.

- **Write new memories to `claude_memories/`**, not to any per-machine location such as
  `~/.claude/projects/<slug>/memory/`. That external directory has been retired for this project;
  if a harness recreates it, the copy in this repo still wins.
- One fact per file, kebab-case name, frontmatter with `name` / `description` / `metadata.type`
  (`user` | `feedback` | `project` | `reference`). Cross-link with `[[other-name]]`.
- Add a one-line pointer to `claude_memories/MEMORY.md` for every new file. Never put memory
  content in the index itself.
- Update the existing file rather than creating a near-duplicate; delete memories proven wrong.
- Commit memory changes along with the work that motivated them.

## The one rule that governs everything

The Stoic method is **proven in live trading — a premise of this project, not a hypothesis under
test**. The job is: learn the method from the educational material → turn it into a deterministic
signal generator → measure whether **our signals** reproduce the method faithfully.

- Never frame work as *"does the strategy have an edge."* Frame it as *"does our implementation
  generate the trades the method calls for."*
- Divergence from the labelled material in `edu/derived/` is a **specification bug**, not strategy
  failure.
- **Never conclude from small n.** Report counts, not verdicts — and never project direction.
- **No parameter grid searches for "the best cell."** Where the material genuinely underdetermines
  a number, the human decides and it is recorded as a strategy decision.

`docs/notes/2026-07-26-edge-measurement-first-probe.md` §0 records what happens when this is
violated.

## Environment

- **`.venv`** (Python 3.14) for all market-data, research and repo work — `uv sync` to build it.
- `.artifacts/training/venv` is a separate 3.12 CUDA venv for the SLM only. `uv run` for training
  **must** have cwd `training/win_cuda`, or it destroys that venv.
- `.artifacts/` (run artifacts) and `.scratch/` (temp work) are gitignored and do not travel
  between machines. See the resume note §7 for what to restore and how.
- Lint with **`uvx ruff check --fix`** — never a bare `ruff check`. Line length 100.
- Deterministic signal code **must not** call an LLM/SLM. The SLM is an offline research tool that
  helps build the rulebook; the rulebook — plain code — makes the calls.
