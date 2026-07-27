# stoic_derived — agent entry point

## Read these four, always. They are 4 pages total.

1. **`docs/STATE.md`** — what is running right now, what is next, what is open. Start here.
2. **`docs/CONSTRAINTS.md`** — what binds the next step, indexed by *when it bites*. Rows are
   triggers pointing at sources; **the row is never the rule**.
3. **`claude_memories/MEMORY.md`** — the memory index. Read
   `signal-fidelity-over-edge-revalidation.md` first, always, then whatever the task touches.
4. **`VISION.md`** — the product and its constraints. **Never modify it**; suggest changes to the
   user instead. Agent behaviour rules live at the bottom.

Then open, when the work calls for it: `coding_rules.md` before writing code,
`docs/notes/2026-07-26-slm-retrain-plan.md` for the active track, `docs/architecture/adr/` for
binding decisions.

## The pointer rule — this file has broken it before

**A pointer says WHEN to open a document. It never says WHAT the document says.**

Every binding document here is short — the 21 ADRs average 39 lines, ADR-0004 is 27. There is
nothing to save by paraphrasing them, and something real to lose: this file used to gloss ADR-0004
as *"parameters come from the education with evidence, never from a grid search"*, which conflated
two different rules and was acted on without anyone opening the ADR. It is actually about **evidence
authority** — primary media/PDF is normative, model-derived artifacts cannot be the sole normative
source. The no-grid-search rule is a separate standing directive, stated below.

So: open the ADR. Open the memory. `docs/CONSTRAINTS.md` tells you which one and when.

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
