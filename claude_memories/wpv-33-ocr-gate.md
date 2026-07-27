---
name: wpv-33-ocr-gate
description: "WP-V §3.3 OCR ground-truth gate — ocr_text is verbatim for rule text; the measured failure modes are dropped diagram labels, misread printed prices, and HCOW read as HCOM. Run it with edu/pipeline/ocr_gate.py"
metadata:
  type: project
---

`edu/pipeline/ocr_gate.py` is the §3.3 gate — the ground-truth half of
`docs/notes/2026-07-26-slm-retrain-plan.md` §3. Read-only, deterministic, safe against the live
extraction. Full write-up: `docs/notes/2026-07-27-wpv-33-ocr-gate.md`.

```bash
python3 edu/pipeline/ocr_gate.py counts      # item 3
python3 edu/pipeline/ocr_gate.py sample      # item 1 worksheet; --force to redraw
python3 edu/pipeline/ocr_gate.py slides --video <v> --start <s> --end <s>   # item 2
python3 edu/pipeline/ocr_gate.py slidevar    # slide text that varies between frames of one slide
python3 edu/pipeline/ocr_gate.py score       # fold graded verdicts into counts
```

The sample is **snapshotted to disk** because the corpus grows underneath it; grading is done by
reading each JPEG. `sample` refuses to overwrite without `--force`.

## First pass, 2026-07-27, on 1,138 records (4 of 16 videos, all `concept_*`)

30 frames graded against their JPEGs: **17 exact / 4 minor / 4 omission / 3 error / 2 hallucination**.
Over 273 content lines: 1.5 % wrong, 8.8 % missing (17 of the 24 are one capped frame; 2.8 % without
it), 0.7 % added. `frame_class` agreed 26/30, `ocr_confidence` 17/30. Corpus counts: 0 errors, one
`prompt_sha`, unreadable rate 0.0000, 3.2 % capped, 13.4 % stripped.

**Item 2: 3 of the 4 known slides diff clean against hand-typed ground truth** — the First
Red/Green Day slide, THREE-DAY CYCLE, INSIDE DAY. The fourth (`htf#0218`) lost only its diagram
labels. The rule text is verbatim in all four, including the Day 1–4 definition that
[[red-day-definition]] rests on.

## The three things worth remembering

**1. `HCOW` came back as `HCOM` on 12 of 32 frames.** The `Gold March 2026` chart is labelled
`HOW` / `HCOW` / `LCOW`; the model returned `HCOW` 18×, **`HCOM` 12×**, `HOCW` 2×. Crops of two
frames confirm the chart reads `HCOW`. Highest Close of the **Week** ≠ Highest Close of the
**Month** — these are different levels in the method. This is the first measured case of a level
label being **replaced by a plausible neighbouring method term** rather than merely dropped, and
labels are exactly what Stage B trains on (`wpv-32-extraction-findings.md` → "train on the semantics").
Treat method-term labels as high-quality but not error-free.

**2. Printed prices are misread too.** The Gold chart prints `4,680.9`; across 71 frames the model
emitted `4,689.9` on 30 and the correct value on 4. Two frames of the *same* chart seconds apart
gave `4,689.9` and `4,899.9`. One frame (`htf#0323`) emitted `48,905`, a number on no part of the
image. So the old rule — "a level whose price is printed is a reading, one that is not is a guess" —
is **too generous**: printed numbers are misread as well, just less often, and `htf#0458` read its
printed `25,138.00` correctly. Derive prices in Python from our own bars, as already decided. This
does not reopen `drawn_levels`; it confirms the decision not to train on any OCR'd price.

**3. Diagram labels drop off template slides; the rule text never does.** For frames sharing a slide
title the printed text cannot change, so variation is model error. `FIRST RED DAY` (n=45) kept `SFP`
and `B&R` on only 12 frames and the `DAY 1 DAY 2 DAY 3` row on 13; `THREE DAY TREND REVERSAL` (n=80)
kept `SFP` on 42; `INSIDE DAY REVERSAL` (n=74) kept everything on 72. **The bullets, Psychology and
Bias lines are stable on all 199 frames.** Low impact — the concept survives in the good frames —
so **do not build a repair pass**. When the dataset build picks one frame per slide, prefer the one
with the most lines.

## Capped frames — the dataset rebuild must not read `ocr_text` alone

Measured 2026-07-27 at 2,143 records (all five concept videos done): the capped rate is climbing
with chart density — **3.2 % at 1,138 → 8.0 % at 2,143**, and `concept_the_only_trading_video` ran
**16.1 %**. Not degradation: still 0 errors, one `prompt_sha`, unreadable-line rate 0.0000.

The worst case in the corpus, `concept_the_only_trading_video#0680`, kept **2 of ~20 content lines**
in `ocr_text` and lost `February HCOM`, `February LCOM` ×2, the second panel header, the wave
numbers, the Fib labels and both watermarks. `ocr_text_raw` shows why — a price ladder extrapolated
from 26,500 down to **12,000**, about 12,000 points below the bottom of the image.

**But `chart.drawn_levels[].label` and `chart.annotations` recovered all of it** — `February HCOM`,
`February LCOM`, the wave count, `Friday`, `9:30`, `3:00`. The labels survive in the field
[[#stage-b--what-the-slm-should-be-trained-on]] already nominated; only the values are wrong, and
those were never going to be trained on.

**So: the rebuild of `edu/derived/dataset.jsonl` must read the `chart` block, not just `ocr_text`.**
Reading `ocr_text` alone silently drops the method-term labels on every capped record — 172 as of
2,143 and climbing, concentrated in the densest and most instructive dual-chart frames.

This is also why the cap stays: without it the frame enters an unbounded decode loop, blows through
`VLM_MAX_TOKENS` after ~361 s, fails to parse under the strict `json_schema`, and the state is
**lost entirely** at ~18 min. Capped-with-labels beats lost. Cropping the axis out of the image
first would attack the real cause but changes what the model sees **without changing `prompt_sha`** —
an invisible corpus split, worse than a visible one. Not mid-run.

## Two rules this pass re-confirmed

- **Open the JPEG.** `BLL` on the CL charts and `PHCOM` on the YM chart both looked like misreads
  and are verbatim correct, and `HCOW` — which looks like a typo for `HCOM` — is the *right*
  reading. Three near-misses in one pass. Same rule as `wpv-32-extraction-findings.md` "STOP AUDITING
  `drawn_levels`". Crop at full resolution before asserting a single character is wrong.
- **`slidevar` is legitimate where the retired checks were not.** It compares a *static render*
  across frames, not hand-drawn levels on a live chart that the instructor is actively editing.
  Confirmed by opening five of the groups. Do not generalise it back to `drawn_levels`.

## Two mechanical leftovers, neither costing content

- `_strip_axis_ladders` matches runs of ≥4 consecutive lines, so a date axis emitted as **one long
  line** slips through (3 lines in the 30-frame sample).
- **`frame_class` flips on slides that get drawn on** — the same INSIDE DAY REVERSAL slide came back
  `slide` on one frame and `chart_annotated` on another, and intro animations land in either instead
  of `other`. All 4 of the 30 class disagreements are this. **If the dataset rebuild filters on
  `frame_class` it will drop rule-bearing slides into the chart bucket** — filter on content instead.

Re-run the whole gate at the end of extraction (`sample --force`) before rebuilding
`edu/derived/dataset.jsonl`. See [[wpv-32-extraction-findings]] and
[[signal-fidelity-over-edge-revalidation]] — counts, not verdicts, and no threshold is set here.
