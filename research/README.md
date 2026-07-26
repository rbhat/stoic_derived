# research/ — edge measurement probes

Research artifacts under ADR-0013. **Nothing here is a rulebook release, a
signal source, or a live gate** (ADR-0011: backtests are observational and
non-gating). Results are descriptive.

## Why this exists

`strategy/rulebook.yaml` carries three `executable_rule` entries whose every
`claim` reads *"No deterministic contract is validated"*, and twelve
`unresolved_decisions` that are exactly the numbers a predicate needs (pivot
detection, break/retest parameters, stop placement, R calculation, confluence
weights, session boundaries). Until something commits to those numbers, the
3.2 GB of Databento NQ/ES data in `data/historical/` has never been asked
whether the strategy has positive expectancy — which is the only claim that
decides whether the project's end goal is reachable.

`bnr_backtest.py` commits to one set of those numbers so the data can answer.

## Files

| file | what it does |
|---|---|
| `build_bars.py` | NQ trades → 1m/5m/15m/60m/D bars through the **production SP1 path** (`MultiTimeframeAggregator`, real calendar, roll-aware coverage planning). Writes to `.artifacts/research/bars/`. |
| `bnr_backtest.py` | Break-and-retest predicate at PDH/PDL + the ADR-0012 fill model + metrics, bootstrap CI, and the random-entry reference class. |
| `run_probe.py` | Runs the baseline parameter set, the full sensitivity grid, and the null test. Writes `.artifacts/research/probe_results.json`. |

## Reproduce

```bash
# 1. bars  (~37 min, single core, ~18k trade-events/sec, ~150k 1m bars)
.venv/bin/python research/build_bars.py       # log: .artifacts/research/logs/build_bars.log

# 2. probe (~seconds once bars exist)
.venv/bin/python research/run_probe.py
```

Uses `.venv` (Python 3.14, `databento` 0.82). Do **not** use
`.artifacts/training/venv` — that is the 3.12 CUDA venv for the SLM side.

## Calendar note (deliberate)

`config/market_data/calendars/cme-equity-index-2026-h1-research-v1.json`
declares **no session overrides**. The choice is asymmetric on purpose:

- omitting a real holiday is **benign** — the calendar expects a session, no
  trades arrive, no bars are emitted;
- asserting a holiday that actually traded would **silently delete a real
  trading day**.

Verified empirically: the only trades excluded from bars fall in
`[15:15:00, 15:29:59]` America/Chicago — exactly the CME equity-index
settlement halt, nothing scattered. That is the calendar working correctly.

## What the fill model does (ADR-0012, implemented literally)

- fill observation starts **strictly after** the signal bar's end, on complete 1m bars
- entry requires a **range touch** of a planned level
- **stop wins** any bar where both stop and target are touchable
- a target touched on the **entry bar is ignored** unless confirmed later
- gaps through the stop fill at the **worse open**; targets get **no favorable gap**
- entry slippage, exit slippage, and round-turn fees are explicit **integer ticks**
- non-Position flatten on the 1m bar whose end is **13:58:00 America/Los_Angeles**
- a position becomes **unresolved at a physical contract roll** rather than crossing it

Results are reported in **ticks and R**. ADR-0012 holds dollar P/L until an
approved contract economics manifest exists; any dollar figure derived from
this output is illustrative arithmetic, not a system output.

## Reading the output

Read in this order, and stop at the first one that fails:

1. **Trade count.** ADR-0021 §8: cells with n < 20 are counts, never rates.
2. **The reference class.** Same day, same direction, same risk, *random*
   entry time. If the observed mean sits inside that null band, the setup's
   timing carries no information and the result is 2R geometry plus drift.
3. **The bootstrap CI on expectancy.** A point estimate with no error bar is
   not a result.
4. **The sensitivity grid.** Every cell is reported and **no cell is
   selected** — ADR-0011 forbids an optimizer, and picking the best cell is
   optimizing. If the sign of expectancy flips across the grid, the grid is
   the finding.

## Known limitations (all material)

- **No HTF context filter.** `rulebook.yaml` maps `Day` to htf 60m / setup 5m /
  execute 1m / manage 5m. This probe implements setup 5m + execute 1m only, so
  it measures the trigger in isolation, not the full multi-timeframe rule.
- **Levels are the previous *session* (Globex) high/low**, derived from the 1m
  bars themselves. Many price-action traders mean the previous *RTH* high/low.
  This is an untested modeling choice and it moves the level on most days.
- **One attempt per direction per trading date.** A "reset" rule, chosen not
  measured.
- **NQ only, 2026-01-02 .. 2026-06-06.** One instrument, one regime, ~110
  trading dates.
- **No walk-forward.** The whole window is one sample.
