---
name: wpv-32-extraction-findings
description: "What the WP-V §3.2 extraction output actually says — STOP AUDITING drawn_levels, ocr_text is the signal and it is healthy, level values are advisory, and what Stage B may and may not train on. How to run the job is wpv-32-extraction-ops."
metadata:
  type: project
---

**This memory is what the output *says*. How to *run* the job is [[wpv-32-extraction-ops]].**

## STOP AUDITING `drawn_levels`. The disagreements are the instructor, not the model.

**User's call, 2026-07-27, after two agents in a row built machinery to measure this field.** Read
this before writing any new check against `chart.drawn_levels`.

These are **screen recordings of a person live-drawing on TradingView**. The corpus therefore
contains transient UI states, and every "the model misread the level" finding so far has turned out
to be the model reading the transient state **correctly**:

- **`candle_swing_theory` #523 → #524** — the "PDH ↔ PDL swap" at 25,265.25. Open the JPEGs: the
  instructor has TradingView's **Horizontal Ray text dialog open and is typing the label.** #523's
  textbox reads `PDH` and the chart reads `PDH`; #524's reads `PDL` and the chart reads `PDL`. He
  typed it wrong and fixed it. **Both frames were read perfectly.**
- **`candle_swing_theory` #388 → #389** — `Previous Day High` "moving" 25,394.5 → 25,749.25. The
  line labelled `Previous Day High` sits at ~25,725. **25,749.25 is the mouse cursor's price tag**
  on the right axis. The model bound a real printed number to the nearest label. Not an axis
  estimate — a cursor.

**So the gate's own headline numbers are not clean model-error rates.** Check 1's 39 % and check 0's
26.6 % (below) both fold in instructor edits, dragged lines, cursor tags and half-typed labels. They
are still worth *looking at*, but they must never be quoted as "the VLM's level error rate", and no
threshold should ever be set against them.

**A check that compares the model against itself cannot tell you the model is wrong** — it tells you
two frames differ, and in this corpus the frames genuinely do differ. Establishing model error needs
ground truth: **open the JPEG.** That is what both retired checks skipped.

Two checks have now been built on this mistake and retired:

1. the naive check 1 (23.2 % on chart advances, retired 2026-07-26), and
2. `check_label_stability` / "check 1b" (4.5 % "label swap", built and reverted 2026-07-27,
   commits `a5a03f1` → `d95090c`). Its 4.5 % was the instructor renaming his own lines.

**Do not build a third.** `drawn_levels` values were already ruled advisory and are explicitly not
trained on — see § Stage B below. Measuring a field we have already decided not to use is the
overcomplication, not the fix.

**What §3.2 is actually for: capturing the concepts.** The method's specification lives in
`ocr_text` (rule statements, slide text), `concepts`, `annotations` and the level **labels** — which
is what Stage B trains on. `ocr_text` has been verbatim-correct on every frame spot-checked against
its JPEG, across slides, NQ, Gold and AUD/USD. **That is the signal, and it is healthy.**
Perfect per-frame capture is not achievable from a live screen recording and is not the goal.

## What the results say

- **`ocr_text` is good.** The First Red/Green Day slide (`concept_simple_stoic_setups_sss#0031`)
  and the THREE-DAY CYCLE slide (`concept_htf_stoic_trader_protocol#0018`) both came back verbatim
  against their JPEGs. This is the objective — see [[slide-text-not-in-transcripts]].
- **`drawn_levels` is mixed, and the "zero tick-exact matches" line was wrong.** That came from a
  small early batch. Measured over the **962 levels of the completed video** (all NQ, the one
  instrument with bars): **460 `ohlc_match` / 498 `in_range_no_match` / 4 `out_of_range`** — a
  47.8 % match rate. Against a coincidence baseline it is real signal, not noise: drawing prices
  uniformly over the span the levels themselves occupy hits some daily OHLC within 1 tick only
  **4.2 %** of the time (2.8 % over the full bars range), so 47.8 % is ~11× the null.
  `ohlc_match` still is not "correct" — a level may legitimately sit on a 15-minute swing the daily
  bars never touch, which is what `in_range_no_match` is for — but the field is carrying
  information and should not be written off.
