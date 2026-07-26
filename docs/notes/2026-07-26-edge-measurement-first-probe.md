# First Edge Measurement: Break-and-Retest on NQ 2026-H1

Date: 2026-07-26. Status: handoff note, written for a reader with no prior
context. Written under ADR-0021 (every derived number is presumed invalid until
adversarially audited).

Companions: `research/README.md` (how to reproduce), ADR-0011 (backtests are
observational and non-gating), ADR-0012 (the fill model), ADR-0013 (research
artifacts), `docs/notes/2026-07-25-slm-eval-learnings-and-gap-to-goal.md` (the
SLM side).

---

## 1. Why this exists — the finding that motivated it

The project's end goal is trading signals from a deterministic Python codebase,
built with the SLM's help, off a live Databento feed.

Auditing that goal surfaced an inverted ordering:

- **The claim that decides everything — "the resulting signals have positive
  expectancy" — had never been tested.** 3.2 GB of Databento NQ/ES trades sat
  in `data/historical/` and nothing had been asked of it. ADR-0011 says it
  outright: *"Current strategy-neutral fixtures prove mechanics but provide no
  edge claim."*
- **Enormous effort had gone into the SLM side, which cannot move that claim at
  its theoretical best.** The videos contain vocabulary and demonstrations, not
  specifications. `strategy/rulebook.yaml` proves it: 3 `executable_rule`
  entries, all `status: unknown`, each claiming *"No deterministic contract is
  validated"*, against **12 `unresolved_decisions`** that are exactly the
  numbers a predicate needs.

There is a tension worth naming plainly. VISION says *"I am NOT inventing a new
strategy."* But the source material is underdetermined, so whoever picks
`n_min=3` over `n_min=5` **is** inventing strategy. ADR-0011 then forbids an
optimizer, which is a sound anti-overfitting guardrail but leaves parameter
selection with no mechanism at all. Those choices are currently hiding inside
`unresolved_decisions` where they look like documentation debt rather than the
strategy design decisions they are.

This probe commits to one set of those numbers so the data can answer.

## 2. What was built

| path | what |
|---|---|
| `config/market_data/calendars/cme-equity-index-2026-h1-research-v1.json` | calendar covering 2026-01-01..2026-06-07 (none existed for the historical range) |
| `research/build_bars.py` | NQ trades → 1m/5m/15m/60m/D bars through the **production SP1 path** |
| `research/bnr_backtest.py` | the predicate + ADR-0012 fill model + bootstrap CI + random-entry null |
| `research/run_probe.py` | health check → baseline → sensitivity grid → disaggregation → null test |
| `research/test_fill_model.py` | 7 ADR-0012 conservative-fill invariants, all passing |
| `research/README.md` | reproduction, limitations, how to read the output |
| `research/exit_policies.py` | ceiling test + exit-policy sweep (answers "would a different target help?") |
| `research/probe_results.json` | the numbers behind this note |

Bars live in `.artifacts/research/bars/` (gitignored, regenerable in ~37 min).
Build log: `.artifacts/research/logs/build_bars.log`.

## 3. Data provenance and health — checked, clean

- Source: `data/historical/GLBX.MDP3__NQ__2026-01-01__2026-06-06.trades.dbn.zst`
  (646 MB, ~41M trade events), read through the repo's own roll-aware
  `plan_coverage` + `MultiTimeframeAggregator`, not a bespoke bar builder.
- Two `instrument_id`s appear (42002475 → 42004058): the 2026-03-22 contract
  roll, handled rather than crossed.
- 1m bar quality: 149,167 `complete`, 2 `degraded` out of 149,169.
- **The only trades excluded from bars fall in `[15:15:00, 15:29:59]`
  America/Chicago** — exactly the CME equity-index settlement halt, nothing
  scattered. That is the calendar working, not a data defect.
- Short sessions detected empirically from bar counts, including **2026-04-03
  (Good Friday)**.

### The calendar choice, and why it is deliberate

The research manifest declares **no session overrides**. The asymmetry is the
whole reason:

