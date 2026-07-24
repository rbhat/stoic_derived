# SP4 Deterministic Trade Ledger and Lifecycle Audit

- Date: 2026-07-24
- Result: PASS; PRODUCTION STRATEGY REMAINS BLOCKED AS DESIGNED
- Scope: immutable Type ledgers, causal lifecycle tracking, deterministic
  reconciliation, transactional SQLite outbox, Drive publication and
  verification, cutoff watchdog, release-bound runner, CLI, and portability

## Vision and Production Boundary Review

- `VISION.md` is unchanged and unstaged.
- Production composition accepts signals only through
  `SignalEngine.from_release(...)` and `SignalEngine.ingest(...)`.
- No SP4 public API or CLI path accepts authoring YAML, test mechanics,
  backtest or paper performance, strategy overrides, broker credentials, or
  order instructions.
- Every lifecycle event declares `execution: false`, `orders_placed: 0`, and
  `broker_fill_claimed: false`.
- No signed, semantically complete, human-approved SP0 release exists.
  `stoic-ledger readiness` therefore reports `blocked`, no ledger identity,
  zero signals, zero events, no execution, and no orders.

## Ledger and Reconciliation Review

- Scalp, Day, Swing, and Position are logically separate ledgers. Drive
  publication requires an explicit folder for each Type and verifies the
  configured parent.
- Writers create one immutable canonical event object per Type, source
  partition, and content identity. They never edit a shared ledger file.
- The complete signal, signal identity, physical market lineage, lineage
  identity, predecessor event, UTC observation time, exact market evidence,
  and all contributing sources survive reconciliation.
- Reconciliation is a bounded order-independent fold. It does not use Drive
  timestamps, uploader clocks, file listing order, wall clocks, or
  last-write-wins.
- Equivalent multi-source observations converge while retaining every source
  event. Incompatible forks, invalid predecessors, impossible OHLC assertions,
  changed signals, and cross-Type or cross-contract transitions fail
  deterministically to unresolved.
- Entry can occur only on a later complete, gap-free manage-timeframe bar from
  the exact physical lineage. Entry-bar targets are rejected; a touched
  entry-bar stop is required to close immediately; later stop/target
  ambiguity is stop-first.
- Lifecycle retention, accepted intervals, gaps, source partitions, active
  observations, events, payload bytes, pages, retries, and outbox rows all
  have explicit fail-closed bounds.

## Drive and Durable Outbox Review

- Drive is the shared authority. Only locally committed but not yet
  acknowledged events supplement a Drive read; acknowledged local rows cannot
  override missing or different remote content.
- The SQLite outbox uses WAL, `synchronous=FULL`, foreign keys, strict tables,
  atomic event and delivery insertion, immutable payload checksums, bounded
  delivery attempts, and durable pre-generated Drive file IDs.
- Startup verifies canonical `sqlite_master` DDL as well as columns,
  `STRICT`, and the delivery foreign key. A same-version database with missing
  or weakened `CHECK` constraints fails closed before it can hide a committed
  event.
- A retry after a lost successful response reuses the reserved Drive ID. A
  `409` is accepted only after the exact ID, parent, app properties, size,
  checksum, and downloaded bytes are verified.
- Every acknowledged local event is reverified at its exact remote ID.
  Missing, moved, replaced, duplicated-conflicting, or malformed remote
  evidence blocks reconciliation.
- Readiness validates explicit ownership mode and authenticated principal
  kind. Service-account production requires a configured shared drive;
  delegated-user mode rejects service-account principals.

## Cutoff Watchdog Review

- The independently invocable watchdog reconstructs ledger state from Drive
  plus the durable undelivered outbox. It does not depend on the signal
  process remaining alive.
- It coalesces immutable input batches so a later watermark-only batch cannot
  hide an earlier exact 13:58 Pacific cutoff bar after restart.
- Scalp, Day, and Swing active observations close at the exact observed
  one-minute cutoff close without claiming a broker fill. Pending observations
  become unresolved rather than gaining a fabricated entry.
- Missing, degraded, or gapped cutoff evidence fails unresolved. Position
  observations remain cutoff-exempt.
- Local competing invocations use monotonic SQLite fencing. Cross-machine
  duplicates converge by content identity; clocks affect liveness only and
  never choose ledger truth.

## Independent Review Findings Resolved

An independent Terra review inspected the implementation, reran focused and
full verification, and found five material issues across its initial audit and
re-audits:

1. reconciliation initially accepted causally impossible price observations
   and some same-bar stop/target chains;
2. a later watermark-only batch could hide an earlier exact cutoff bar in the
   CLI watchdog restart path;
3. Drive verification did not initially compare returned metadata ID with the
   reserved upload ID;
4. readiness did not initially reject an ownership mode whose authenticated
   principal kind was incompatible;
5. the SQLite schema check initially proved columns, strictness, and foreign
   keys but not the declared `CHECK` constraints.

All findings were fixed. Regression tests cover impossible OHLC assertions,
same-bar ordering, cutoff batch coalescing, mismatched Drive IDs, ownership
principal mismatch, missing acknowledged remote objects, atomic lifecycle
bounds, and same-version outbox databases with weakened constraints. The final
independent re-audit reported no remaining blocker.

## Verification

```text
uv run pytest -q
324 passed, 1 skipped

uv run pytest -q tests/ledger
73 passed

uv run ruff format --check src tests
74 files already formatted

uv run ruff check src tests
All checks passed

uv run mypy src
Success: no issues found in 39 source files

uv lock --check
Resolved 67 packages

uv run stoic-ledger readiness
status: blocked
signal_count: 0
event_count: 0
execution: false
orders_placed: 0

uv build
source distribution and wheel built successfully

git diff --check
passed
```

The blocked state is the intended production behavior until SP0 is
semantically complete, human-approved, signed, and pinned. SP4 records
observational signal lifecycle only; it cannot place or represent broker
orders.
