---
name: marked-charts-do-not-fingerprint-to-our-bars
description: SUPERSEDED 2026-08-10 — the SMA fingerprint dates §10's charts to 0.08 points; the 2026-08-09 failure was the bar range, not the method, and the dating conclusion it reached was wrong
metadata:
  type: project
---

**The title is kept because the claim it makes is the thing to unlearn.** On 2026-08-09 an attempt
to date `NQ3` by matching its printed right-axis values against our 5m SMAs found nothing closer
than 41 points in seven years. That was read as the method failing. **It was the range.** Every
§10 fixture is a 2026-07-27 → 2026-08-03 session, and `data/historical/NQ_1m.parquet` ended
2026-06-10 — the sessions were not in the series at all.

Once `scripts/merge_signal_bars.py` extended the spine, the same method dated all five fixtures.
`NQ3` reproduces all four printed values to **0.08 points**. Evidence and the full table:
`docs/evidence/fixture_dating.md`. Tool: `scripts/date_marked_chart.py`.

**Both of the old note's conclusions were wrong, and in the same shape:**

- It dated the charts to **May–June 2026** because `28,716.75` occurred as a bar high only three
  times "in the seven-year series" — a series that stopped at the edge of the very window it was
  reasoning about.
- It proposed that the plotted MAs might not be simple averages of the **close**, and recommended
  testing the contract-roll explanation first. The close is right; `hl2`/`hlc3`/`ohlc4` are 9–13
  points out on the same bar.

**A negative result over an incomplete range is a fact about the range, not about the world.** Both
errors are that one mistake. Before concluding a signal is absent, state the span actually searched
and check the target could have been inside it.

**How to apply:**

- To date a marked chart: `scripts/date_marked_chart.py <four printed axis values>`, then find a
  **second, independent** agreement — a printed daily/weekly level, an on-screen clock, a day
  separator. One sharp minimum is a candidate; `docs/PHASE3.md` requires two.
- **Anchor on recent levels.** Same-week `PWC` matches to a tick (28,306.75 vs 28,306.50);
  month-old `LCOM` drifts ~2 points between screenshots taken a day apart, so it corroborates and
  never dates.
- The old note's advice to prefer *relative* measurements over absolute levels is now unnecessary
  for dating, but it remains true for reading marks off pixels — that error is still ±10 points.

Related: [[artifact-locality]] for where a probe's output belongs; [[coverage-claims-need-enumeration]]
for the sibling failure — a count that matches is not coverage, and a search that finds nothing is
not absence.