- omitting a real holiday is **benign** — the calendar expects a session, no
  trades arrive, no bars are emitted;
- asserting a holiday that actually traded would **silently delete a real
  trading day**.

So holidays are detected from the data afterwards rather than asserted from
memory. If this calendar is ever promoted beyond research, the overrides must
be sourced from CME and human-reviewed.

## 4. The predicate, stated exactly

Timeframes match the `Day` row of `rulebook.yaml`'s timeframe map — **setup 5m,
execute 1m** — with one deliberate omission: **the 60m HTF context filter is
NOT applied**, so this measures the trigger in isolation, not the full
multi-timeframe rule.

Long at PDH (short is the mirror at PDL):

1. **Level** = previous trading date's session high, derived from the 1m bars.
2. **Break**: a 5m bar closes ≥ level + `break_ticks`.
3. **Retest**: within `retest_bars` 5m bars, a bar whose low ≤ level +
   `retest_tol_ticks` and whose close ≥ level.
4. **Entry**: buy-stop at that bar's high + `entry_offset_ticks`.
5. **Stop**: that bar's low − `stop_buffer_ticks`. **Target**: `r_multiple` × risk.
6. **Reset**: one attempt per direction per trading date.

Committed parameters: `break_ticks=4`, `retest_bars=6`, `retest_tol_ticks=8`,
`stop_buffer_ticks=4`, `entry_offset_ticks=1`, `r_multiple=2.0`,
`min_stop_ticks=8`, `max_stop_ticks=400`, `entry_expiry_min=30`,
entry/exit slippage 1 tick each, fees 1 tick round turn, session 08:30–14:30 CT.

Fill model is ADR-0012 implemented literally and **tested**: stop wins ambiguous
bars, entry-bar target ignored, gaps through the stop fill at the worse open,
targets get no favorable gap, unresolved at roll. `research/test_fill_model.py`
asserts all seven.

## 5. RESULTS

Data: **41,165,185 trade events → 149,169 1m bars, 111 trading dates**,
2026-01-02 .. 2026-06-05. Health checked before any metric was read: 149,167
bars `complete`, 2 `degraded`; both roll `instrument_id`s present; short
sessions detected at 2026-03-20 and 2026-04-03 (Good Friday).

### The headline, with its error bar

| | |
|---|---|
| trades | **46** (from 60 setups; 14 cancelled/unfilled; 0 unresolved-at-roll) |
| win rate | 41.3% (19W / 27L) |
| expectancy | **+0.203 R** / +44.2 ticks per trade |
| bootstrap 95% CI | **[−0.225, +0.624]** — **includes zero** |
| t | 0.93 |
| total | +9.33 R over 5 months |
| max drawdown | −5.15 R |
| median risk | **222 ticks = 55.6 NQ points ≈ $1,112/contract** |

### The reference class — the number that actually decides it

Same trading date, same direction, same risk in ticks, same 2R geometry,
**random entry time**:

| | |
|---|---|
| observed mean | +0.2028 R |
| null mean | **+0.0837 R** |
| null 5th–95th pct | **[−0.1995, +0.4034]** |
| p (one-sided) | **0.2475** |

**The observed result sits inside the null band.** Random entry with identical
geometry produces a result at least this good about one time in four. Note the
null mean is *positive*: a 2R target with a session flatten is mildly
profitable on random entries in this sample, which is exactly the artifact a
reference class exists to catch.

### Three things the headline hides

1. **64% of the total comes from three trades.** Top 3 winners = +5.99 R of
   +9.33 R. Excluding them: +3.33 R over 43 trades = **+0.077 R**.
2. **The monthly signs alternate**: Jan +0.19 (n=10), Feb −0.15 (n=7),
   Mar +0.28 (n=7), Apr −0.26 (n=8), May +0.51 (n=13), Jun n=1. Every cell is
   n<20, so these are counts, not rates. There is no stable month.
3. **`max_stop_ticks` still flips the sign non-monotonically** on the full
   sample: 120 → +0.483 (n=18), 200 → **−0.043** (n=27), 400 → +0.203 (n=46),
   800 → +0.092 (n=49).

