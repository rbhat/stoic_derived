# Does the material contain what the 12 open decisions need?

**Date:** 2026-07-27 · **Status:** preliminary — run at 2,463 of 10,120 records (24 %)
**Tool:** `edu/pipeline/spec_coverage.py` (read-only, counts only, safe against the live run)

Prompted by the user's framing, which is the right one: the education will **not** state
tick-aware parameters, so do not look for them. Look for the concept **with worked examples**, and
work backwards:

```
Python rulebook (deterministic parameters)
    ^ derived from
SLM answers ("what is a break and retest?")
    ^ learned from
training data — does it mention the concept, WITH examples?
```

The unit that matters is therefore not a definition but a **dated worked example**: a chart frame
where the instructor has labelled the concept, on a named instrument, resolvable to a date. That is
measurable against our own bars — the same move as the Stage B levels decision (do not OCR the
price, compute it from bars).

## 0. The headline: the chain works, verified end to end

Frame `concept_candle_swing_theory_pdh_pdl_pdc#0385` — graded `exact` by the §3.3 gate, carrying the
drawn labels `Break & Retest`, `Swing Failure Pattern SFP`, `Previous Day High`, `Previous Day Low`,
`Friday Close`, `INSIDE DAY` and the weekday columns — resolves to a single bar:

| | O | H | L | C |
|---|---|---|---|---|
| frame header (OCR) | 25385.**00** | 25415.00 | 25379.25 | 25394.50 |
| `NQ_60m.jsonl`, **2026-01-02** | 25385.**25** | 25415.00 | 25379.25 | 25394.50 |

**H, L and C match to the tick and identify the bar uniquely** among 2,521. The open is wrong by one
tick — another instance of the printed-number misread measured in
`docs/notes/2026-07-27-wpv-33-ocr-gate.md` §5.

**Consequence: the join rule must be 3-of-4, not 4-of-4.** A naive 4-tuple equality returns zero
matches and would have made the whole method look impossible.

### Why this route exists at all

These frames carry **no printed date** — the date is in the time axis, which RULE 1 deliberately
strips as furniture. The first version of this probe looked only for a printed date string and
scored break-and-retest at **0 datable examples**, which was a measurement artifact, not a fact. The
TradingView single-chart header prints an OHLC quadruple that is a far better key than a date string:
it identifies the bar, not just the day. Dual-panel frames do not print OHLC but *do* carry a dated
title, so the two routes are complementary.

## 1. Coverage by concept (2,463 records, 6 videos, 2,028 chart frames)

`uniq` = distinct `(video, ocr_text)` among chart frames. Raw frame counts are inflated by
repetition — one slide held on screen for 74 states counts 74 times — so `uniq` is the number to
read. `DATED` = carries a join key (OHLC fingerprint or dated title) **and** a named instrument.

| concept | slide | chart | uniq | DATED | via ohlc | via title | narrated | serves decision |
|---|---|---|---|---|---|---|---|---|
| `break_and_retest` | 183 | 405 | **176** | **148** | 148 | 0 | 682 | 3. break-and-retest-parameters |
| `swing_failure` | 253 | 405 | **175** | **148** | 148 | 0 | 822 | 4. sfp-parameters |
| `consolidation_range` | 99 | 724 | **375** | **372** | 162 | 210 | 1115 | 5. chop-zone-parameters |
| `session_calendar` | 8 | 1088 | **706** | **586** | 0 | 586 | 719 | 1. session-calendar |
| `golden_zone_fib` | 76 | 595 | **429** | **139** | 1 | 138 | 397 | 8. fib-anchors-and-target-order |
| `swing_pivot` | 22 | 17 | 11 | 2 | 0 | 2 | 55 | 2. pivot-detection |
| `risk_management` | 54 | 6 | 6 | 1 | 0 | 1 | 490 | 10. risk-and-management |
| `chop_zone` | 15 | 2 | 2 | 2 | 0 | 2 | 29 | 5. chop-zone-parameters |
| `sbs_entry_model` | 38 | 263 | 93 | **0** | 0 | 0 | 573 | 7. sbs-pivots / 9. entry-model-selection |
| `confluence` | 191 | 100 | 20 | **0** | 0 | 0 | 117 | 11. confluence-score |
| `trapped_side` | 38 | 40 | 5 | **0** | 0 | 0 | 207 | 6. trapped-side-inference |

