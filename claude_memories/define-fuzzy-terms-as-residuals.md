---
name: define-fuzzy-terms-as-residuals
description: User design rule 2026-08-09 — define a fuzzy structural term by what it is NOT (the residual left when the named states are excluded), which removes the threshold instead of calibrating it
metadata:
  type: feedback
---

**When a term the material leaves vague has to become code, try defining it as the residual before
trying to measure it.** The user's rule for the *obvious base*, 2026-08-09: *"unless its trending or
breakingout, we should think of it as a base"*, with *"the goal here is to identify an entry, not be
super focused on base definition."* That became **D-34**, and it needed **no *tuned* number** — one
structural floor and nothing to calibrate.

**What the residual framing bought, concretely.** The agent's proposal had been to enumerate four
positive constructions (containment run, overlap run, pullback terminal span, MA-band intersection)
and measure which reproduced the trader's marked bases. All four are *detectors*, and every one
needs a cut point somewhere. Inverting it — name the states that are **not** the term, and let
everything else be the term — meant **D-3**'s three clauses could be **dropped rather than
calibrated**: compression because a base's ranges can be about the same, MA proximity and *breakouts
inside* because **D-15**'s reset already ends the count. The engine has **two** constants after this,
not one: `MEANINGFUL_FRACTION = 0.10` and `MIN_BASE_CANDLES = 2`.

**Where it still went wrong, and this is the part worth keeping.** The first write-up claimed D-34
carried *no number* and that `MEANINGFUL_FRACTION` remained the only constant in the engine. Both
were false — a bare `< 2` was sitting in the predicate. **A residual definition removes the *tuned*
numbers, not every number, and the leftover structural literal is the one most likely to go
unnamed**, precisely because the design story says there are none. Name it and cite its decision row
like any other. Review also caught a second-order version of the same blind spot: inside candles
were skipped when *classifying* but still counted toward that floor, so a run of them became a base
on its own — **96 of 413** bases in the first replay. Residual definitions fail *permissively*, so
their bugs show up as **too much output**, not as errors.

**Why:** a positively-defined predicate for a **J** term is the *"hypothesis wearing a spec's
clothes"* that [[audit-hard-rules-not-in-material]] warns about — it compiles, it reads as settled,
and its threshold is invented. A residual definition has no threshold to invent, so there is nothing
to pre-decide. It also fails safe in the right direction here: the permissive branch is the one the
downstream machinery (the reset, the MA gates, the meaningful-close test) already filters.

**How to apply:**

- Ask *"what is this term NOT?"* before asking *"how do I measure it?"* If the not-states are
  already defined elsewhere in the spec, the term may need no new machinery.
- **Check what already excludes the bad cases downstream.** Two of D-3's three clauses were
  redundant against **D-15**'s reset. A clause that another rule already enforces is not a
  simplification you are giving up — it is duplication you are avoiding.
- **Expect the residual to still need one structural distinction**, and expect that to be the real
  question. Here it was *what counts as trending*, and the answer reused **D-28**'s two-clause test
  via `stoic.structure.opens_pullback` rather than restating it.
- The user's scope note travels with this: **do not perfect the definition of an intermediate
  concept.** The deliverable was an entry, not a base.

Related: [[audit-hard-rules-not-in-material]] for why an invented predicate is the failure mode;
[[measure-after-the-engine-runs]] for the sequencing that let this be decided before any labelling.
