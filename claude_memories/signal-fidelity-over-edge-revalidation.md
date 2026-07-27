---
name: signal-fidelity-over-edge-revalidation
description: "User directive — Stoic's method is a proven given, not a hypothesis; build a signal generator from the education and measure fidelity, never re-litigate the edge or gate on small-sample profit tests"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1d8f168f-98ba-445f-bd52-251e530880d6
  modified: 2026-07-26T02:30:21.991Z
---

The Stoic method is proven in live trading across timeframes and futures instruments. It is a
**premise of this project, not a hypothesis under test.** The job is: learn the method from the
educational material → turn it into a deterministic signal-generation system → measure whether
**our signals** reproduce and execute that method faithfully.

**Why:** treating the strategy as the thing under test inverts the project. It lets a thin proxy
with invented parameters stand in for the method, and lets a tiny-sample null result read as a
verdict on Stoic. Small samples and profit-chasing are a strong selection bias — they kill
promising paths before they are specified well enough to be worth measuring. VISION says the same
thing ("I am NOT inventing a new strategy"; validation "does NOT gate"), and so does ADR-0011
(backtests are observational and non-gating).

**How to apply:**

- Never frame work as *"does the strategy have an edge."* Frame it as *"does our implementation
  generate the trades the method calls for."*
- **Validate against the labeled material first.** `edu/derived/` has annotated case studies
  (`cs_vol1..7`) and live trades (`live_3_5r_on_nq`, `live_4_14r_on_nq`, `live_4_2r_on_nq`,
  `live_4_3r_on_cl`). Does the generator find *those* setups on *those* dates with comparable
  entry/stop/target? Divergence is a **specification bug**, not strategy failure.
- **Never measure a partial stack as if it were the rule.** The taught stack is HTF map →
  prior-day level / POI → session environment → setup (B&R, SFP) → entry model (SBS) → risk and
  management. Missing legs are a spec gap to close, not a result to report.
- **Reject reference classes that condition away the selection.** A random-entry null holding
  day + direction + risk fixed hands the null three of the four edge components; a profitable
  system fails it. If a control is used, it must not be given the method's own choices.
- **Measure outcomes the way the ledger defines them:** per signal, tracked to close, taught
  management applied, flatten rule honoured, disaggregated by Type / instrument / timeframe.
- **Never conclude from small n.** Widen the data (ES + NQ, all available history) before drawing
  any inference. When n is small, report counts, not verdicts — and not project direction.
- **No parameter grid searches for "the best cell."** Where the material genuinely underdetermines
  a number, the human decides and it is recorded as a strategy decision. **This is the user's
  standing directive, not ADR-0004** — do not cite the ADR for it. ADR-0004 is a separate and
  stricter constraint about *evidence authority*: primary media/PDF is normative, model-derived
  artifacts cannot be the sole normative source. Conflating the two cost a full work cycle on
  2026-07-27 (`docs/notes/2026-07-27-spec-coverage-probe.md` §3).

Rigor is not relaxed by this rule — [[audit-derived-numbers]] (ADR-0021) still governs every
number. What changes is *what is being tested*: our fidelity to the method, not the method.

See [[edge-measurement-first-probe]] for the probe that violated this and what survives from it.
