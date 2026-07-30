# stoic_derived — agent entry point

## Read these four, always. They are 4 pages total.

1. **`docs/STATE.md`** — what is running right now, what is next, what is open. Start here.
2. **`docs/CONSTRAINTS.md`** — what binds the next step, indexed by *when it bites*. Rows are
   triggers pointing at sources; **the row is never the rule**.
3. **`claude_memories/MEMORY.md`** — the memory index. Read it, then whatever the task touches.
4. **`VISION.md`** — the product and its constraints. **Never modify it**; suggest changes to the
   user instead. Agent behaviour rules live at the bottom.

Then open, when the work calls for it: `coding_rules.md` before writing code.

**2026-07-29: the prior build (signal engine, backtest, ledger, dashboard, 22 ADRs, all planning
notes) was archived to the `stoic_legacy` branch and removed from `main` to start a simpler stoic
strategy from scratch.** `docs/architecture/`, `docs/superpowers/`, and `docs/notes/` no longer
exist on `main` — check `git show stoic_legacy:<path>` if you need to see what they said. Do not
recreate them speculatively; the new plan is intentionally minimal until there's a rulebook to bind.

## The pointer rule — this file has broken it before

**A pointer says WHEN to open a document. It never says WHAT the document says.**

There is nothing to save by paraphrasing a binding document, and something real to lose: this file
used to gloss ADR-0004 (now archived) as *"parameters come from the education with evidence, never
from a grid search"*, which conflated two different rules and was acted on without anyone opening
the ADR. The no-grid-search rule is a separate standing directive, stated below.

So: open the source. Open the memory. `docs/CONSTRAINTS.md` tells you which one and when.

## Memory lives in this repo — `claude_memories/`

**Location: `<repo>/claude_memories/` — index at `claude_memories/MEMORY.md`.**

This is the **single source of truth** for this project's agent memory, version-controlled so it
travels between the Windows box and the Mac. Read the index at the start of every session.

**These files must be present.** If `claude_memories/MEMORY.md` is missing or the directory is
empty, something is wrong — stop and tell the user rather than proceeding without context or
rebuilding it from scratch. `git log -- claude_memories/` will show what should be there.

**Do not enumerate the files here.** This paragraph used to hold a hand-typed list; by 2026-07-27 it
claimed 15 files against an actual 21 and was itself the thing most likely to be trusted over the
directory. It was the same failure as the pointer rule above, one section later. `ls
claude_memories/` is the list, `claude_memories/MEMORY.md` is the index, and
`git log -- claude_memories/` is the history — all three are generated, and none of them drifts.

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

## Environment

- **`.venv`** (Python 3.14) for all repo work — `uv sync` to build it.
- `.artifacts/` (run artifacts) and `.scratch/` (temp work) are gitignored and do not travel
  between machines.
- Lint with **`uvx ruff check --fix`** — never a bare `ruff check`. Line length 100.
- Deterministic signal code **must not** call an LLM/SLM. The SLM is an offline research tool that
  helps build the rulebook; the rulebook — plain code — makes the calls.
