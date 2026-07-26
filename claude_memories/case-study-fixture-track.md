---
name: case-study-fixture-track
description: "The Vol 1-7 case-study PDFs are machine-readable fixture ground truth — text layer gives instrument/date/day-label, our bars reproduce the instructor's HCOM/LCOM exactly, and page-title dates are TRADE days not signal days"
metadata: 
  node_type: memory
  type: project
  originSessionId: 55875ae9-8877-4cbf-92fe-1c4e67ee40a4
  modified: 2026-07-26T03:45:21.441Z
---

Started 2026-07-25 under [[signal-fidelity-over-edge-revalidation]]. User chose: start fixtures
from the **case-study PDFs** (not the live videos), and **human-verify every fixture**.

Seeder: `research/extract_case_studies.py` (deterministic, text layer + SHA-256 only, reads no
chart imagery). Output `.artifacts/research/fixtures/case_study_index.json`.

## The PDFs have a text layer — this was the unlock

`edu/resources/case_studies/vol*/…pdf` page titles are machine-readable and carry
**instrument + date + the instructor's own day classification**, e.g. `NQ Feb 4th (First Red Day)`,
`GC Mar 12th, 2026 (First Red Day, Inside Day, Consolidation → Expansion)`. No VLM needed for the
index. Charts are embedded at ~4200-4800px; render with `pymupdf` (installed into `.venv`).

- **59 pages** → 50 session pages + 9 overview/undated.
- **25 in-scope (NQ)**, spanning **2026-02-03 .. 2026-04-17** — entirely inside both historical
  files, so every one is checkable against data we already have. **22 distinct sessions**
  (2026-02-04 appears 3×, 2026-04-10 2×).
- Out of scope: GC 11, BTC 5, GBP/JPY 4, CL 2, YM 2, RTY 1.
- vol2 page titles omit the year; it comes from the volume cover page ("NQ February-March 2026").
- Audit note: the one weekend date (`cs-vol1-p03-btc-2026-02-21`, Saturday) is **correct** — BTC
  trades weekends. Not a parser bug; don't re-investigate.

## Our bar pipeline is verified against the instructor's own charts

Glossary (with evidence ids): **HCOM = highest daily close of the month, LCOM = lowest daily close
of the month**; PDH/PDL/PDC = previous daily high/low/cash close.

Derived from `.artifacts/research/bars/NQ_D.jsonl`, February 2026:
**HCOM 25,873.25 (2026-02-02) and LCOM 24,425.25 (2026-02-05) — delta 0.00 vs the levels drawn on
vol2 p03.** Independent confirmation that the SP1 aggregation reproduces the material's levels.
PDC 25,421.25 / PDL 25,219.00 for the 2026-02-04 session are consistent with the drawn lines, but a
visual read is ±10pt so this does **not** settle session-close vs cash-close for PDC.

## Specification finding: page-title date is the TRADE day

`NQ Feb 4th (First Red Day)` does **not** mean Feb 4 is the first red day. The education says it
outright (`cs_vol3` and `concept_candle_swing_theory_pdh_pdl_pdc` transcripts):

> "printed first red day and **this was the trade day right after the first red day**"
> "**if yesterday was the first red day after a pump** look for continuation shorts"

So the flip day is **D-1** and the page date **D** is when you trade. Guessing the naive reading
would have mislabelled every one of these fixtures.

Open, deliberately **not** resolved by fitting: the same passage defines red as closing "below the
day one close" (close-vs-prev-close), while candle color is close-vs-open. Over the 7 labelled
NQ red/green pages **both definitions score 5/7 with the identical two misses** (2026-03-05:
D-1 not a flip at all; 2026-03-09: D-2 also red so D-1 isn't *first*). n=7 does not discriminate —
resolve by **reading vol2 p06 and p08**, which arrow the intended candle. Do not try more variants.

## Conventions chosen

- Fixtures are a **separate artifact from rulebook `examples`** — `strategy/rulebook.py` hard-fails
  unless `examples[].evidence_role == "illustrative_only"`, so chart-derived numbers cannot ride in
  that way. Verified fixtures belong in `strategy/fixtures/` (committed); the generated index stays
  in `.artifacts/` ([[artifact-locality]]).
- Prefer **deriving** levels from our own bars and using the chart as the *check*, rather than
  reading prices off images. Only chart-exclusive facts (which setup, which pivots, instructor
  intent) need the image.
- Page renders for reading go to `.scratch/case_study_pages/` (VISION says use `.scratch/`).
- `pymupdf>=1.28,<2` is now a declared dependency in `pyproject.toml` + `uv.lock` (it was installed
  ad-hoc first, which would have broken the script on a fresh machine).

## Resume point (next actions, in order)

1. **Read `.scratch/case_study_pages/vol2_p06.png` and `vol2_p08.png`** — they arrow the intended
   candle and settle the red/green definition above. Regenerate renders with the snippet in
   §Conventions if `.scratch/` is empty (it is gitignored and does not travel).
2. Chart-extraction pass over the 25 in-scope pages → per-fixture proposals for human review.
   Derive levels from `.artifacts/research/bars/` where possible; use the chart only for
   chart-exclusive facts.
3. Feed confirmed numbers into the 12 `unresolved_decisions`. vol2 p03 alone bears on
   `fib-anchors-and-target-order` (ladder 1 / 1.618 / 2 / 2.618 / 4.236), `sbs-pivots-and-origin`
   (pivots are numbered 1-5 on the chart), and `risk-and-management`.

**Regenerating bars is NOT needed** — `.artifacts/research/bars/NQ_{1m,5m,15m,60m,D}.jsonl` already
cover 2026-01-02..06-05, which contains every in-scope fixture date. But `.artifacts/` is gitignored
and does not travel to the Mac; rebuild there with `research/build_bars.py` (~37 min single-core).
