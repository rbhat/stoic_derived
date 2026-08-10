---
name: plausible-cause-is-not-a-measured-cause
description: a specific, plausible explanation for a failure was written into a docstring as the cause, spread to three documents and named the wrong fix — attribute a failure only after a check that could have refuted it
metadata:
  type: feedback
---

**When something fails, the explanation you write down becomes the cause. Run one check that could
refute it first.**

**2026-08-10, `LT3`/`LT4`.** `scripts/fit_marked_chart.py` reported **16.95 points sd** on this
fixture against 0.4–1.0 on the others. The note written at the time blamed the **CME maintenance
break**: the chart spans 17:00–18:00 ET, the script counts slots back from the anchor, so slots left
of the break must be off. Specific, mechanical, and true of the script as described. It went into
the module docstring, `docs/STATE.md` and `docs/CONSTRAINTS.md`, and it named a fix — *"walk real
bar timestamps instead of counting slots"*.

**All of it was wrong.** Our 5m frame holds no bars in the break either, so `last_index - k` already
walks across it correctly and the named fix was work that would have changed nothing. The real cause
was in the line above the one everyone read: **four candles draw no body pixels** — dojis, and
candles under the shaded session boxes — and each leaves a two-slot gap that the `span / median_gap`
seed could not see, so the comb searched 134–138 slots when the truth was 139. Seeding the count
from the summed gaps fixed it: `LT4` **0.92** pts sd, `LT3` **0.69**, and `T1`/`T2`/`NQ3`
reproduce unchanged.

**Why:** the story was never checked against the artifact, and it was *plausible enough to stop the
search*. The refuting check was one line — print whether our bar frame contains 17:00–17:55 — and
nobody ran it, because the explanation already felt like an answer. Worse, the tool had been
reporting the true cause the whole time: the **comb's own pixel residual was 10.79 px on a 22 px
spacing**, half a candle width, and drops to 0.51 at the right slot count. A diagnosis that explains
the headline number can still ignore the diagnostic sitting next to it.

**How to apply:**

- Before writing a cause into a docstring or `docs/`, ask **what observation would refute it** and
  make that observation. If it costs one line, there is no excuse.
- **Read every number the tool already prints**, not just the one that failed. Intermediate
  residuals fail earlier and more specifically than the final one.
- Distrust an explanation that arrives *with* a fix attached and no measurement between them. The
  fix is what makes it feel finished.
- A cause written into a shared document is load-bearing within a day. Correct it in **every** place
  it landed — [[sweep-a-misreading-to-every-instance]] is the same sweep for reading errors.

Related: [[negative-result-over-an-incomplete-range]] (theorising about *why* a search failed before
checking the search); `VISION.md` *Evidence* — check the source artifact, not the system's own
other output.
