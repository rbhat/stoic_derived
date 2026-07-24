# SP4 - Deterministic Trade Ledger and Lifecycle Implementation Plan

## Milestone

Deliver four Drive-backed, concurrency-safe observational ledgers over the
unchanged SP2 production boundary while truthfully keeping current production
blocked and at zero.

## Task 1 - Immutable ledger contracts `[portable]`

Files:

- `src/stoic_derived/ledger/model.py`
- `src/stoic_derived/ledger/codec.py`
- `tests/ledger/test_model.py`
- `tests/ledger/test_codec.py`

Implement strict event kinds, state, canonical bytes, signal and market
lineage, predecessor links, Type partitioning, content identities, bounds, and
exact decoding. Every event declares observational/no-execution semantics.

## Task 2 - Causal lifecycle tracker `[portable]`

Files:

- `src/stoic_derived/ledger/lifecycle.py`
- `tests/ledger/test_lifecycle.py`

Implement pending/active/closed/unresolved transitions, manage-timeframe
observations, conservative OHLC handling, exact physical-lineage isolation,
gaps, contract roll, duplicate input, interval conflicts, and bounded state.

## Task 3 - Deterministic reconciliation `[portable]`

Files:

- `src/stoic_derived/ledger/reconcile.py`
- `tests/ledger/test_reconcile.py`

Fold immutable events independently of file/listing/timestamp order. Merge
semantically equivalent multi-source observations, retain all evidence, and
turn incompatible chains into typed unresolved views without last-write-wins.

## Task 4 - Durable local outbox `[portable]`

Files:

- `src/stoic_derived/ledger/outbox.py`
- `tests/ledger/test_outbox.py`

Implement versioned SQLite initialization, full-synchronous WAL durability,
atomic event+delivery enqueue, immutable collision checks, Drive file-ID
reservation, bounded claims, retry state, safe restart, and monotonically
fenced watchdog leases.

## Task 5 - Drive authority and retry-safe sync `[portable]`

Files:

- `src/stoic_derived/ledger/drive.py`
- `tests/ledger/test_drive.py`

Use ADC-authorized Drive REST calls, explicit ownership modes and Type folder
mapping, pre-generated file IDs, bounded transient retries, exact `409`
verification, paginated immutable reads, canonical-byte verification, and
readiness checks. Tests use a scripted transport and no real credentials.

## Task 6 - Independent cutoff watchdog `[portable]`

Files:

- `src/stoic_derived/ledger/watchdog.py`
- `tests/ledger/test_watchdog.py`

Reconstruct active state, consume exact committed one-minute cutoff evidence,
close non-Position observations at the observed 13:58 Pacific close, leave
Position exempt, mark missing evidence unresolved, enforce local fencing, and
remain independently invocable after process death.

## Task 7 - Release-bound runner and CLI `[portable]`

Files:

- `src/stoic_derived/ledger/runner.py`
- `src/stoic_derived/ledger/cli.py`
- `src/stoic_derived/ledger/__init__.py`
- `tests/ledger/test_runner.py`
- `tests/ledger/test_cli.py`
- `tests/ledger/test_boundaries.py`
- `pyproject.toml`

Compose only `SignalEngine.from_release(...)` and `SignalEngine.ingest(...)`,
then lifecycle/outbox delivery. Expose `readiness`, `run`, `watchdog`,
`reconcile`, and `sync` without strategy/test-fixture/performance/execution
switches. Without a release, readiness must be blocked/zero and must not load
`strategy/rulebook.yaml`.

## Task 8 - Audit and milestone delivery `[portable]`

Adversarially review Type/source isolation, exact signal and contract lineage,
causal transitions, ambiguous bars, cutoff/DST, dead-process restart,
competing watchdogs, event forks, SQLite crash points, Drive response loss,
`409` verification, ownership mode, bounds, forbidden dependencies, and
absence of order or performance-gating paths.

Verification:

```bash
uv run pytest -q tests/ledger
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-ledger readiness
uv build
git diff --check
```

Record the independent audit, fix every material finding, commit one coherent
SP4 milestone, and push `main`.