### Would a different profit target help? Open, with a specific lead

`research/exit_policies.py`. Not answered by trying targets until one looks
good (optimising on n=46 noise), but by asking whether the entries carry
information an exit policy could monetise — always real vs the random-entry
null under identical treatment.

**Test 1 — the ceiling.** Max favourable excursion reachable *before the stop
is hit*: the best price any exit rule could ever take. Real mean **1.761** vs
null **1.740**, oracle p=**0.475**. So **no policy that monetises _average_
excursion can help.** That is the bound this test establishes — and it is the
only one it establishes.

**Test 2 — policy sweep**, real vs null, one-sided p:

| policy | real E[R] | null E[R] | p |
|---|---|---|---|
| fixed 1.0R | 0.125 | 0.052 | 0.320 |
| fixed 1.5R | 0.190 | 0.071 | 0.240 |
| fixed 2.0R | 0.206 | 0.094 | 0.260 |
| fixed 3.0R | 0.163 | 0.101 | 0.365 |
| runner (no target, flatten) | **−0.061** | 0.153 | 0.785 |
| breakeven at 1R | **0.343** | 0.148 | 0.130 |
| half at 1R, rest 2R | 0.242 | 0.130 | 0.240 |
| ceiling oracle | 1.756 | 1.734 | 0.475 |

No policy clears its null. `runner_flatten` is *negative* and worse than its
own null — letting these run to the session flatten is actively harmful.

**Test 3 — shape. This is the open lead.** Equal means can hide differences
that cancel, and here they do. Each feature of the real MFE distribution
against the null's per-iteration distribution of the same feature:

| feature | real | null mean | null p05 | null p95 | p(null ≥ real) |
|---|---|---|---|---|---|
| mean | 1.761 | 1.740 | 1.317 | 2.208 | 0.475 |
| **median** | **1.287** | 0.977 | 0.645 | 1.346 | **0.075** |
| p90 | 3.768 | 4.428 | 3.082 | 6.524 | 0.760 |
| **≥1R** | **56.5%** | 47.8% | 37.0% | 58.7% | **0.105** |
| **≥2R** | **39.1%** | 28.7% | 19.6% | 39.1% | **0.060** |
| ≥3R | 21.7% | 18.4% | 10.9% | 28.3% | 0.315 |

**Real entries reach the 1R–2R band more reliably; the null owns the fatter
extreme tail.** Those offset exactly, which is why the means match and why
"no exit policy can help" would overstate test 1.

Nothing here is significant at n=46 — the strongest is ≥2R at p=0.060, and
with six features examined that is what chance produces. But the direction is
consistent across median, ≥1R and ≥2R, and it is coherent with `breakeven_at_1R`
being the best real policy in test 2 (0.343): a policy that protects once 1R is
reached is precisely what exploits reliability in that band rather than tail
capture.

**Treat this as a hypothesis to retest, not a finding.** It is exactly the
shape of thing that either sharpens or dissolves at 4× the sample (next action
1). The concrete question for a future session: *do real entries reach the
1R–2R band more reliably than random, and does a reliability-harvesting exit
(breakeven, partial scale-out, trail-after-1R) beat its null once n supports
it?* Reproduce with `.venv/bin/python research/exit_policies.py`, test 3.

### Verdict

**No edge demonstrated.** The expectancy is positive but statistically
indistinguishable from zero, indistinguishable from random entry with the same
geometry, carried by three trades, unstable month to month, and sign-unstable
in the one parameter that most controls sample selection.

This is a clean negative result, not a failed measurement: the pipeline is
healthy, the fill model is conservative and tested, and the rule as
parameterised simply does not show an edge on NQ over these 111 dates.

Two things it is **not**: it is not a verdict on the Stoic strategy (the HTF
context filter is absent, and the level definition is an untested choice), and
it is not a verdict on break-and-retest generally (n=46 can only detect a large
effect). It **is** a verdict on the idea that a first probe would obviously
print money.

### The stop is correctly placed — checked, and it is not the problem

