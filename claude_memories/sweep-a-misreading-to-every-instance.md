---
name: sweep-a-misreading-to-every-instance
description: One misread number in §10 was four, and the fourth had already propagated into our own evidence — after finding a reading error, enumerate every instance of its shape
metadata:
  type: feedback
---

When a **reading** error is found once, treat it as a class and sweep for every other instance —
including in the documents we derived from the source, which is where it will have propagated.

**2026-08-10, labelling `T1`/`T2`.** `docs/evidence/fixture_dating.md` had already caught one:
§10.7 reads *"Stop 28,540.75, the PTB low"* off a number that is that chart's **20 SMA axis tag**,
not a level. Measuring the drawn levels on `T1`/`T2` found the same shape three more times —
§10.2's *28,482*, §10.8's *28,473.81* and §10.9's *28,471.53* are the **200 SMA** (`T1`, `T2`) and
the **10 SMA** (`LT3`/`LT4`) at each chart's last bar, all within 0.2 points, while the *drawn*
`Jun LCOM` line measures 28,471.6 against our 28,472.00.

**Why:** the fourth instance had already been believed and built on. `fixture_dating.md` used the
two mis-attributed LCOM prints to state a *contract drift* limit — "month-old levels move ~2 points
between screenshots" — and `docs/CONSTRAINTS.md` carried that as standing advice. The limit did not
exist. A misreading of the source does not stay in the source; it becomes a derived fact that no
later check of the source will catch, because nothing re-reads it. Same failure as
[[coverage-claims-need-enumeration]], one step downstream.

**How to apply:**

- After confirming one misread, **list every place the same kind of number appears** and measure
  them all. Four §10 charts print right-axis tags; all four had to be checked, not the one that
  raised the flag.
- Then **grep our own `docs/` for what was built on it** and correct that too. The source may be
  the user's to edit — `docs/RULEBOOK.md` §10 is — but our evidence and constraint files are ours.
- Prefer a value **measured off the plot** to a value **printed in the axis**: the axis carries
  every indicator's last value, which is what makes the tags non-tick-valid and plausible.
  `scripts/fit_marked_chart.py --probe` is the measurement.
