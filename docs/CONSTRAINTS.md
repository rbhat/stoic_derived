# Constraints register — what binds the next step

**Read this before starting work. It is an index of triggers, not a summary of rules.**

Each row says *when* a constraint bites and *where the rule lives*. **The row is never the rule** —
open the source. A row that starts to look like a paraphrase has become a bug.

| When you are about to… | Open |
|---|---|
| Write anything that decides a trade | `CLAUDE.md` — "The one rule that governs everything"; `VISION.md` — "What the SLM does vs what generates signals" |
| Implement any part of the sequence, the entry, or the exit | `docs/RULEBOOK.md` — §2 sequence, §5 entry, §6 targets and exit |
| Read a term the engine has to compute | `docs/RULEBOOK.md` — §0 status legend, then the section that defines it |
| Pick a number the material does not pin | `docs/RULEBOOK.md` — §11 decisions, §12 open; `CLAUDE.md` — no grid searches |
| Select a base boundary, or backtest one | `docs/RULEBOOK.md` — §2.2.8 and its engine note |
| Compute R, or place a stop | `docs/RULEBOOK.md` — §5.4, especially the engine note on 5.4.4 (the ATR floor changes R before every downstream ratio) |
| Decide which bar the entry order sits on | `docs/RULEBOOK.md` — §5.3.4–§5.3.6 (no bar cap; the order re-anchors), and §12 row **O-13** |
| Reach for a lookback or tolerance on an MA filter | `docs/RULEBOOK.md` — §7.1.7 and the note under it |
| Reach for a rule from the daily-templates / signal-days / chop-zone material | `docs/RULEBOOK.md` — §13 |
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

Rows get added as decisions close. `docs/RULEBOOK.md` §11 is where a closed decision lives; §12 is
where an open one waits. Point at the source; do not paraphrase it.
