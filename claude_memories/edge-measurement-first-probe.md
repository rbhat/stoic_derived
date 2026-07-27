---
name: edge-measurement-first-probe
description: The 2026-07-26 NQ probe — what it actually measured (a thin proxy, not the method), why its conclusion was retired, and which infrastructure survives for reuse
metadata:
  type: project
---

**Read [[signal-fidelity-over-edge-revalidation]] first — it is the rule this probe violated.**

**On `main`** — the probe code (`research/bnr_backtest.py`, `build_bars.py`, `exit_policies.py`,
`test_fill_model.py`) is committed there. The old `research/edge-measurement-probe` branch was
deleted 2026-07-25 once confirmed to hold no unique commits; earlier revisions of this memory said
"not merged to main", which was wrong. Full record and the direction correction:
**`docs/notes/2026-07-26-edge-measurement-first-probe.md` §0** (§0 supersedes §1 and the §8
ordering). `research/README.md` has reproduction steps.

## What it was, and what it actually measured

`research/bnr_backtest.py` fixes **one invented parameterization** of break-and-retest: no HTF map,
no HCOM/LCOM, no POI location filter, no chop zone, no SFP, no SBS entry model, no confluence
score, no management — a fixed 2R bracket. All 12 `unresolved_decisions` in `strategy/rulebook.yaml`
were guessed. So the measured object shares a name with the taught setup and little else.

Numbers (real, keep them, but they describe the proxy): 41,165,185 trade events → 149,169 1m bars,
111 dates, NQ 2026-01-02..06-05. 46 trades, E[R] +0.203, bootstrap 95% CI [−0.225, +0.624].
Random-entry null p=0.2475. 64% of total R from 3 trades. `max_stop_ticks` flips the sign
non-monotonically. Exit-policy sweep: none clears its null; shape test hints real entries reach the
1R–2R band more reliably (median p=0.075, ≥2R p=0.060) while the null owns the fatter tail.

## Why the conclusion was retired (not the data — the framing)

1. A null on a thin proxy is evidence about the proxy, not about the method.
2. The random-entry null held **day, direction and risk fixed** — it hands the null three of the
   four places the edge lives (day selection, trapped-side direction, POI location) and asks only
   whether the entry *minute* matters under fixed 2R geometry. A profitable system fails that test.
3. It was used as a project gate, which ADR-0011 ("observational and non-gating") and VISION
   ("does NOT gate going live with signals/dashboard") both forbid. n=46, one instrument, five
   months cannot steer project direction.

Also wrong: the note's claim that the SLM side "cannot move the goal." The **specification is the
bottleneck**, and mining it out of the education is exactly what that path is for.

## What survives and should be reused

`research/build_bars.py` (trades → bars via the production SP1 path), the **ADR-0012 fill model
with 7 passing invariant tests** (`research/test_fill_model.py`), the research calendar, R
accounting, funnel-first diagnostics, n<20 → counts-not-rates, and restating tick parameters as ATR
fractions. Plus two standing user corrections: **keep the stop 5m-aligned, never tighten it with 1m
structure** (1m is entry precision only), and the ES+NQ widening below.

## Carried-over work items (not a research program — inputs to one)

- `data/historical/GLBX.MDP3__ES-NQ__2025-09-01__2026-06-06.trades.dbn.zst` has **both roots over
  ~9 months** (~4× the NQ-only sample). Needs the research calendar extended to 2025-09-01.
  ~2.5 h aggregation at 18k events/s. Do this whenever a measurement is next needed.
- Sizing is account arithmetic, not a rule change: 222 ticks ≈ $1,112/NQ contract → MNQ on a small
  account.
- Session-level vs RTH-level `derive_daily` is an open modeling question the material should
  settle, not a grid.

## Gotchas

- Use **`.venv`** (Python 3.14, databento 0.82) for all market-data/research work.
  `.artifacts/training/venv` is the 3.12 CUDA venv for the SLM only. See [[eval-comparison-wp-progress]].
- `.artifacts/` is gitignored — research **code** lives in `research/`, regenerable bars go to
  `.artifacts/research/bars/`. See [[artifact-locality]].
- Bar rebuild is ~37 min single-core; log at `.artifacts/research/logs/build_bars.log`.
- `uvx ruff check --fix research/` is clean; repo enforces line-length 100 ([[ruff-always-fix]]).
- Data health verified: excluded trades fall **only** in [15:15:00, 15:29:59] Chicago (CME
  settlement halt). Don't re-investigate.
- Untracked `data/historical/GLBX.MDP3__NQ__...T16"45"00.symbology.json` is a Windows-name
  duplicate of an already-tracked file; left alone deliberately.
