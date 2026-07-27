---
name: ohlc-frame-to-bar-join
description: "The TradingView OHLC header joins a frame to one of our bars on 3-of-4 legs — validated against a perturbed control (0/44). And: count DISTINCT quadruples, never frames — repetition inflates frame counts ~5x."
metadata:
  type: project
---

A TradingView single-chart header prints `O… H… L… C…`. That quadruple identifies a **bar**, not
just a day, and joins deterministically back to `.artifacts/research/bars/NQ_*.jsonl` — the route
around the fact that these frames carry no printed date (the time axis is stripped as furniture by
RULE 1). Tool: `edu/pipeline/ohlc_join.py --audit`.

## The join rule, and the control that makes it reportable

**3-of-4 legs, exact to the tick.** 4-of-4 is too strict — OCR misreads one leg often enough to
matter ([[wpv-33-ocr-gate]] §5) — but a looser rule that matched everything would resolve nothing,
so it was tested rather than assumed (ADR-0021, [[audit-derived-numbers]]):

- **Perturbed control — every leg shifted +1 tick, so the quadruple is on no chart by construction:
  0 of 44 matched anything.** The join is not matching noise.
- **2-of-4 produces 9 ambiguous matches** (median 2 bars). Ambiguity appears immediately outside the
  rule, so 3-of-4 is the floor, not a convenience.
- **3-of-4 produced zero ambiguous matches on real data.** It identifies one bar or nothing.

Prices are stored as integer ticks; NQ is 0.25/tick — verified by reproducing a known bar, not
assumed.

## Count DISTINCT quadruples, never frames

**This is the trap.** A chart held on screen for 40 states prints its header 40 times. At 2,519
records, **232 OHLC-header frames are only 44 distinct quadruples** — a ~5× inflation.

`spec_coverage.py`'s `DATED` / `via_ohlc` column counts **frames**, so its
"~148 break-and-retest instances measurable from our own data" is at most ~44 distinct chart states.
The note warns about exactly this inflation for its `printed_chart` column, provides a `uniq` column
for it, and then does not apply it to `DATED`. **Any count over this corpus needs the same
treatment** — the material repeats itself by construction, because it is a screen recording.

## What resolved, as of 2026-07-27 (concept videos only)

7 of 44, all to `complete` bars — and **all seven to one trading date, 2026-01-02** (6 of that date's
23 hourly bars plus its daily). That is one session walked through on a 60m chart, not seven
independent examples. 4 of the 7 matched all four legs, so the 3-of-4 relaxation bought +3, not +7.

Of the 37 that did not resolve: 1 outside our price envelope, 2 needing a weekly aggregation we
never built, and **34 unexplained**. Do not build a weekly aggregation expecting it to unlock this —
it accounts for 2. The two untested candidates are multi-leg OCR misreads and charts dated outside
the Jan–Jun 2026 window we built; **the price-envelope check cannot rule the second one out**, since
NQ traded through the same prices on many days. An envelope can only rule a quadruple *out*.

`cs_*` and `live_*` — the actual worked-example material — have not been seen by this at all. Re-run
when extraction completes.

**A resolved quadruple is a fixture CANDIDATE, not a fixture.** The identification comes from VLM
output, which ADR-0004 rejects as a sole normative source; [[primary-evidence-review-gate]] stands
between it and any validated rule.

See [[bars-match-education-not-tradingview]] (why our series is the right one),
[[case-study-fixture-track]], [[signal-fidelity-over-edge-revalidation]].