An earlier draft of this note claimed the wide stop was a design defect and
proposed tightening it using 1m structure. **That was wrong on both counts**
and is retracted here.

**Timeframe alignment.** A stop derived from a lower timeframe than the signal
gets hit by noise before the higher-timeframe thesis can play out. A 5m setup
must carry a 5m-aligned stop and target; the 1m timeframe's job is entry
precision, which is exactly what it does here (ADR-0012 range-touch fills).
The implemented stop already sits beyond the **5m** retest bar's extreme, so it
was 5m-aligned all along — the proposed "fix" would have been a regression into
precisely the noise-stop failure mode.

**And the evidence says the geometry is fine:**

| | |
|---|---|
| stopped trades, median MFE | **+0.51 R** (max +1.92 R) |
| stopped trades reaching ≥1.0 R first | 7 of 27 |
| stopped trades, median hold | **10 minutes** |
| target trades, median hold | 42 minutes |
| 2R distance vs median daily range | **25%** — reachable, and reached 18 of 46 times |

Short holds with *low* MFE is clean, fast invalidation. Noise-stopping would
look like short holds with *high* MFE. It does not.

**R-multiple sweep, stop held fixed** — the decisive one:

| R | n | win% | E[R] | 95% CI |
|---|---|---|---|---|
| 1.00 | 46 | 56.5% | +0.123 | [−0.182, +0.428] |
| 1.50 | 46 | 47.8% | +0.188 | [−0.193, +0.569] |
| 2.00 | 46 | 41.3% | +0.203 | [−0.225, +0.624] |
| 3.00 | 46 | 32.6% | +0.159 | [−0.315, +0.670] |

Expectancy is flat and win rate decays exactly as pure geometry predicts. A
setup carrying directional information would show some R multiple pulling
ahead. **This strengthens the negative result**: mis-specified stop/target
design is eliminated as an explanation for it.

**What the wide stop does cost is position sizing, not expectancy.** R
normalisation means stop size cannot move E[R]. But 222 ticks ≈ 55.6 NQ points
≈ **$1,112 per NQ contract** per trade. Risking 1% of a $50k account is $500 —
less than a single NQ contract on this setup. Trading it at that account size
means **MNQ micros** (~$111/trade), or a larger account. That is an account
arithmetic constraint to plan around, not a defect to fix.

## 6. Methodology findings (these outlive the numbers)

1. **My own parameter was the binding constraint, and it decided the sign of
   the answer.** The first run set `max_stop_ticks=120` and silently discarded
   **83% of qualifying setups** — a sweep-and-reclaim bar is by construction a
   *wide* bar (observed retest-bar ranges 121–553 ticks), and NQ near 26,000
   makes tick-denominated stops far larger than intuition from lower index
   levels. Across the band the expectancy read +1.39 (n=5), −0.35 (n=9),
   +0.28 (n=14), +0.19 (n=15). **One arbitrary number flipped the verdict.**
2. **The funnel is the diagnostic, not the P/L.** 331 breaks → 109 retests in
   window → 46 in RTH → 8 taken told me instantly where the strategy was being
   strangled. Any future rule should print its funnel first.
3. **A backtest without a reference class is not evidence.** 2R geometry
   produces plausible-looking equity curves from noise. The random-entry null
   (same day, same direction, same risk, random entry time) is the control that
   makes the result falsifiable, and it is cheap.
4. **n < 20 means counts, not rates** (ADR-0021 §8). Almost every cell in the
   grid is under that bar. An 80% win rate on 5 trades is a coin sequence.
5. **Tick-denominated parameters are not portable across price levels.**
   Anything expressed in ticks needs restating as a fraction of ATR or of the
   level, or it silently changes meaning as NQ moves.

## 7. What this does NOT measure (blindness statement, ADR-0021 §6)

- **No HTF context filter.** The `Day` rule is htf 60m + setup 5m + execute 1m;
  only the last two are implemented.
- **Session vs RTH levels.** Levels are the previous *Globex session*
  high/low. Many price-action traders mean the previous *RTH* high/low. This is
  an untested modeling choice that moves the level on most days.
