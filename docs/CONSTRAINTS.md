# Constraints register — what binds the next step

**Read this before starting work. It is an index of triggers, not a summary of rules.**

Each row says *when* a constraint bites and *where the rule lives*. **The row is never the rule** —
open the source. A row that starts to look like a paraphrase has become a bug.

| When you are about to… | Open |
|---|---|
| Write anything that decides a trade | `CLAUDE.md` — "The one rule that governs everything"; `VISION.md` — "What the SLM does vs what generates signals" |
| Pick a number the material does not pin | `docs/PLAN.md` — decision register; `CLAUDE.md` — no grid searches |
| Report how well the engine reproduces the method | `CLAUDE.md` — never conclude from small n; `VISION.md` — Evidence |
| Resample or aggregate bars | `claude_memories/databento-ohlcv-buckets-by-ts-recv.md`; `stoic/bars.py` docstring |
| Touch a timestamp, a session boundary, or the flatten cutoff | `VISION.md` — Timestamps; `stoic/sessions.py` docstring; `claude_memories/tz-aware-day-arithmetic.md` |
| Read bars for a date near 2025-11-28 | `claude_memories/historical-bars-2025-11-28-outage.md` |
| Emit a signal record | `VISION.md` — "What a signal actually is" |
| Write to the ledger | `VISION.md` — Trade ledger |
| Decide where a run artifact goes | `claude_memories/artifact-locality.md` |
| Write any code at all | `coding_rules.md` |
| Call something an error | `VISION.md` — Evidence: check the source artifact, not the system's other output |

The two standing directives that apply regardless of strategy — see `CLAUDE.md`:

- Never conclude from small n. Report counts, not verdicts, and never project direction.
- No parameter grid searches for "the best cell". Where the material genuinely underdetermines a
  number, the human decides and it is recorded as a strategy decision.

Rows get added as decisions from `docs/PLAN.md`'s register close. Point at the source; do not
paraphrase it.
