# Case-study fixture track — state and resume point

**Date:** 2026-07-25 · **Branch:** `research/case-study-fixtures` · **Commit:** `97d9fba`

This note is the durable handoff for the fixture work. It travels with the repo, unlike the
per-machine agent memory, so a session on any machine can resume from here.

---

## 0. The direction this serves

Read `docs/notes/2026-07-26-edge-measurement-first-probe.md` §0 first if you have not.

The Stoic method is a **premise of this project, not a hypothesis under test**. The question is
never *"does the strategy have an edge"* — it is *"does our implementation generate the trades the
method calls for."* Divergence from the labelled material is a **specification bug**, not strategy
failure. Small samples produce counts, never verdicts, and never project direction (ADR-0011:
backtests are observational and non-gating; VISION: validation "does NOT gate").

## 1. Decision: do not retrain or rebuild the SLM

Asked whether to rebuild or fine-tune next. The answer is neither, for three reasons that should
survive:

1. The fine-tune's **only** real win is *closed-book* grounding — citing from memory with no corpus
   in the prompt (`cited_qa`: 240/240 real corpus videos, vs the instructed base's 297/297
   invented; McNemar p=1.1e-72).
2. Both tasks the SLM now serves — resolving the 12 `unresolved_decisions` in
   `strategy/rulebook.yaml`, and building fixtures from `edu/derived/` — are **open-book**: the
   source goes into the prompt. That is the `rule_candidate` regime, where the fine-tune is neutral
   on citations (349/349 vs 346/349, p=0.25) and materially **worse** on body text (.395 vs .630).
3. You cannot train toward the new objective anyway — its training signal is *labelled fixtures*,
   which do not exist yet. Building them is the work.

Full audited verdict: `docs/notes/2026-07-25-slm-eval-learnings-and-gap-to-goal.md`.

**What would reopen a model decision:** chart reading proving unreliable during the fixture pass.
That calls for a **vision** model change (the Mac's `qwen3-vl-30b-a3b-instruct-mlx`, which already
produced `moments.json`), not another text fine-tune on citations.

## 2. What was built

`research/extract_case_studies.py` — deterministic seeder over
`edu/resources/case_studies/vol*/*.pdf`. Extracts **only** what the PDF proves: the embedded text
layer plus a SHA-256 of the source asset. It reads no chart imagery and infers no price.

```bash
.venv/bin/python research/extract_case_studies.py \
    --out .artifacts/research/fixtures/case_study_index.json
```

### The unlock: these PDFs have a text layer

Page titles are machine-readable and carry **instrument + date + the instructor's own day
classification** — e.g. `NQ Feb 4th (First Red Day)`,
`GC Mar 12th, 2026 (First Red Day, Inside Day, Consolidation → Expansion)`. No VLM needed for the
index. Charts are embedded at ~4200–4800 px; render with `pymupdf` (now a declared dependency).

- **59 pages** → 50 session pages + 9 overview/undated.
- **25 in v1 scope (NQ)**, spanning **2026-02-03 .. 2026-04-17** — entirely inside the historical
  data already on disk. **22 distinct sessions** (2026-02-04 appears 3×, 2026-04-10 2×).
- Out of scope: GC 11, BTC 5, GBP/JPY 4, CL 2, YM 2, RTY 1.
- vol2 titles omit the year; it comes from the volume cover page ("NQ February-March 2026").
- Audit: the single weekend date (`cs-vol1-p03-btc-2026-02-21`, Saturday) is **correct** — BTC
  trades weekends. Not a parser bug; do not re-investigate.

## 3. Finding: our bar pipeline reproduces the material's own levels exactly

Glossary (with evidence ids) defines **HCOM = highest daily close of the month**, **LCOM = lowest
daily close of the month**; PDH/PDL/PDC = previous daily high/low/cash close.

Derived from `.artifacts/research/bars/NQ_D.jsonl` for February 2026:

| level | derived from our data | drawn on vol2 p03 | delta |
|---|---|---|---|
| February HCOM | **25,873.25** (2026-02-02) | 25,873.25 | **0.00** |
| February LCOM | **24,425.25** (2026-02-05) | 24,425.25 | **0.00** |

Independent confirmation that the SP1 aggregation reproduces the instructor's levels. PDC 25,421.25
and PDL 25,219.00 for the 2026-02-04 session are consistent with the drawn lines, but a visual read
carries roughly ±10 pt, so this does **not** settle session-close vs cash-close for PDC.

