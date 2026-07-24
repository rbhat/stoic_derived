# SP4 - Deterministic Trade Ledger and Lifecycle Design

*Design status: accepted for implementation*

## 1. Objective

SP4 consumes complete SP2 `SignalRecord` values and immutable SP1 market
observations, then records every signal in exactly one Type ledger:
`Scalp`, `Day`, `Swing`, or `Position`. It deterministically tracks each
observation through `pending`, `active`, `closed`, or `unresolved` without
claiming a broker fill or placing an order.

The current repository has no signed, semantically complete, human-approved
SP0 release. Production SP4 therefore remains successfully blocked and emits
zero signals and zero ledger events. Lifecycle mechanics are tested with
test-only values that are unreachable from production composition and the CLI.

## 2. Brainstorm Decisions

### 2.1 Keep the signed-release boundary in front of production writes

Production composition calls `SignalEngine.from_release(...)` and then only
`SignalEngine.ingest(...)`. SP4 cannot accept authoring YAML, an unsigned
strategy program, a fixture switch, a confidence override, or a performance
result. Only complete `SignalRecord` values returned by that production engine
may create production signal events.

Backtest, chronological replay, and paper results remain observational and
cannot enable, disable, promote, filter, or configure the ledger. Production
readiness without a pinned signed release calls the same public SP2 boundary
with no release identity and reports `blocked`, zero signals, zero ledger
events, `execution: false`, and `orders_placed: 0`.

### 2.2 Store immutable event objects in four logical ledgers

The authoritative ledger is an immutable set of canonical event objects,
partitioned first by Signal Type and then by logical source. No writer opens,
edits, appends to, truncates, replaces, or renames a shared ledger file.

Each Drive Type folder contains one object per event. The object name includes
a canonical source partition digest and the content-addressed `event_id`.
`appProperties` repeat the schema, Type, source partition, signal ID, event ID,
and payload SHA-256 for bounded discovery and verification. Duplicate physical
objects with the same exact event bytes are harmless and reconcile to one
fact. The four folder IDs are explicit configuration; writing an event into a
folder for another Type fails closed.

The local filesystem is never the shared authority. Local SQLite stores a
transactional outbox, verified remote cache, and watchdog coordination state.
Drive remains the shared source of truth.

### 2.3 Use exact, content-addressed lifecycle evidence

Every `LedgerEvent` contains:

- the event schema and event kind;
- Signal Type, `signal_id`, logical event source, and source partition;
- the full physical `MarketLineage` and its identity;
- a canonical UTC nanosecond observation timestamp;
- an explicit predecessor event ID where a transition requires one;
- the complete `SignalRecord` on `signal_observed`, or its exact canonical
  digest on later events;
- exact integer-tick market price plus source bar identity and canonical market
  observation fields where a price is observed;
- `execution: false`, `orders_placed: 0`, and
  `broker_fill_claimed: false`.

The content excluding `event_id` determines `event_id`. Hostname, absolute
path, wall-clock ingestion time, retry count, Drive file ID, and watchdog
instance ID never enter the identity.

The event vocabulary is:

- `signal_observed`: creates `pending`;
- `entry_observed`: `pending -> active` when a later eligible complete market
  bar from the exact physical lineage touches the planned entry;
- `stop_observed`: `active -> closed`;
- `target_observed`: `active -> closed`;
- `session_flatten_observed`: `active -> closed` at the exact observed 13:58
  Pacific one-minute close;
- `unresolved_observed`: `pending|active -> unresolved` at a physical contract
  roll, unavailable required cutoff price, or other explicit evidence
  boundary.

These are market observations, not executions. No event kind is named `fill`,
`order`, `position`, or `execution`.

### 2.4 Make lifecycle evaluation conservative and causal

Only complete, gap-free market bars from the signal's exact physical lineage
are eligible. A bar ending at or before `signal_ts_ns` cannot activate a
signal. Ordinary entry/stop/target observations use the signal Type's pinned
manage timeframe. A physical contract roll makes pending and active
observations unresolved before retiring their lineage.

Entry requires a planned entry touch. On the entry bar, a touched stop wins
conservatively and a touched target is ignored because OHLC cannot prove that
target occurred after entry. On later bars, stop wins a stop/target tie. A
signal can never cross physical lineage.

The tracker retains explicit monotonic watermarks, accepted observation
identities, active observations, and known gaps. Exact replays are idempotent.
Conflicting content for the same lineage/timeframe/interval fails closed.

### 2.5 Reconcile semantic chains, never arrival timestamps

