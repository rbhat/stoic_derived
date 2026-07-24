# SP2 - Deterministic Signal Engine Design

*Design status: accepted for implementation*

## 1. Objective

SP2 turns immutable SP1 bars and one pinned, signed SP0 release into immutable
signal decisions for NQ and ES. It is a pure deterministic module: it has no
network, model, broker, execution, ledger, wall-clock, or backtest dependency.

SP2 succeeds when:

1. identical release bytes and finalized bars produce byte-identical decisions;
2. a signal is published only when every Vision-required field is filled;
3. evaluation is closed-bar, causal, tick-exact, and isolated by physical
   contract and market-data semantics;
4. invalid, incomplete, ambiguous, or unsupported inputs produce typed
   suppressions and never a partial signal;
5. SP3 and the live path invoke the same engine without configuring its rules.

## 2. Brainstorm Decisions

### 2.1 Separate engine capability from strategy readiness

The repository rulebook is deliberately not publishable. Its exact setup,
entry, stop, target, confluence, session, and feature semantics still require
source mining and human approval. In addition, the v1 release grammar does not
bind a rule to a Trade Type or qualify operands by `htf`, `setup`, or `execute`
role. Allowlisted derived and confluence feature names do not yet define their
calculators or predicates, confidence has no qualification threshold, and no
approved repeated-setup rearm policy or market-data profile binding exists.

SP2 therefore has two distinct readiness gates:

- SP0 release readiness: signature, pinned hash, provenance, and complete
  validated profiles;
- SP2 semantic readiness: an unambiguous Type/role binding and deterministic
  feature implementations.

Neither gate fills missing strategy semantics. The current production
composition reports a typed blocker and emits zero signals. Strategy-neutral
fixtures exercise the complete engine substrate without becoming live rules.

### 2.2 Compile once to a closed typed program

SP2 accepts only `load_published_release(...)` output. It converts JSON
mappings into frozen typed values and rejects duplicate profile keys, unknown
shapes, missing semantic bindings, unsupported feature calculators, or
ambiguous selection. A ready program covers every
Type/setup/direction combination; partial Type coverage cannot silently omit a
signal family. Evaluation does not interpret authoring YAML or access `edu/`.

The expression vocabulary is closed: comparisons, Boolean composition, and
bounded temporal operations. It never permits code, imports, callbacks,
plugins, network access, or model calls.

### 2.3 Evaluate only committed causal snapshots

Bars enter in committed batches carrying `finalized_through_ns`. SP2 processes
all bars at the same end timestamp atomically. For an execute bar ending at
`T`, every selected bar must end at or before `T`; equal ends are eligible and
later bars are invisible. Evaluation waits until the finalization watermark is
strictly greater than `T`, so same-end fragments may arrive in more than one
batch without revising an earlier decision.

A snapshot uses exactly one lineage:

- source;
- root and continuous symbol;
- physical `instrument_id`;
- calendar fingerprint;
- aggregation fingerprint;
- market-data schema.

SP2 never joins through logical `series_id` alone and never crosses a contract
roll. Missing or degraded required bars, structured coverage gaps, and
insufficient bounded lookback suppress evaluation. SP2 does not fabricate or
repair bars.

Bars within one physical lineage and timeframe cannot overlap. Once retained
history has advanced beyond a gap, that gap is causally incapable of affecting
a present or future admissible snapshot and is pruned. Retained gap state has a
hard fail-closed bound.

### 2.4 Use exact values and content-addressed output

Market prices remain integer ticks. Signal entry, stop, and target are positive
integer ticks. R is stored as a reduced integer numerator and denominator;
canonical output also exposes its exact decimal string without binary float.
Confidence is a bounded integer score from the signed rule formula, never a
model output.

Published constants carry an explicit unit. Point-valued prices are converted
exactly through the signed 0.25-point market binding; tick and quantity
constants must already be integral. Unitless constants cannot compile.

`signal_ts_ns` is the execute bar's UTC `end_ns`, not machine time. A signal
pins the release file SHA, rulebook version, rule ID, engine/schema version,
physical instrument, Type, setup/entry model, and every causal input bar ID.
`signal_id` is SHA-256 over the canonical record excluding `signal_id`.

### 2.5 Dedupe by identity, never by market values

At-least-once replay of an exact bar cannot create a second logical signal.
Different Types, rules, directions, or physical contracts remain distinct even
when their timestamp and prices match. An in-process exact replay is an
idempotent no-op while its bounded history is retained. Older
behind-watermark input is rejected and cannot create a duplicate; after
restart, SP4 performs durable deduplication by `signal_id`.

### 2.6 Keep backtesting observational

SP3 supplies bars to the same public engine and consumes its decisions. SP3
cannot inject rules, thresholds, feature values, or parameters into SP2 and
cannot publish or gate live releases.

## 3. Fixed Timeframe Plans

