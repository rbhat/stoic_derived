---
name: case-study-fixture-track
description: "The Vol 1-7 case-study PDFs are machine-readable fixture ground truth — text layer gives instrument/date/day-label, our bars reproduce the instructor's HCOM/LCOM exactly, and page-title dates are TRADE days not signal days"
metadata:
  type: project
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

The page date **D** is when you trade, and the arrows on the chart mark that trade day, not the flip
candle. Reading the title as a per-date candle classification would mislabel every one of these
fixtures.

**The parenthetical is a cycle-context label, not a per-date claim**, so the flip is *not* always
D-1 — do not build a fixed D-1 offset into anything. Red itself is a recorded human decision
(`close < open`); the data cannot discriminate the two candidate definitions, since they agree on
all 7 labelled dates. See [[red-day-definition]].

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

1. **WP-V exhaustive visual extraction** — the blocking prerequisite, because rule definitions
   live on slides no transcript contains ([[slide-text-not-in-transcripts]]). Plan:
   `docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`.
2. Chart-extraction pass over the 25 in-scope pages → per-fixture proposals for human review.
   Derive levels from `.artifacts/research/bars/` where possible; use the chart only for
   chart-exclusive facts.
3. Feed confirmed numbers into the 12 `unresolved_decisions`. vol2 p03 alone bears on
   `fib-anchors-and-target-order` (ladder 1 / 1.618 / 2 / 2.618 / 4.236), `sbs-pivots-and-origin`
   (pivots are numbered 1-5 on the chart), and `risk-and-management`.

**Bars are rebuilt on the Mac as of 2026-07-26** — `.artifacts/research/bars/NQ_{1m,5m,15m,60m,D}.jsonl`
cover 2026-01-02..06-05 (111 daily bars), which contains every in-scope fixture date. `.artifacts/`
is gitignored and does not travel; rebuild with `research/build_bars.py` (~31 min, 41.2M events).
Sessions `2026-03-20` and `2026-06-05` come out `quality != complete`.
See [[bars-match-education-not-tradingview]] for the series-choice finding and the
don't-read-a-file-mid-build trap.
