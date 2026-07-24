# SP3 - Observational Backtest Implementation Plan

## Milestone

Deliver a portable, causal measurement subsystem over the unchanged SP2 engine
while truthfully keeping current production performance evaluation blocked.

## Task 1 - Immutable research contracts `[portable]`

Files:

- `src/stoic_derived/backtest/model.py`
- `tests/backtest/test_model.py`

Implement and test simulation policy, fills, lifecycle records, warnings,
metrics, evidence modes, folds, canonical bytes, identities, explicit state
bounds, and strict validation.

## Task 2 - Conservative outcome tracker `[portable]`

Files:

- `src/stoic_derived/backtest/simulator.py`
- `tests/backtest/test_simulator.py`

Implement next-one-minute entry, conservative OHLC ordering, adverse
slippage/costs, long/short symmetry, idempotence, lineage isolation,
pending/open cutoff and roll boundaries, end-of-data states, and the exact
one-minute close ending at 13:58 Pacific.

## Task 3 - Exact descriptive metrics `[portable]`

Files:

- `src/stoic_derived/backtest/metrics.py`
- `tests/backtest/test_metrics.py`

Implement exact per-instrument/timeframe/Type partitions, equity/drawdown,
sample warnings, uncertainty metadata, and explicit separate lifecycle
denominators. Do not invent an unspecified market-regime classifier.

## Task 4 - Runner and chronological replay `[portable]`

Files:

- `src/stoic_derived/backtest/runner.py`
- `src/stoic_derived/backtest/chronological_replay.py`
- `tests/backtest/test_runner.py`
- `tests/backtest/test_chronological_replay.py`

Compose only the public engine boundary, merge signal/bar event time
causally, preserve suppressions, retire drained lineages, run chronological
fresh-engine folds, label retrospective replay truthfully, and prove there is
no tuning or live gate.

## Task 5 - Incremental paper observations `[portable]`

Files:

- `src/stoic_derived/backtest/paper.py`
- `tests/backtest/test_paper.py`

Implement committed-live-batch observation through signed-release production
composition only, content-addressed bounded checkpoints, idempotent restart,
declared horizon completion, and blocked/zero behavior without a signed
semantically complete release. Paper observations never place orders.

## Task 6 - Artifacts and CLI `[portable]`

Files:

- `src/stoic_derived/backtest/artifact.py`
- `src/stoic_derived/backtest/codec.py`
- `src/stoic_derived/backtest/cli.py`
- `src/stoic_derived/backtest/__init__.py`
- `tests/backtest/test_artifact.py`
- `tests/backtest/test_cli.py`
- `tests/backtest/test_boundaries.py`
- `pyproject.toml`

Define a strict canonical SP1 batch codec, write atomic canonical artifacts,
expose portable readiness/run/inspect commands, reject overwrite, and keep the
private fixture seam unreachable from production modules and CLI. Readiness
without a signed release must call the public SP2 boundary and report blocked;
it must not load `strategy/rulebook.yaml`.

The public export allowlist is readiness, release-based replay, chronological
replay, paper observation, artifact write, and artifact inspection. No public
function accepts an engine, program, direct signal, strategy mapping, or
fixture flag.

## Task 7 - Audit and milestone delivery `[portable]`

Adversarially review lookahead, same-end fragmentation, replay, missing data,
ambiguous OHLC, session/DST cutoffs, roll isolation, denominators, drawdown,
small samples, fold leakage, artifact determinism, forbidden dependencies, and
absence of any live gating path.

Verification:

```bash
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-backtest readiness
git diff --check
```

Record the audit, add Windows SP3 commands, commit, and push one coherent
verified milestone.