This is why the working rule is: **derive levels from our own bars and use the chart as the check**,
rather than reading prices off images. Only chart-exclusive facts (which setup, which pivots,
instructor intent) require the image.

## 4. Finding: the page-title date is the TRADE day, not the signal day

`NQ Feb 4th (First Red Day)` does **not** mean Feb 4 is the first red day — Feb 3 is. The education
states it outright:

> "printed first red day and **this was the trade day right after the first red day**"
> — `edu/derived/cs_vol3_gold_futures_study/transcript.txt`

> "**if yesterday was the first red day after a pump** look for continuation shorts"
> — `edu/derived/concept_candle_swing_theory_pdh_pdl_pdc/transcript.txt`

The naive reading would have mislabelled every one of these fixtures by one day.

### RESOLVED 2026-07-26 — see §4a. The definition of "red" is a recorded strategy decision.

The earlier framing here was wrong in two ways and is superseded by §4a below. Kept for the record:
it claimed the arrows on vol2 p06/p08 mark "the intended candle" (they do not — they mark the trade
day), and it scored 5/7 against page-title parentheticals that are **cycle context labels**, not
per-date candle classifications.

## 4a. RESOLVED — red day, signal day, trade day

**"Red day" = `close < open`.** Human strategy decision by the user on 2026-07-26 (ADR-0004: where
the material underdetermines, the human decides and it is recorded). Recorded as a decision, not a
measurement — the data cannot settle it: across all 7 labelled NQ red/green pages, `close<open` and
`close<prior_close` agree on **every single date**, under both D-0 and D-1 scoring. Do not re-derive
this from data; it is not discoverable there.

**The setup sequence** is stated verbatim on a slide in `concept_simple_stoic_setups_sss`, held
**00:35:12 → ~00:35:57**:

> First Red/Green Day — "The first crack in the wall"
> **Day 1:** Highest Close of the Month · **Day 2:** Highest Close of the Month
> **Day 3:** Highest Close of the Month · **Day 4:** First Red Day = CONFIRMATION

**Signal vs trade day:** the red day is the **signal**; you trade the **next** day.
`concept_simple_stoic_setups_sss` 00:37:33 — *"the signal is the first red day and you look for the
setup the next day; we don't trade the signal, we trade the day after the signal."* Confirm with
consolidation on the 5-minute chart; after a first red day the setup may appear in **Asia or London**,
not only the New York range (`sss` 00:22:48).

Documented exception — the red day itself is sometimes traded, and is explicitly the worse variant:
`cs_vol1` 00:16:43 (*"You can try to trade this first red day, but… the better setup comes after"*),
`cs_vol5` 00:33:28, and `cs_vol2` 00:13:54–00:15:04 (the Mar 5 page — *"not as clean"*, *"ugly"*).

### The canonical fixture (verified against our bars)

The example on screen at the slide is Jan 26–30, and our daily bars reproduce it:

| | date | open | close | candle | |
|---|---|---|---|---|---|
| Day 1 | 2026-01-26 | 25,585.50 | 25,861.25 | GRN | |
| Day 2 | 2026-01-27 | 25,861.25 | 26,110.00 | GRN | new HCOM |
| Day 3 | 2026-01-28 | 26,111.25 | 26,268.25 | GRN | **new HCOM** |
| Day 4 | **2026-01-29** | 26,282.50 | 25,982.50 | **RED** | **signal** |
| trade | 2026-01-30 | 25,998.50 | 25,639.25 | RED | continuation, −343.25 |

**Test case to implement:** 3 consecutive `close>open` days, the third setting the month's highest
close → Day 4 `close<open` = signal → trade Day 5.

Note `2026-03-05` (vol2 p06) **fails** this precondition — March had only Mar 2 and Mar 4 as
new-HCOM days, and they are not consecutive. That is consistent with the instructor calling it
"not as clean". Do not treat p06 as a positive fixture for this template.

### What the arrows and page titles actually mean

- The **arrow marks the trade day** = the page-title date = the session on the intraday panel.
  Verified on p03 (Feb 4), p06 (Mar 5), p07 (Mar 6), p08 (Mar 9), p09 (Mar 12).
- The **title parenthetical is a cycle-context label**, not a classification of that date's candle.
  `concept_htf_stoic_trader_protocol` 00:21:03 shows templates stack — *"the day two signal, which is
  the inside day, **also a first red day**, and then you have the day three that you trade."* So
  p06–p09 all reading "(First Red Day)" is one cycle across four sessions, not four flip days.