- **Where it fails is levels with no printed price.** The Gold frame `#0025` transposed the
  Previous Month Lowest Close to `4,689.9` against a chart reading **4,680.9**, every other field
  exact. On the AUD/USD frames the PDH/PDC/PDL lines carry *no printed number at all*, and across
  five consecutive frames of the same chart the model returned three different values for PDH
  (0.71840 / 0.71940 / 0.71920 / 0.71840 / 0.71940) and three for PDL (0.71180 / 0.71180 / 0.71120 /
  0.71180 / 0.70340) — it is estimating against the axis. **The rule is: a level whose price is
  printed is a reading; a level whose price is not printed is a guess.** The prompt already says to
  leave the latter out, and it does not obey. Levels stay advisory; the rulebook value is in
  `ocr_text`. Consistent with [[bars-match-education-not-tradingview]] and [[audit-derived-numbers]].
  (Real call-outs on those frames did survive, but in `annotations` — `2 @ 0.71255`,
  `2 @ 0.70835` — prose, not verbatim, and `Monday Low` came back 0.70520 where the chart reads
  0.69560.)
- **The label sorts the good from the junk, and it does it cleanly.** Splitting those same 962
  levels by what they are labelled:

  | label | n | `ohlc_match` | vs 4.2 % null |
  |---|---|---|---|
  | method term (`Previous Day High`, `Friday Close`, `PDC`, `PWL`, …) | 627 | **68.4 %** | 16× |
  | anything else (`M` 157, `Y` 52, `BWH`, `Swing Failure Pattern SFP`) | 281 | **5.7 %** | ~1× |
  | unlabelled | 54 | 27.8 % | 7× |

  The "other" bucket is indistinguishable from chance because most of it **is not a level at all** —
  `M` and `Y` are chart furniture, and `Swing Failure Pattern SFP` / `Break & Retest` are concepts
  misfiled into `drawn_levels`. So the field is not uniformly unreliable; it is two populations, and
  the label separates them deterministically, the same way `_strip_axis_ladders` separates furniture
  from content.
- **Frame classification is loose at the edges.** Intro animation frames come back
  `chart_annotated` with `ocr_confidence: high` over scattered glyphs; `frame_class` also flips
  between `slide` and `chart_annotated` on slides the instructor drew over; and on dual-panel frames
  the reported `timeframe` is arbitrary (`#235` said `1D`, `#236` said `5`, same two-panel chart).
  The OCR is faithful to what is on screen; the label and the confidence are not. **Do not filter on
  `frame_class`** — see [[wpv-33-ocr-gate]].
- **`ocr_confidence` has no enum value for "no text present"**, so blank frames report `unreadable`.
  Affects ~7 records. Not worth a corpus split.

## The levels audit — BUILT 2026-07-26, `edu/pipeline/levels_audit.py`

