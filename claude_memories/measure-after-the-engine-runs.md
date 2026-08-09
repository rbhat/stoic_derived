---
name: measure-after-the-engine-runs
description: user directive — do not gate the engine on building an answer key first; decide the open rule, build it, measure once the system runs
metadata:
  type: feedback
---

**Do not propose labelling fixtures as a prerequisite for settling a rule.** When a spec question is
down to a small set of enumerated readings, the user decides it and the engine gets built. Measuring
which reading was right happens **after the system is running**, not before it exists.

Stated 2026-08-08, closing **O-14**. The recommendation on the table was: build the Phase 3 labelled
set from the marked charts (`T2`, `NQ3`, `LT3`/`LT4`, `PTBV`), run all three candidate readings of
the pullback boundary against the trader's own marked entries, and adopt whichever reproduced them.
The user's response: *"why are we even doing this? we will backtest once the system is on. For now,
we go #3."* — and **D-28** was taken directly.

**Why:** the answer-key-first route is defensible on paper and still wrong on sequencing. It puts a
slow, manual, chart-reading phase in front of the deliverable, to settle one rule that the human can
settle in a sentence. Phase 3 and Phase 6 will measure it anyway; doing it first buys nothing that
doing it after does not, and costs the engine its start date. `docs/PLAN.md` already says Phases 2,
3 and 4 bootstrap each other rather than running as a waterfall — the engine is allowed to go first.

**How to apply:**

- When an open row is down to *n* cited readings, present them and ask for the call. Do **not**
  offer "let's build ground truth first and measure" as the recommended path.
- Record the decision as a **D-row** with the rejected readings named, so the later measurement
  knows what it is testing against. D-28 does this.
- Deferred is not cancelled. Say plainly what still depends on the deferred work — Phase 6 cannot
  report fidelity without Phase 3 — so it does not quietly vanish.
- This does not license guessing. The human still decides; see
  [[audit-hard-rules-not-in-material]]. It only settles **when** the evidence gets gathered.

Related: [[audit-hard-rules-not-in-material]] for who decides an underdetermined rule;
[[opus-expanded-role]] for how the work gets run.
