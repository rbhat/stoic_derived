# SP3 - Observational Backtest, Walk-forward, and Paper Design

*Design status: accepted for implementation*

## 1. Objective

SP3 replays immutable SP1 batches through the unchanged public SP2 engine and
measures the resulting signals. It is a parallel validation track: its results
cannot configure, publish, enable, disable, tune, or gate live signals.

The current repository has no signed, semantically complete strategy release.
Production SP3 therefore reports `blocked` and produces zero trades. Private
strategy-neutral fixtures verify simulator mechanics without becoming trading
rules or performance evidence.

## 2. Brainstorm Decisions

### 2.1 Keep one causal engine boundary

Production composition calls `SignalEngine.from_release(...)` and then only
`SignalEngine.ingest(...)`. SP3 never interprets rulebook YAML, evaluates a
predicate, computes confidence, or accepts a rule/threshold/feature override.
Every engine suppression is retained as an exclusion fact, never scored as a
loss or silently discarded. Readiness without a pinned signed release calls
that same public boundary with no release identity; it never loads the
authoring candidate.

### 2.2 Simulate one independent unit-risk signal

V1 has no broker, position sizing, portfolio allocation, or netting. Each
signal is observed independently as one simulated contract. Results are exact
integer ticks and reduced rational R. Dollar P/L is unavailable until a
versioned NQ/ES contract-value and fee schedule is approved.

An explicit immutable simulation policy separately pins non-negative integer
`entry_slippage_ticks`, `exit_slippage_ticks`, and
`fees_ticks_round_turn`, plus the one-minute observation model and conservative
intrabar handling. Trigger touches use planned levels. Simulated prices include
adverse slippage, gross ticks use those simulated prices, and net ticks subtract
fees exactly once. Gross/net R use the planned-risk denominator. Zero-cost
assumptions are allowed only when explicitly declared; they are never an
implicit default.

### 2.3 Use only future complete one-minute bars

A close-bar signal cannot fill on its decision bar. The earliest eligible
observation is a complete one-minute bar from the same physical lineage whose
end is strictly later than `signal_ts_ns`. Degraded bars and intervals covered
by structured gaps are unavailable.

Entry requires the planned entry to lie inside the future bar range. On the
entry bar, a touched stop wins conservatively; a touched target is ignored
until a later bar because OHLC cannot prove that target occurred after entry.
On later bars, stop wins any stop/target tie. Stop gap-through exits at the
worse open; target gap-through receives no favorable improvement. All prices
include explicitly declared adverse slippage.

These are versioned simulation assumptions, not changes to Stoic strategy.

### 2.4 Enforce the session cutoff without inventing a price

The complete one-minute bar whose `end_ns` converts to exactly 13:58:00 in
`America/Los_Angeles` can flatten Scalp, Day, and Swing observations. Position
observations are exempt. DST is resolved with `zoneinfo`; no fixed UTC offset
is permitted. If that exact cutoff bar is absent, degraded, or covered by a
known gap, SP3 reports an unresolved observation and a typed warning rather
than fabricating a late or interpolated fill.

At the cutoff, pending non-Position observations become unresolved without a
fabricated entry. Signals at or after the cutoff cannot carry into the next
session. At a physical contract roll, every pending or open observation becomes
`unresolved:contract_roll` before the lineage is retired. Position is exempt
from the daily cutoff, never from the roll boundary.

### 2.5 Report descriptive evidence, never promotion

Metrics are produced per NQ/ES root, physical instrument, Signal Type, execute
timeframe, direction, and setup. Root/timeframe summaries may combine completed
physical contracts only within one root and must retain the contract count.

Closed-trade metrics include sample size, win rate, expectancy/average R,
average win/loss R, and maximum drawdown in R and ticks. Pending, open,
unresolved, and suppressed observations are separate denominators. Samples
below 30 closed trades receive `insufficient_sample`; multiple partitions
receive a selection/multiplicity warning. No metric or confidence interval
creates a pass/fail result.

Session, bull/bear, trend, and volatility regime splits remain unavailable
until their causal classifiers and half-open boundaries are separately
specified and reviewed.

### 2.6 Make walk-forward chronological and non-optimizing

A `ChronologicalReplayPlan` is the non-optimizing, walk-forward-shaped
historical contract. It contains explicit half-open warm-up, context, embargo,
and evaluation intervals. Folds are chronological, evaluation intervals never
overlap across folds, and every interval ends no later than the next begins.
Warm-up/context input may build a fresh engine's state, but decisions before
`evaluation_start` cannot create observations or enter metrics. Only signals
with `evaluation_start <= signal_ts_ns < evaluation_end` are admitted; all open
or pending observations are unresolved at the fold end.

Context windows are descriptive only: SP3 has no optimizer, candidate
selection, fitting, promotion, or parameter sweep API. Every historical result
is labeled `retrospective_replay`; an interval named evaluation is never
described as genuine out-of-sample evidence.

Paper mode is labeled `paper_forward` and uses the same incremental outcome
tracker over committed live batches. Its content-addressed checkpoint records
the pinned release, policy, plan, accepted batch identities, and active state
for idempotent restart. A declared horizon is operationally complete only when
it ends and every observation is closed or explicitly unresolved. Performance
never gates live readiness.

### 2.7 Emit immutable, comparable artifacts

Canonical input identities, release identity, simulation policy, replay plan,
and pinned simulator/metrics/artifact schema versions determine a `plan_id`.
Ordered signals, suppressions, simulated observations, trades, warnings,
metrics, and the `plan_id` determine the content-addressed `run_id`. No wall
clock, locale, random seed, hostname, or absolute path enters reproducible
content.

