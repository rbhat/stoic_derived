# SP2 Deterministic Signal Engine Audit

- Date: 2026-07-24
- Result: PASS for engine mechanics; LIVE STRATEGY BLOCKED AS DESIGNED
- Scope: SP2 contracts, release compiler, causal alignment, evaluator, engine,
  readiness CLI, and portable tests

## Vision and Boundary Review

- `VISION.md` is unchanged and unstaged.
- SP2 contains no network, model, broker, execution, ledger, dashboard, or
  backtest dependency.
- The production constructor accepts only a canonical SP0 release loaded with
  an external SHA-256 pin and Ed25519 public key.
- Draft YAML and arbitrary mappings cannot reach the production constructor.
- SP3 will call the same engine and has no rule, weight, threshold, feature, or
  publication override. Backtesting remains parallel and non-gating.
- Every signal and suppression pins the release SHA, rulebook version, engine
  version, physical market lineage, event time, and causal bar identities.

## Truthful Readiness Review

No `strategy/releases/` artifact exists. The current SP0 candidate remains
blocked by 21 publication conditions: missing human approval, four unvalidated
setup/direction profiles, three unknown executable rules, eleven unresolved
decisions, and the SMA source conflict.

Even a structurally publishable SP0 v1 fixture is not yet live-executable. The
signed schema still needs human-reviewed:

- Trade Type and timeframe-role binding;
- deterministic feature predicates/calculators;
- a confidence threshold;
- repeated-setup emission/rearm semantics;
- market-data/session and unit bindings.

SP2 reports these as deterministic compile blockers and produces no production
program or signal. Strategy-neutral fixtures are private test seams and are
not Stoic rules.

## Causality and Determinism Review

- All four Vision timeframe maps are exact, including strict `1d` to `D` and
  `1w` to `W` translation.
- Committed batches are lineage-scoped and same-end bars become visible
  atomically, independent of tuple order or batch fragmentation. Evaluation
  waits for the watermark to advance strictly beyond the execute close.
- A new coverage gap whose start precedes the sealed watermark is rejected, so
  late gap delivery cannot retroactively invalidate an emitted decision.
- Every selected bar ends no later than its execute close. Future bars are
  invisible.
- Source, logical symbol, physical instrument ID, calendar fingerprint,
  aggregation fingerprint, and schema must all match.
- Contract rolls start with independent empty history.
- Degraded bars, missing context, insufficient history, and overlapping
  structured gaps suppress. Quality gaps are not count-pruned across unrelated
  timeframes. They are pruned only after retained history has causally passed
  them, and pathological retained-gap growth fails closed.
- Compiler lookbacks include explicit offsets, crossing predecessors, temporal
  windows, sequences, confidence predicates, and price formulas. Combined
  lookback is capped at 1,000 and the engine allocates the full compiled bound.
- Signed point-valued constants convert exactly to 0.25-point ticks; unitless
  constants and mixed-dimension predicates fail compilation. Entry, stop, and
  target must all be price-valued. R is a reduced exact rational.
- Confidence uses signed executable predicates and an explicit 0–100 output
  range and threshold. Weights must be nonnegative, sum to at most 100, and
  make the threshold reachable. Unimplemented derived features keep
  compilation blocked.
- Only the implemented once-per-execute-bar rearm policy can compile.
- Signed market-data source, schema, calendar, aggregation, and tick bindings
  are enforced against every snapshot.
- Signal time is the execute bar's UTC epoch-nanosecond close, never wall time.
- Exact in-process replay is an idempotent no-op. A restart reproduces the same
  content-addressed signal ID for SP4 to deduplicate durably.
- Replay state is bounded by retained aligner history; older behind-watermark
  input is rejected without an unbounded per-decision memory set.
- Active physical lineages are hard-bounded at four and require explicit
  retirement after a drained contract roll.
- Different Types, rules, directions, execute bars, and physical contracts
  remain distinct even at equal timestamps and prices.

## Adversarial Coverage
Committed tests cover:

- invalid release path/hash/key and semantic blockers;
- duplicate profiles and private-fixture isolation;
- all operators, crossings, current-inclusive windows, sequences, unavailable
  features, thresholds, tick failures, and both orientations;
- same-close permutations, future data, lineage mixing, rolls, degraded bars,
  fragmented same-end batches, gap pressure, missing lookback, exact
  duplicates, and conflicts;
- temporal warm-up through full-engine emission;
- 1,000-bar engine construction and rejection of oversized nested lookbacks;
- point-to-tick conversion, unit blockers, derived-feature blockers, and signed
  market-data mismatch;
- mixed dimensions, non-price signal outputs, confidence bounds/reachability,
  unsupported rearm, and a late gap overlapping a sealed decision;
- replay after history trimming and absence of unbounded engine dedupe state;
- long-horizon causal gap pruning, overlapping-bar rejection, and explicit
  bounded lineage lifecycle;
- all four Types, same-timestamp distinct contracts, replay identity, and
  release-pinned suppressions;
- static forbidden imports and truthful candidate readiness output.

An independent Terra review reran the suite and additional read-only probes for
temporal warm-up, permutations, roll isolation, data quality, price failures,
and dependency boundaries. It passed. Its one documentation finding—an unused
duplicate-replay suppression code conflicting with idempotent no-op
semantics—was resolved by making the contract explicit and removing the unused
code.

The Sol architecture audit found latent-path defects despite the initial green
suite: point/tick unit confusion, unenforced signed market-data bindings,
same-end fragmentation, a 512-bar buffer below the compiler's bound, unsafe
gap pruning and late-gap handling, unchecked value dimensions, unsupported
rearm semantics, invalid or unreachable confidence formulas, and unbounded gap
and retired-lineage state. Each was fixed and given a committed regression
test before the final PASS.

## Verification

```text
uv run pytest -q
181 passed, 1 skipped

uv run ruff format --check src tests
32 files already formatted

uv run ruff check src tests
All checks passed

uv run mypy src
Success: no issues found in 18 source files

uv lock --check
Resolved 64 packages

uv run stoic-signal readiness --candidate strategy/rulebook.yaml
status: blocked
signal_engine_ready: false

git diff --check
passed
```

The blocked strategy state is not an SP2 defect. Actual B&R/SFP signals remain
unavailable until the SP0 human-validation and signed-schema work is complete.