Reconciliation is a pure deterministic fold over verified event bytes. It
groups by `(Signal Type, signal_id)`, validates the exact signal and physical
lineage, and follows predecessor relationships. Drive listing order, file ID,
modification time, creation time, uploader clock, and local receipt order are
irrelevant.

Equivalent observations from multiple sources converge when their lifecycle
kind, predecessor semantic state, market price, market observation identity,
and terminal reason are identical. Their source event IDs remain preserved as
evidence. An incompatible fork, invalid predecessor, changed signal payload,
cross-Type event, cross-contract event, or multiple different terminal
observations yields a deterministic `unresolved` view with typed conflicts.
The reconciler never uses last-write-wins and never discards either branch.

The fold emits four separate bounded `LedgerView` collections. Each view
contains the exact contributing event IDs and source partitions so the state
can be reproduced byte-for-byte.

### 2.6 Enforce 13:58 Pacific with an independent watchdog

Scalp, Day, and Swing are cutoff-bound. Position is cutoff-exempt.
`America/Los_Angeles` converts the UTC event time only at the session edge;
there is no fixed UTC offset.

The exact complete one-minute bar whose `end_ns` is 13:58:00 Pacific supplies
the observed flatten price as its close. At that evidence boundary, every
active non-Position observation for the same physical lineage receives a
`session_flatten_observed` event. Pending observations become unresolved
without inventing an entry. If a committed watermark proves that the exact
cutoff bar is absent, degraded, or covered by a known gap, affected
observations become `unresolved` with a typed missing-cutoff reason. A late
price, interpolation, quote, or previous close is never substituted.

`stoic-ledger watchdog` is independently invocable by systemd or a GCP
scheduler. It reconstructs state from Drive plus the durable outbox and
accepts committed SP1 evidence; it does not depend on a still-running signal
process or an in-memory heartbeat.

SQLite `BEGIN IMMEDIATE` lease rows provide monotonically increasing local
fencing tokens. A stale local holder cannot enqueue after a newer token.
Cross-machine invocations may both observe the same cutoff; canonical event
identity and Drive reconciliation make identical output idempotent.
Incompatible output fails unresolved. Lease expiry and wall clocks are
liveness aids only and never decide ledger truth.

### 2.7 Use a durable transactional SQLite outbox

Creating a ledger event and scheduling its Drive delivery occur in one SQLite
transaction. SQLite uses foreign keys, WAL journaling, `synchronous=FULL`, an
explicit busy timeout, and schema-version checks. Event bytes are immutable
under a unique `event_id`; a repeated ID with different bytes is corruption.

The dispatcher:

1. durably allocates and stores a pre-generated Drive file ID before upload;
2. uploads exact canonical bytes to the configured Type folder;
3. retries bounded transient `403` rate-limit, `429`, `5xx`, timeout, and
   connection failures with truncated exponential backoff;
4. treats `409 Conflict` after a retry as potentially successful and verifies
   the exact remote file ID, parent, metadata, size, and downloaded bytes;
5. marks delivery complete only after exact verification.

A crash before enqueue commits creates no event. A crash after commit is
replayed. A crash after remote success but before local acknowledgement is
resolved by the same file ID and `409` verification. A lost generated ID may
produce a second physical object, but exact event identity deduplicates it
without data loss.

### 2.8 Resolve Drive authentication and ownership explicitly

The implementation uses Google Application Default Credentials with an
explicit Drive scope. It supports exactly two declared ownership modes:

- `shared_drive_service_account`: production on GCP uses a least-privilege
  attached service account that is a member of the configured shared drive;
- `delegated_user`: authorized-user or delegated-user ADC writes into storage
  owned by that human user.

Mode, root folder, four Type folder IDs, and (for shared-drive mode) shared
drive ID are required configuration. Readiness verifies the authenticated
principal, folder parents/capabilities, and shared-drive membership. An
attached service account targeting ordinary My Drive, an undeclared ownership
mode, a mismatched folder, or insufficient capability is blocked.

This follows current official behavior:

- [`files.generateIds`](https://developers.google.com/workspace/drive/api/guides/create-file#generate_ids_to_use_with_your_files)
  permits pre-generated IDs for ordinary uploaded files and a successful retry
  returns `409 Conflict` without creating a duplicate;
- [shared drives](https://developers.google.com/workspace/drive/api/guides/about-shareddrives)
  state that service accounts have no Drive storage quota and cannot own files,
  so they must upload to shared drives or act for a human user;
- [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
  prefers an attached service account in Google Cloud production;
- [Drive upload error handling](https://developers.google.com/workspace/drive/api/guides/manage-uploads#handle_media_upload_errors)
  and [usage limits](https://developers.google.com/workspace/drive/api/guides/limits#resolve_time-based_quota_errors)
  require retries and truncated exponential backoff for transient failures.

### 2.9 Bound all retained state and payloads

`LedgerLimits` explicitly bounds canonical event bytes, events per reconcile,
signals per Type, active signals, source partitions, accepted market
observations, retained gaps, outbox rows, delivery attempts per dispatch,
Drive pages, and downloaded bytes. Crossing any safety bound fails closed
before accepting, publishing, or presenting a complete state.

All source strings are normalized to a content-addressed partition digest for
Drive naming. Human-readable source remains inside signed canonical bytes and
cannot create a path traversal or unbounded folder vocabulary.

## 3. Domain Contracts

### Input

- production `SignalBatch` values emitted only by a release-bound SP2 engine;
- ordered immutable `FinalizedSeriesBatch` values from SP1;
- verified immutable Drive event objects;
- explicit ownership configuration and `LedgerLimits`.

Signals are accepted by `signal_id`; physical market input is accepted by
canonical SP3 batch identity and interval-conflict rules. Production CLI input
is canonical batch JSONL, never raw DBN, draft rulebook YAML, backtest output,
or fixture JSON.

### State

```text
signal_observed
    |
    v
 pending --entry_observed--> active --stop_observed----------> closed
    |                         |------target_observed----------> closed
    |                         |------session_flatten_observed-> closed
    |                         |
    +--unresolved_observed----+-------------------------------> unresolved
```

Position follows the same graph except that it never admits
`session_flatten_observed` or a cutoff-specific unresolved transition.

### Output

- immutable canonical `LedgerEvent` objects;
- deterministic per-Type `LedgerView` objects;
- typed `LedgerConflict` and readiness blockers;
- durable outbox delivery results;
- watchdog reports with `execution: false` and `orders_placed: 0`.

No output claims broker position, broker fill, order acknowledgement, or
capital P/L. Price deltas and exact R may be derived for display later, but
SP4 never labels them realized broker profit or loss.

## 4. Failure and Restart Semantics

- Missing or invalid SP0 release: successful `blocked` result, zero production
  signals/events, no Drive writes.
- Local event-ID collision with different bytes: corruption error; no write.
- Drive timeout after create: retry same pre-generated ID, then verify `409`.
- Duplicate exact remote objects: deterministic deduplication.
- Changed remote bytes/metadata, unknown schema, cross-Type placement,
  noncanonical JSON, or hash mismatch: fail closed.
- Event-chain fork: retain all evidence and present the signal as unresolved.
- Missing cutoff market observation: unresolved, never a fabricated close.
- Stale watchdog fence: no local enqueue.
- Bounds exceeded: fail before reporting a complete reconciliation or
  acknowledging durable publication.

## 5. Acceptance Criteria

- Exactly four Type ledgers exist and no event can move between them.
- Every production signal creates exactly one semantic `signal_observed` fact
  or no committed fact; retries never create a different fact.
- Every signal deterministically appears as pending, active, closed, or
  unresolved with complete signal and physical-contract lineage.
- Entry, stop, target, ambiguity, gap, roll, DST, cutoff, and Position-exempt
  behavior are exact and idempotent.
- The watchdog can close eligible active observations after a prior process
  death using independently supplied committed evidence and never sends an
  order.
- Reconciliation is byte-identical under arbitrary Drive listing order and
  exact duplicates.
- Conflicts fail unresolved; no timestamp or last-write-wins path exists.
- SQLite crash points and Drive timeout/`409` recovery lose no committed event.
- ADC ownership readiness blocks unsupported service-account/My Drive
  combinations and verifies Type folders before writes.
- Current production readiness is blocked with zero signals, zero ledger
  events, `execution: false`, and `orders_placed: 0`.
- SP2 imports no SP4 module; SP3 metrics never enter SP4 readiness.
- Full tests, Ruff, mypy, lock, packaging, readiness, and boundary checks pass
  on portable code.

## 6. Decisions

- [ADR-0014](../../architecture/adr/0014-immutable-lifecycle-event-ledgers.md)
- [ADR-0015](../../architecture/adr/0015-drive-authority-with-transactional-outbox.md)
- [ADR-0016](../../architecture/adr/0016-observational-cutoff-watchdog.md)
