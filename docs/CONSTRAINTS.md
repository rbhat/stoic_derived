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
| **Write any new rule into `docs/RULEBOOK.md` §1–§9** | `claude_memories/audit-hard-rules-not-in-material.md` — say where the predicate came from before writing it; a rule invented to fill a silence pre-decides what Phase 4's SLM exists to discover. `docs/PLAN.md` Phase 2a is the audit that clears the ones already there |
| Select a base boundary, or backtest one | `docs/RULEBOOK.md` — §2.2.8 and its engine note |
| Decide whether a trade **or a pending order** is still alive | `docs/RULEBOOK.md` — §5.4.7–§5.4.7c (three conditions, any one ends it) and the engine note under them; §5.3.4a for what ends an unfilled order; decisions **D-24** and **D-17**; §12 row **O-15** |
| Move a stop after entry | `docs/RULEBOOK.md` — §5.4.5 and the engine note on 5.4.4/5.4.5; decision **D-25**; §6.5b and **D-26**. There is exactly one stop move, it is not a trail, and an inside candle never moves it |
| Reach for a "price made a lower high" test after entry | `docs/RULEBOOK.md` §6.5a–§6.5b and decision **D-26** — it is a **cue, not an invalidation**, and an inside candle never counts as one. §5.4.7 is the closed list of things that end a trade |
| Cite a diagram, or lean on two sources agreeing | `docs/AUDIT-2a.md` — F-1: `DIA-P`, `DIA-L` and `step-1-2-3.svg` are one file. Check `md5` before calling two sources independent |
| Compute R, or place a stop | `docs/RULEBOOK.md` — §5.4.1–§5.4.2 and the engine note on 5.4.4/5.4.5. R is fixed once at fill; **5.4.4 has no floor** — do not reintroduce one |
| Decide which bar the entry order sits on | `docs/RULEBOOK.md` — §5.3.3a–c (what a PTB candidate *is*, and the two tests that are **not** it) and the engine note under them, §12 row **O-14**; §5.3.4–§5.3.6 (no bar cap; the order re-anchors) and §5.3.4a (what ends the walk); §5.2.8–§5.2.8a (an inside bar is never the anchor, and what *inside* is measured against) |
| Reach for a distance-to-the-MA test, or any per-candle test for "is this a pullback" | `docs/RULEBOOK.md` §12 **O-14** and the engine note on §5.3.3a; `docs/PLAN.md` Phase 5 layer table. A pullback is a property of a **leg**, owned by **L1** — a layer that has to invent a predicate is usually reaching past a layer that already owns it |
| Emit a second signal while a direction is still running | `docs/RULEBOOK.md` — §2.5 and §3.7; decision **D-21** |
| Fill an order, or decide what a gap through the trigger costs | `docs/RULEBOOK.md` — §5.3.7–§5.3.10 and the engine note under them (R comes from the fill, not the trigger) |
| Reach for a lookback or tolerance on an MA filter | `docs/RULEBOOK.md` — §7.1.7 and the note under it |
| Reach for a rule from the daily-templates / signal-days / chop-zone material | `docs/RULEBOOK.md` — §13 |
| Label a fixture off a marked chart, or go looking for its stop | `docs/RULEBOOK.md` §10.10 — no chart in §10 draws a stop, and the R labels are dollar-normalised; recover the distance, do not guess it. Read the two limits stated there before relying on it |
| Reach for a previous-week level | `docs/RULEBOOK.md` §7.3 — `PWC` / `PWH` / `PLOW` and the week-boundary note (`stoic/bars.py`, ISO week over CME trading days); §12 row **O-16** for the one that is *not* defined |
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
