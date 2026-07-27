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

## 3. ADR-0004 already answers this, and the question was posed wrongly

The first draft of this note asked whether measuring retest depth across ~148 instructor-labelled
instances counts as "parameters from the education" or as a grid search, and offered it to the user
as a judgement call. **That was the wrong question, argued from CLAUDE.md's one-line gloss instead of
from the ADR.** ADR-0004 is `0004-strategy-source-authority.md`, *Keep Primary Stoic Material as
Normative Evidence*, and it says nothing about grid searches. Its Context names this hazard exactly:

> Transcription, VLM captioning, SLM mining, and dataset labels accelerate research but can omit,
> paraphrase, or hallucinate details.

Its decision and compliance clauses:

> Stoic media and PDFs are primary evidence. … **Model-derived artifacts may aid discovery but
> cannot be the sole normative source.**
>
> The validator requires a primary media/PDF record for every executable rule, checks asset digests
> and locators, and **rejects model-only evidence**.

**So the proposal fails, for a different and stricter reason than the one debated.** The
break-and-retest *identification* comes from `chart.drawn_levels` and `ocr_text` — VLM output, which
is model-only evidence and is explicitly rejected. Whether the derivation resembles a grid search is
irrelevant; the evidence is the wrong kind. (The no-grid-search rule is real, but it is the user's
directive in CLAUDE.md and `signal-fidelity-over-edge-revalidation`, not ADR-0004. The two got
conflated.)

It remains permitted, explicitly, as **discovery** — "Mining remains useful without entering the
live path." That is what this probe is, and everything in §1 is a candidate, not a finding.

### The compliant path, which is mostly already built

Every visual record cites `video`, `t_start`, `hms_start` and `source_frame` — the locator the
validator asks for. The missing piece is the human verification step, and that is **unresolved
decision 12, `primary-evidence-review`**: *"Which cited media ranges have a human reviewer checked
before any candidate becomes validated?"*

**That reframes decision 12.** It is not one of twelve peer decisions — it is the ADR-0004 gate every
other decision must pass through. No parameter mined from the SLM or the VLM becomes a rule until 12
is defined. It should be resolved first, not last.

## 3a. The join keys, resolved — §4 item 3, done 2026-07-27

**Tool:** `edu/pipeline/ohlc_join.py` (read-only; `--audit` runs the controls). Run at 2,519
records. **Counts, not verdicts, and every number below survived the ADR-0021 controls in §3b.**

`DATED` in §1 counts join keys. Resolving them against `.artifacts/research/bars/NQ_*.jsonl` gives:

| | |
|---|---|
| frames carrying a parseable OHLC header | 232 — all NQ, no unjoinable instrument |
| legs that are not a whole tick | 0 |
| **distinct quadruples** | **44** |
| resolve to exactly one completed bar | **7** |
| match more than one bar | **0** |
| match no bar | 37 |

### The number that matters is 44, not 232 — and it corrects §1

**§1's `via ohlc` column counts frames, and frames are inflated by repetition — the same inflation
§1 warns about for `printed_chart` and then does not apply to `DATED`.** A chart held on screen for
40 states prints its header 40 times. 232 frames carry only **44 distinct quadruples**, so
`break_and_retest`'s 148 `via ohlc` is at most ~44 distinct chart states, not 148 worked examples.
The tier-1 claim that its parameters are "measurable from our own data" across ~148 instances
**rests on a 5× overcount.** Seven resolve today.

All 7 land on **2026-01-02** — 6 of that trading date's 23 hourly bars, plus its daily bar. That is
not a reporting artifact (`trading_date` spans all 111 dates), and it is what walking through a
single session on a 60m chart looks like. It also means the resolved set is **one day**, not seven
independent examples.

### 4-of-4 was not as useless as §0 implies

**4 of the 7 match on all four legs; only 3 needed the 3-of-4 relaxation.** §0 says "a naive 4-tuple
equality returns zero matches" — true of frame `#0385`, which is the frame it was written about, but
not of the corpus: 4-of-4 alone resolves 4 of 44. The relaxation is still right, and §3b shows it
costs nothing in precision, but it buys +3, not +7.

### Why the other 37 did not resolve — mostly unknown, and that is the honest answer

| | |
|---|---|
| price outside our bars' envelope | 1 |
| H-L wider than any timeframe we built (needs weekly/monthly) | 2 — `#0544`, `#0563` |
| **not explained** | **34** |

The missing-timeframe hypothesis was the attractive one — the method is full of weekly levels
(`HCOW`, `LCOW`) and we built only `1m/5m/15m/60m/D`. **It accounts for 2 of 37.** Do not build a
weekly aggregation expecting it to unlock this.

Two candidates remain, **neither tested, and neither should be reported as the cause**: two or more
legs misread by OCR (the OCR-gate note §5 measures single-leg misreads and finds them common), and a
chart whose date falls outside the Jan–Jun 2026 window we built. **The price-envelope check cannot
rule the second one out** — NQ traded through 25,600 on many days, so an instructor charting a date
we never built looks identical to one we did. The envelope can only rule a quadruple *out*.

## 3b. The controls that make §3a reportable

A 3-of-4 rule is weaker than 4-of-4, so under ADR-0021 it has to survive an attempt to break it. A
rule loose enough to match everything resolves nothing.

| control | result | reading |
|---|---|---|
| **perturbed** — every leg shifted +1 tick, so the quadruple is on no chart by construction | **0 of 44 match anything** | the join is not matching noise. Had this landed near 15.9 %, §3a would be worthless. |
| **2-of-4** — the same join relaxed by one leg | 11 unique but **9 ambiguous** (median 2 bars) | ambiguity appears immediately outside the rule. 3-of-4 is the floor, not a convenience. |

3-of-4 produced **zero ambiguous matches** on the real data. The rule identifies a bar or nothing.

```bash
.venv/bin/python edu/pipeline/ohlc_join.py --audit
.venv/bin/python edu/pipeline/ohlc_join.py --audit --videos cs_ live_
```

## 4. Next

1. **Resolve decision 12 first.** It gates the other eleven under ADR-0004.
2. Re-run this probe when extraction completes — the answer for tier 3 will likely change.
3. ~~Resolve the other 147 B&R join keys.~~ **Done — §3a.** 44 distinct quadruples, 7 resolved, all
   on one trading date. Re-run `ohlc_join.py --audit` when the corpus completes; the `cs_*` and
   `live_*` material has not been seen by it at all.
4. Suggest to the user that CLAUDE.md's ADR-0004 gloss ("parameters come from the education with
   evidence, never from a grid search") be split: the evidence-authority half is ADR-0004, the
   no-grid-search half is a separate standing directive. Conflating them cost a full cycle here.

```bash
.venv/bin/python edu/pipeline/spec_coverage.py
.venv/bin/python edu/pipeline/spec_coverage.py --videos cs_ live_
```