### Three tiers

**Tier 1 — has datable worked examples.** `break_and_retest`, `swing_failure`,
`consolidation_range`, `session_calendar`, `golden_zone_fib`. The parameters for these do not need
to be *stated* anywhere: with ~148 instructor-labelled B&R/SFP instances resolvable to NQ 1h bars,
the actual break depth, retest depth, hold time and expiry are **measurable from our own data**.

**Tier 2 — discussed, barely drawn.** `swing_pivot` (11 uniq, 2 datable) and `chop_zone`
(2 uniq) are thin, and both are *foundational* — B&R and SFP are defined in terms of what a swing
is, so decision 2 gates decisions 3 and 4. `risk_management` is heavily narrated (490) but almost
never drawn (6 uniq), which fits: risk is spoken, not charted.

**Tier 3 — zero datable examples today.** `trapped_side`, `sbs_entry_model`, `confluence`. All three
are well narrated (207 / 573 / 117) and appear on slides, but no datable chart instance yet.

## 2. What this does NOT establish

- **24 % of the corpus, and the wrong 24 % for this question.** All seven `cs_vol*` case studies and
  all four `live_*` sessions are absent (`cs_vol1` had just started). The case studies are *by name*
  the worked-example material, and the live sessions are 5,139 states of real-time execution — which
  is exactly where `sbs_entry_model`, `trapped_side` and `confluence` would be demonstrated. **Tier 3
  today is a statement about the concept videos, not about the corpus.** Re-run when extraction ends.
- **`DATED` counts join keys, not resolved dates.** One frame has been resolved end to end. The other
  147 are unverified, and some will fail — a partial/live right-edge bar has no completed match, and
  non-NQ instruments (RTY, Gold, AUD/USD, GBP/JPY, CL, BTC) have no bars in
  `.artifacts/research/bars/` at all, which holds NQ only (`1m`, `5m`, `15m`, `60m`, `D`).
- **Alias matching is crude.** `retest` fired 471×, `range` 429× — both will have false positives
  (`"out of the range"` on the INSIDE DAY slide is not a range instance). The `uniq` column controls
  repetition, not semantic precision. Treat every count as an upper bound.
- **Nothing here has been read against a JPEG** except `#0385`. The tier-3 zeros in particular are
  unaudited.

## 3. The ADR-0004 question this raises — needs the user's decision

If we measure break depth / retest depth / hold time across ~148 instructor-labelled B&R instances
and take the distribution, **is that "parameters from the education with evidence", or a grid
search?**

The argument that it is the former: a grid search optimises a parameter against a *performance*
metric, choosing the cell that backtests best. This measures what the instructor's own labelled
examples actually did, with bars as the measuring instrument and his label as the evidence. No
outcome is consulted. It is closer to reading the education than to searching it.

But it is a judgement call on a binding ADR, and per `signal-fidelity-over-edge-revalidation` the
human decides where the material underdetermines. **No number derived this way should enter
`strategy/rulebook.yaml` without explicit sign-off.**

## 4. Next

1. Re-run this probe when extraction completes — the answer for tier 3 will likely change.
2. Resolve the other 147 B&R join keys and report how many land on a completed bar. That converts
   "148 candidates" into a fixture count.
3. Decide the §3 question above before deriving any parameter.

```bash
.venv/bin/python edu/pipeline/spec_coverage.py
.venv/bin/python edu/pipeline/spec_coverage.py --videos cs_ live_
```