Read-only, deterministic, safe against a live extraction, counts only. **Bars are secondary by
construction** (user's direction: if there are no bars we should not depend on them) — we hold daily
bars for NQ alone and the corpus is mostly AUD/USD, gold, GBP/JPY, RTY and BTC. Results on the first
833 records:

| check | needs bars | result |
|---|---|---|
| **0. collapse** — distinct method-term levels on one frame sharing a price | no | **110 / 363 frames (30.3 %)** |
| **1. self-consistency** — adjacent states, chart advances excluded | no | **104 / 272 labels (38.2 %)** moved while a neighbour held still, median **24.6 bp** |
| **2. label taxonomy** | no | 78.4 % method-term; the rest is `M` ×157, `Y` ×52, `Swing Failure Pattern SFP` |
| **3. nearest daily OHLC** | NQ only | method-term: 65.5 % within 1 tick, **95.9 % within 40 ticks, none beyond 200** |

**Read these under the STOP directive above** — checks 0 and 1 fold in instructor edits and are not
model-error rates.

**The naive version of check 1 was wrong** and its first run reported 23.2 % on evidence that proved
nothing: in a video teaching PDH/PDL the instructor steps the chart forward a day, so
`Previous Day High` genuinely changes between adjacent states. The discriminator is whether labels
move **together** — an advance moves all of them, a misread moves one and leaves its neighbour
alone. Deltas are in **basis points, not ticks**, because a tick is not the same thing on AUD/USD as
on NQ.

**Checks 0 and 3 look contradictory and are not.** Against bars the values are *near* misses — the
right neighbourhood, wrong by a few ticks. Against itself the model puts three different levels on
one price 30 % of the time. Both are what "estimating against the axis" predicts: it finds the
region and cannot resolve which line it is. **That makes the label usable and the value not.**

## Stage B — what the SLM should be trained on

The guide is the user's: the SLM exists so we can **derive a mathematical model for the Python
code**. Under that test `drawn_levels` values are worthless and the labels are valuable:

- **Do not train on the OCR'd price.** If a level is labelled `Previous Day High` and the frame's
  date is known, the value is **computable exactly from our own bars** — it never needed reading.
  Training on axis-estimated numbers teaches the SLM to emit precise-sounding prices it cannot read,
  and per ADR-0021 they would enter training un-audited.
- **Train on the semantics**: which levels the method draws, what they are called, which one a setup
  keys off. That is the specification Python turns into a rulebook, and it survives every failure
  above — 95.9 % within 40 ticks means the model reliably identifies *which line*, and identification
  is all the label needs to be right about.
- `ocr_text` is unaffected and remains where rule statements live — **but not `ocr_text` alone.**
  Capped records lose most of it while keeping their method-term labels in the chart block; read
  `chart.drawn_levels[].label` and `chart.annotations` too. See [[wpv-33-ocr-gate]] for the full
  Stage B reading rules.

## Gold Fib spot-check — the axis-estimation failure, third instrument

State `#236` / `0236_003353.jpg` (`GC Jan 29th, 2026`, dual 1D + 5m) read against the JPEG:

- **`ocr_text` is right.** Title, both chart headers, `DAY1/DAY2/DAY3`, `Thursday`, `9:30`,
  `61.8%`, `50%`, `1.618`, `2`, `2.618`, `StoicEdge.com` — all verbatim. Wave numbers 1-5 are not
  in `ocr_text` but are in `annotations` ("numbered wave count from 1 to 5"), as documented.
- **`drawn_levels` values are wrong by 28–82 points, every one.** Chart reads 1.618 ≈ 5,380 /
  2 ≈ 5,352 / 2.618 ≈ 5,258 / 61.8 % ≈ 5,580 / 50 % ≈ 5,560; the model returned 5,420 / 5,380 /
  5,340 / 5,531 / 5,520. **None of these has a printed price on the chart.** Same finding as the
  Gold `#0025` transposition and the AUD/USD PDH/PDL spread — the rule holds on a third instrument.
- **It binds printed numbers to the wrong label.** `9:30` — a *time* label at the top of the chart —
  came back with value `5,531.0`, which is the current-price tag printed on the right axis.
- **Adjacent-state disagreement, again.** `#235` and `#236` are the same chart: 1.618 = 5,436 vs
  5,420, 2 = 5,386 vs 5,380, 50 % = 5,524 vs 5,520. Values that must be identical are not.
- Every label here (`1.618`, `2`, `2.618`, `61.8%`, `50%`, `9:30`) is in the **non-method-term**
  bucket, which the levels audit already measured at 5.7 % `ohlc_match` — indistinguishable from
  chance. Consistent, not new evidence against the method-term bucket.

Minor leftover: the TradingView logo glyph came back as `T7`.

**Nothing here changes the Stage B decision** — it is the third independent confirmation of it.
Train on level semantics; derive prices in Python from our own bars.

## The §3.3 gate refines all of this — see [[wpv-33-ocr-gate]]

`edu/pipeline/ocr_gate.py`, first pass 2026-07-27 on 1,138 records. It confirms the "`ocr_text` is
the signal and it is healthy" line above with ground truth, and adds three measured caveats: level
**labels** are not error-free either (`HCOW` → `HCOM` on 12 of 32 frames of one chart), **printed**
prices are misread too (`4,689.9` for a printed `4,680.9` on 30 of 71 frames), and diagram labels
(`SFP`, `B&R`, the `DAY` row) drop off some template slides while the rule text never does. Re-run
it with `sample --force` when the corpus finishes.