- Consequence: **the flip is not always D-1.** p03/p07 trade the day after the signal; p06 trades
  the signal day itself.

## 5. Conventions

- Fixtures are a **separate artifact from rulebook `examples`**. `strategy/rulebook.py` hard-fails
  unless `examples[].evidence_role == "illustrative_only"`, so chart-derived numbers cannot ride in
  that way. Human-verified fixtures belong in `strategy/fixtures/` (committed); the generated index
  stays under `.artifacts/` (ADR: artifacts are repo-relative and gitignored).
- Page renders go to `.scratch/case_study_pages/` (VISION: use `.scratch/` for temp work).
- `uvx ruff check --fix` — never a bare `ruff check`. Line length 100.
- Every number reported is presumed invalid until adversarially audited (ADR-0021).

## 6. Resume point — next actions in order

1. ~~Read vol2_p06/p08 to settle the red definition.~~ **DONE 2026-07-26** — see §4a. Superseded:
   the arrows mark the trade day, and the definition is now a recorded human decision.
2. **WP-V: exhaustive visual extraction** — `docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`.
   This is now the blocking prerequisite: definitional content lives on slides that no transcript
   contains, and the existing keyframe labels are unverified (one is a hallucinated caption). Do
   this before more chart-pixel archaeology.
3. **Chart-extraction pass** over the 25 in-scope pages → one proposal per fixture for human
   review. The user has chosen to **review every fixture**, not a sample: the VLM/agent proposes,
   the human confirms or corrects each field, with source page cited alongside. Nothing downstream
   consumes a fixture whose `review.status` is still `unverified`.
4. **Feed confirmed numbers into the 12 `unresolved_decisions`.** vol2 p03 alone bears on
   `fib-anchors-and-target-order` (the ladder drawn is 1 / 1.618 / 2 / 2.618 / 4.236),
   `sbs-pivots-and-origin` (pivots are numbered 1–5 directly on the chart), and
   `risk-and-management`.

## 8. Our bar series matches the education — not a stock TradingView chart

On 2026-07-26 the user's TradingView quoted 2026-03-04 close **25,645** and 2026-03-05
O 25,663 / H 25,757 / L 25,279.6 / C 25,517. Our `NQ.c.0` bars give 25,138.00 and
O 25,156.50 / H 25,250.00 / L 24,772.50 / C 25,010.50 — a **near-constant +506.5 to +507.1 offset
across all four legs**, i.e. a contract/back-adjustment difference, not a data error.

Ours is the series that matches the material: the vol2 PDFs label **HCOM 25,138.00**,
**Feb HCOM 25,873.25**, **Feb LCOM 24,425.25**, and our bars reproduce all three **to the tick**.
Keep `NQ.c.0`. If a future chart disagrees, check the symbol/adjustment before suspecting the bars.

## 7. Rebuilding the environment on another machine

Gitignored and therefore **absent after a fresh clone**:

| what | how to restore |
|---|---|
| `.venv/` | `uv sync` (Python ≥3.14; `pymupdf` is now declared) |
| `.artifacts/research/bars/` | `.venv/bin/python research/build_bars.py` — ~37 min single-core |
| `.scratch/case_study_pages/` | re-render (snippet below) |
| `data/historical/*.dbn.zst` | Google Drive |
| `edu/**/*.mp4`, `videos.zip` | Google Drive, then `./unzip_videos.sh` |
| `edu/derived/**/keyframes/` | regenerate via `edu/pipeline/` |
| `.artifacts/training/` (the SLM) | Google Drive — see §1; not needed for this track |

Bars already cover 2026-01-02..06-05, which contains **every** in-scope fixture date, so no data
download or research-calendar extension is required for this track.

Re-rendering the case-study pages:

```python
import pymupdf, glob, pathlib
out = pathlib.Path('.scratch/case_study_pages'); out.mkdir(parents=True, exist_ok=True)
for pdf in sorted(glob.glob('edu/resources/case_studies/vol*/*.pdf')):
    vol = pathlib.Path(pdf).parent.name
    with pymupdf.open(pdf) as d:
        for i, page in enumerate(d, 1):
            page.get_pixmap(dpi=150).save(out / f'{vol}_p{i:02d}.png')
```