The manifest itself is excluded from the `run_id` digest to avoid a recursive
identity. It pins the digest and row count of every other artifact, declares
`execution: false` and `orders_placed: 0`, and states that every simulated fill
is a research observation only. Explicit policy limits bound active
observations, active lineages, retained gaps, accepted batches, output records,
and artifact bytes; exceeding a bound fails closed before publishing a
completed run.

Artifacts are canonical UTF-8 JSON/JSONL. The final target must not exist. SP3
writes a sibling temporary directory, flushes and synchronizes files, writes
the manifest last, then atomically renames the directory into place:

```text
run_manifest.json
signals.jsonl
suppressions.jsonl
fills.jsonl
trades.jsonl
equity.jsonl
metrics.json
warnings.jsonl
```

The manifest pins every artifact hash and row count. SP3 refuses every existing
target, including an empty directory.

## 3. Domain Contracts

### Input

- ordered immutable `FinalizedSeriesBatch` values;
- one pinned signed SP0 release through `SignalEngine.from_release`;
- explicit `SimulationPolicy`;
- optional explicit `ChronologicalReplayPlan`.

Every batch remains physical-lineage scoped. The SP3-owned input codec derives
canonical batch bytes and identities from the unchanged SP1/SP2 lineage,
watermark, ordered bar bytes, and ordered gap bytes. Callers must provide
batches in canonical order by watermark, lineage identity, and canonical batch
bytes; SP3 rejects non-canonical order instead of silently sorting it.
Per-lineage watermarks must remain monotonic. Exact repeated batch identities
are idempotent; same-interval conflicting content fails closed. Historical CLI
input is canonical batch JSONL, not raw DBN and not authoring YAML.

### Lifecycle

`pending -> open -> closed` is the only realized-trade path. A pending or open
observation may instead become `unresolved` at a declared data/fold boundary.
Duplicate signal IDs and replayed one-minute bars are idempotent. A trade never
crosses a physical contract roll. Explicit limits bound active lineages,
active observations, retained gaps, accepted batches, output records, and
artifact bytes.

Within each accepted batch, SP3 first ingests the batch through SP2, registers
equal-time decisions by signal ID, and only then considers complete one-minute
bars ordered by `(end_ns, identity)`. Bars ending at or before a signal
timestamp can never fill it. This allows a batch to contain both decision
context and a strictly later eligible observation without lookahead.

### Output

- `SimulatedFillRecord`: entry/target/stop/session-flatten research
  observation, exact ticks, event time, policy ID, and source bar ID;
- `TradeRecord`: full signal provenance, state, fills, gross/net ticks, exact
  gross/net R, and terminal reason;
- `MetricRecord`: explicit grouping key, denominator counts, exact measures,
  uncertainty metadata, and warning codes;
- `ExclusionMetric`: suppression counts grouped only by provenance SP2
  supplies; direction/setup are never inferred;
- `RunWarning`: typed, deterministic, content-addressed evidence limitation;
- `BacktestResult`: immutable ordered records, evidence class, blocked/complete
  status, readiness blockers, and canonical manifest identity.

## 4. Causality and Accounting

- Bars at or before the decision timestamp cannot fill that signal.
- Only complete one-minute bars from the signal's exact lineage are eligible.
- A known overlapping data gap makes the bar unavailable.
- Directional gross ticks are `long: exit - fill`, `short: fill - exit`.
- Simulated prices include adverse slippage; net ticks subtract explicit
  round-turn fees exactly once.
- Gross/net R divide by planned signal risk `abs(entry - stop)`.
- Equity ordering is `(exit_ts_ns, trade_id)`.
- Maximum drawdown is the greatest peak-to-subsequent decline in cumulative
  net R/ticks; open and unresolved observations do not enter the curve.

## 5. Failure and Readiness

- A blocked SP2 release yields a successful safety result with status
  `blocked`, readiness blockers, and no simulated population.
- Invalid, conflicting, non-canonical, or behind-watermark input fails before
  publishing a completed artifact.
- Missing data, ambiguous observation ordering, absent cutoff price, and end-of-data
  exposure produce typed warnings and unresolved records.
- No SP3 public API contains `promote`, `enable_live`, strategy mutation, or
  live-readiness output.

## 6. Acceptance Criteria

- Direct SP2 decisions and decisions observed through SP3 are byte-identical.
- Appending future input cannot change any earlier decision or fill.
- Long/short entry, stop, target, tie, gap, cost, and 1:58pm DST behavior are
  deterministic and tick exact.
- Duplicate inputs are idempotent; contracts and instruments never mix.
- Metrics reconcile exactly to terminal lifecycle records and cover all Vision
  measures per instrument and execute timeframe.
- Walk-forward folds are chronological, fresh-engine, immutable, and contain
  no optimization path.
- Same canonical inputs produce byte-identical artifacts and run IDs.
- Current production readiness is blocked with zero trades.
- Historical folds are labeled `retrospective_replay` and never claim genuine
  out-of-sample evidence.
- Paper checkpoints restart idempotently and remain blocked/zero without a
  signed semantically complete release.
- Every manifest states `execution: false`, `orders_placed: 0`, and simulated
  observations only.
- SP2 imports no SP3 module and live output is identical before and after any
  good or poor backtest result.

## 7. Decisions

- [ADR-0011](../../architecture/adr/0011-observational-non-gating-backtests.md)
- [ADR-0012](../../architecture/adr/0012-conservative-causal-fill-model.md)
- [ADR-0013](../../architecture/adr/0013-content-addressed-research-artifacts.md)