| Type | HTF | Setup | Execute | Manage |
|---|---|---|---|---|
| Scalp | 15m | 5m | 1m | 5m |
| Day | 60m | 5m | 1m | 5m |
| Swing | D | 60m | 15m | 60m |
| Position | W | D | 60m | D |

The compiler owns the fixed `1d` to `D` and `1w` to `W` translation. A
non-execute timeframe never triggers that Type.

## 4. Domain Contracts

### 4.1 Input

`FinalizedSeriesBatch` contains:

- one explicit `MarketLineage`;
- a monotonic `finalized_through_ns`;
- immutable `FinalBar` values;
- structured half-open `CoverageGap` values.

The batch rejects foreign roots, instrument IDs, sources, fingerprints, and
schemas. A repeated bar identity is idempotent; a conflicting bar for the same
lineage/timeframe/interval is a hard validation error.

### 4.2 Compiled program

`CompiledRuleSet` pins the release identity and contains unique frozen
`CompiledRule` profiles, `TimeframePlan` values, a closed predicate AST, signal
value expressions, orientation and R operations, and a confidence formula.
Each profile also pins the accepted source, market-data schema, calendar and
aggregation fingerprints, and tick size; every snapshot must match.

The production compiler rejects the current release contract as semantically
incomplete until human-reviewed Type/role, constant-unit, feature,
confidence-range/threshold, rearm, and market-data binding semantics are
released. A package-private strategy-neutral fixture compiler may be used by
tests only; the production entry point cannot enable it.

### 4.3 Output

`SignalBatch` contains an ordered tuple of complete `SignalRecord` values and
an ordered tuple of `Suppression` facts. Suppression codes cover at least:

- release unavailable or semantically unsupported;
- missing context or lookback;
- degraded data or coverage gap;
- lineage mismatch;
- predicate not matched;
- unfillable or off-tick price;
- invalid long/short orientation;
- invalid R or confidence.

Suppressions are deterministic audit facts, not partial signals.

## 5. Predicate Semantics

All bar operands are closed-bar references in an explicit timeframe role.
Offsets are backward only and capped by SP0's bound.

- `eq`, `lt`, `lte`, `gt`, `gte`: exact integer/decimal comparison;
- `crosses_above`/`crosses_below`: current strict crossing after prior
  non-strict opposite relation;
- `all`, `any`, `not`: ordinary short-circuit-free Boolean semantics;
- `within_bars(n, p)`: `p` matches at least once in the current-inclusive
  bounded window;
- `consecutive(n, p)`: `p` matches every bar in the current-inclusive window;
- `sequence(n, [p...])`: the final predicate matches the current bar and prior
  predicates match in chronological order within the bounded window.

All referenced bar IDs become signal provenance. Insufficient history
suppresses; it is never interpreted as false.

These are evaluator mechanics, not values for any Stoic setup. Live use still
requires a signed release whose fields select the mechanics unambiguously.

## 6. Public Boundary

Live and SP3 may import:

- signal model and validation types;
- the strict release compiler/readiness API;
- `SignalEngine`, `FinalizedSeriesBatch`, `CoverageGap`, and output records.

They may not import:

- test fixture compilers;
- mutable alignment buffers;
- authoring YAML, education assets, model clients, vendor SDK types;
- broker/execution, ledger, dashboard, or backtest configuration.

## 7. Failure and Recovery

- Invalid configuration or conflicting input raises a typed validation error.
- Expected no-signal conditions produce typed suppressions.
- A later market-data issue never mutates an already emitted signal.
- Restarting from the same release and committed batches reproduces the same
  canonical decisions.
- Advancing `finalized_through_ns` is monotonic per lineage.
- At most four physical lineages may be active concurrently. Composition must
  explicitly retire a fully drained old lineage at a contract boundary before
  admitting another, bounding roll state without silently evicting context.

## 8. Acceptance Criteria

- All four maps are exact and tested, including `1d`/`1w` translation.
- Only signed, pinned published JSON can reach production compilation.
- The current repository candidate yields zero production signals with an
  explicit readiness blocker.
- Same-end bars are permutation invariant and future bars cannot leak.
- Contract, source, calendar, aggregation, and schema mixing fail closed.
- Degraded bars, gaps, missing context, and insufficient history suppress.
- Complete fixture matches produce all Vision-required fields and exact R.
- Replay produces byte-identical signals and stable IDs.
- No signal-engine import or source contains model, network, broker, execution,
  ledger, dashboard, or backtest dependencies.
- Full tests, formatting, lint, typing, and Vision-drift checks pass.

## 9. Decisions

- [ADR-0008](../../architecture/adr/0008-two-stage-strategy-readiness.md)
- [ADR-0009](../../architecture/adr/0009-causal-multi-timeframe-snapshots.md)
- [ADR-0010](../../architecture/adr/0010-content-addressed-signal-records.md)