- **One instrument, one regime, one window.** NQ, 2026-01-02..2026-06-06,
  ~110 trading dates. No walk-forward; the whole window is one sample.
- **No ES**, though `data/historical/` has it (2.5 GB, 2025-09-01..2026-06-06),
  which would roughly double the sample and add an instrument.
- **Signals-only economics.** Results are ticks and R. ADR-0012 holds dollar
  P/L until an approved contract economics manifest exists.

## 8. Next actions, in order

1. **Widen the sample before touching the rule.** `data/historical/
   GLBX.MDP3__ES-NQ__2025-09-01__2026-06-06.trades.dbn.zst` (2.5 GB) carries
   **both ES and NQ over ~9 months** — verified via `stoic-data inspect`: roots
   `['ES','NQ']`, 8 instrument mappings, 2025-09-01..2026-06-06. That is
   roughly **4× the current sample** (NQ alone, 5 months), and it is the
   cheapest way to move every cell out of the n<20 regime. Requires extending
   the research calendar back to 2025-09-01. **No new modeling — do this
   first.** Budget ~2.5 h of aggregation at the observed 18k events/s.
2. **Walk-forward split.** Report the window in halves/quarters rather than
   pooled. A result that only exists in one quarter is not a result.
3. **Test the RTH-level variant** against the session-level one. This is a
   single-parameter change to `derive_daily` and it is the most likely
   mis-modeling in the probe.
4. **Add the 60m HTF context filter** so the `Day` rule is actually the `Day`
   rule, then re-measure. Only after 1–3, so the sample can support it.
5. **Keep the stop 5m-aligned; do not tighten it with 1m structure.** A stop
   below the signal timeframe is hit by noise before the 5m thesis resolves.
   1m is for entry precision only. Verified not to be the problem (§5): fast,
   clean invalidation and a flat R sweep. If stop *placement* is ever revisited,
   the open question is which **5m** structure defines invalidation — the retest
   bar's extreme (current) vs the reclaimed level itself — and that is the
   `risk-and-management` entry in `unresolved_decisions`, a strategy decision
   for the human, testable as a variant.
6. **Plan sizing around ~$1,112/contract risk**, or trade MNQ. This is account
   arithmetic, not a rule change, but it decides whether the setup is tradeable
   at a given account size.
7. **Restate every tick parameter as a fraction of ATR** so parameters survive
   a change in price level.
8. **Retest the exit-shape lead once n supports it** (§5, test 3). Real entries
   reach the 1R–2R band more reliably than random (median p=0.075, ≥2R p=0.060)
   while the null owns the fatter tail; the two cancel in the mean, so the
   ceiling test bounds only *average*-excursion policies. Concrete question:
   does a reliability-harvesting exit — breakeven-at-1R, partial scale-out,
   trail-after-1R — beat its null at 4× sample? `research/exit_policies.py`
   test 3 is the harness; add trailing variants there. Do this AFTER action 1,
   never before: at n=46 it would be fitting noise.
9. **Only then** decide whether break-and-retest is worth keeping, and whether
   the SLM's batch-annotation path (see the SLM note) is worth resuming to
   scale from one setup to several.

**Do not** tune parameters against these results. ADR-0011 forbids an
optimizer, and with cells this small, tuning would be fitting noise — the
sensitivity grid above is the demonstration of exactly how easy that would be.

## 9. Where to find everything

- Probe code and README: `research/`
- Numbers: `research/probe_results.json`
- Bars (regenerable, gitignored): `.artifacts/research/bars/`, summary in
  `build_summary.json`, log in `.artifacts/research/logs/build_bars.log`
- Calendar: `config/market_data/calendars/cme-equity-index-2026-h1-research-v1.json`
- Source data: `data/historical/` (`.dbn.zst` are gitignored, kept in Drive)
- The rulebook gap this addresses: `strategy/rulebook.yaml` →
  `unresolved_decisions`
- Environment: `.venv` (Python 3.14, databento 0.82). **Not**
  `.artifacts/training/venv` — that is the 3.12 CUDA venv for the SLM side.
