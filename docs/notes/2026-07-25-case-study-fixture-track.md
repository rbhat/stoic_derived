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

### Deliberately left open: the definition of "red"

The same passage defines red as closing "below the day one close" (close-vs-prior-close), while
candle colour is close-vs-open. Over the 7 labelled NQ red/green pages, **both definitions score
5/7 with the identical two misses**:

- `2026-03-05` — D-1 is not a flip day at all under either definition.
- `2026-03-09` — D-2 is also red, so D-1 is not the *first* red day.

n=7 does not discriminate. **Do not try more variants** — that is parameter fitting. Resolve it by
reading the chart pages that mark the intended candle (see next actions).

## 5. Conventions

- Fixtures are a **separate artifact from rulebook `examples`**. `strategy/rulebook.py` hard-fails
  unless `examples[].evidence_role == "illustrative_only"`, so chart-derived numbers cannot ride in
  that way. Human-verified fixtures belong in `strategy/fixtures/` (committed); the generated index
  stays under `.artifacts/` (ADR: artifacts are repo-relative and gitignored).
- Page renders go to `.scratch/case_study_pages/` (VISION: use `.scratch/` for temp work).
- `uvx ruff check --fix` — never a bare `ruff check`. Line length 100.
- Every number reported is presumed invalid until adversarially audited (ADR-0021).

## 6. Resume point — next actions in order

1. **Read `.scratch/case_study_pages/vol2_p06.png` and `vol2_p08.png`.** They arrow the intended
   candle and settle §4's open definition by evidence rather than fitting.
2. **Chart-extraction pass** over the 25 in-scope pages → one proposal per fixture for human
   review. The user has chosen to **review every fixture**, not a sample: the VLM/agent proposes,
   the human confirms or corrects each field, with source page cited alongside. Nothing downstream
   consumes a fixture whose `review.status` is still `unverified`.
3. **Feed confirmed numbers into the 12 `unresolved_decisions`.** vol2 p03 alone bears on
   `fib-anchors-and-target-order` (the ladder drawn is 1 / 1.618 / 2 / 2.618 / 4.236),
   `sbs-pivots-and-origin` (pivots are numbered 1–5 directly on the chart), and
   `risk-and-management`.

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
