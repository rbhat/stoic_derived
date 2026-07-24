# SP1 - Market Data Layer Design

*Design status: accepted for implementation*

## 1. Objective

SP1 provides one deterministic stream of immutable NQ/ES bars for the signal
engine and backtest. It loads local Databento DBN trades, adapts the Databento
live trades feed, normalizes both through the same contract, and aggregates
1m, 5m, 15m, 60m, daily, and weekly bars.

SP1 succeeds when:

1. the same canonical trades produce byte-identical bars in history and live;
2. bars use exact prices, UTC storage, explicit sessions, and closed-bar
   semantics;
3. contract rolls, duplicates, late data, gaps, and malformed records are
   visible and never silently repaired;
4. SP2 and SP3 depend only on the owned bar interface, not Databento classes;
5. all portable tests run without network access on Mac, WSL, and GCP.

## 2. Brainstorm Decisions

### 2.1 Use trades as the bar source

Historical files already contain Databento `trades`, and the live API exposes
the same schema. Vendor OHLCV would create a second semantics path, so it is a
later cross-check only.

### 2.2 Keep the module pure and streaming

SP1 is a Python module in the modular monolith, not a service or database. It
streams normalized events and finalized bars. Durable ledger storage belongs to
SP4; optional bar caches are reproducible artifacts, not authorities.

### 2.3 Use fixed-point values

Databento prices use 1e-9 fixed-point units. NQ and ES have a 0.25-point tick,
so normalization requires an exact multiple of 250,000,000 and stores the
result as integer ticks. It never rounds and never uses binary floats.

### 2.4 Use event time

Aggregation is driven by `ts_event`, not arrival time or the machine clock.
Live mode uses an explicit lateness watermark. Historical completion explicitly
flushes the stream. Emitted bars are immutable.

### 2.5 Preserve contract identity

The source uses unadjusted continuous symbols. The Databento instrument ID is
part of every aggregation key, so a roll cannot manufacture a cross-contract
OHLC candle. Raw contract symbols are optional definition data and are never
guessed.

### 2.6 Version session semantics

Intraday buckets are half-open UTC-aligned durations. Daily and weekly buckets
use a versioned `America/Chicago` CME equity-index calendar. Regular Globex
hours are 17:00–16:00 CT; 16:00–17:00 is maintenance, and 15:15–15:30 is the
regular equity-index pause. The cash-reference window is 08:30–15:00 CT.
Holiday and early-close exceptions are data overrides, not hidden conditionals.
Production construction loads a committed, strict calendar manifest with a
reviewed half-open coverage horizon and source provenance. Dates outside that
horizon, and ad hoc calendars without provenance, fail closed.

These are named data profiles, not a declaration of Stoic strategy semantics.
SP0 still requires human validation of the authoritative ETH/cash profile,
60-minute anchor, daily-close definition, and PDC/HCOM/LCOM calendar. SP1 can
build and test the profiles without allowing SP2 to select one implicitly.

## 3. Observed Historical Corpus

The local files are DBN v1, dataset `GLBX.MDP3`, schema `trades`, input
symbology `continuous`, and output symbology `instrument_id`.

| File scope | Compressed size | Logical symbols | Requested range |
|---|---:|---|---|
| ES + NQ | 2.5 GB | `ES.c.0`, `NQ.c.0` | 2025-09-01 to 2026-06-06 |
| NQ overlap | 646 MB | `NQ.c.0` | 2026-01-01 to 2026-06-06 |
| NQ tail | 27 MB | `NQ.c.0` | 2026-06-06 to 2026-06-10 16:45 UTC |

The main file contains four mapped instrument IDs per root. The NQ overlap is a
redundant coverage region, so multi-file ingestion must select explicit source
coverage rather than concatenate or set-deduplicate trades. The tail contains
1,745,595 ordered trades, zero off-tick or zero-size records, and many
legitimate equal timestamps.

## 4. Domain Model

### 4.1 Instrument specification

V1 has an allowlist of two specifications:

- `NQ`: logical continuous symbol `NQ.c.0`, tick size 0.25;
- `ES`: logical continuous symbol `ES.c.0`, tick size 0.25.

Instrument definitions can add a raw contract symbol, but cannot change the
root or tick without explicit validation.

### 4.2 Canonical trade

`TradeEvent` is immutable and contains:

- schema version and source;
- root and continuous symbol;
- publisher and instrument IDs;
- `ts_event_ns` and `ts_recv_ns` in UTC;
- integer `price_ticks` and positive integer size;
- action, aggressor side, flags, depth, and venue sequence.

Its canonical serialization preserves every record, including repeated
byte-identical records. Live reconnect recovery uses Databento's per-instrument
timestamp-and-count protocol rather than content-set deduplication.

### 4.3 Final bar

`FinalBar` is immutable and contains:

- schema version, root, continuous symbol, instrument ID, and source;
- timeframe, calendar fingerprint, and aggregation-spec fingerprint;
- half-open UTC `start_ns` and `end_ns`;
- trading date for daily/weekly session assignment;
- integer-tick open, high, low, and close;
- integer volume and trade count;
- first and last event timestamps;
- explicit quality state.

No mutable/in-progress bar crosses the module boundary. Its derived `series_id`
binds source, continuous symbol, timeframe, calendar, and bar-build algorithm;
its bar identity also retains the physical instrument ID and values.

### 4.4 Quality facts

Malformed input raises a typed validation error before aggregation. Runtime
conditions produce typed `MarketDataIssue` facts, including:

- duplicate replay record;
- event-time regression;
- late event after finalization;
- trade outside a declared session;
- missing coverage;
- contract boundary;
- unsupported calendar range.

Issues have stable codes and canonical serialization. No synthetic zero-volume
bar is emitted.

## 5. Historical Ingestion

The DBN adapter:

1. validates DBN version, dataset, trades schema, symbology, symbols, and
   mapping completeness;
2. maps each instrument ID to NQ or ES from metadata intervals;
3. streams records without loading the file into memory;
4. normalizes with the same function used by live records;
5. creates explicit root/time coverage slices before reading records;
6. applies the named, input-order-independent
   `widest-coverage-then-path/v1` policy, excluding wholly contained redundant
   coverage but never deduplicating individual trades;
7. rejects unresolved partial overlap, a gap between explicitly consecutive
   sources, or a conflicting/unknown mapping.

Paths are supplied with `pathlib`; no repository-relative data path is
hardcoded.

## 6. Live Ingestion

The live adapter is thin:

- key comes from an explicit argument or `DATABENTO_API_KEY`;
- dataset is fixed to `GLBX.MDP3`;
- schema is fixed to `trades`;
- symbols are fixed to `NQ.c.0` and `ES.c.0` with continuous symbology;
- optional replay start is a UTC timestamp;
- SDK automatic reconnect is disabled so it cannot bypass durable
  timestamp-and-count recovery; the supervisor reconnects explicitly;
- heartbeats and non-trade system messages become connection status, not
  market events.

Recovery is at-least-once. A resume cursor records the last `ts_event` and
number of records processed at that timestamp per instrument. On reconnect,
the inclusive replay starts at the lowest saved timestamp, discards earlier
records, then discards exactly the already-seen count at the equal timestamp.
This preserves legitimate duplicate payloads. A response timeout is not
treated as proof that the feed or prior processing failed.

Heartbeat and replay-completed system records retain provider `ts_event` as
source progress. The session projects progress onto mapped contracts so the
pure aggregator can finalize quiet bars without wall time or vendor objects.
A skipped-record error poisons the session until replay recovery or explicit
backfill. Roll resubscription is refused while any emitted trade awaits
durable acknowledgement.

Databento does not remap an existing live continuous-contract subscription.
The production supervisor must start a new identical subscription at each
reviewed roll/session boundary and verify the resulting `SymbolMappingMsg`
before publishing bars for the new instrument.

The API key is never logged, serialized, or committed.

## 7. Aggregation

### 7.1 Bucket semantics

- Intraday: 1, 5, 15, and 60-minute UTC-aligned half-open intervals.
- Daily: one CME trading date from the prior calendar day 17:00 CT through the
  trading date 16:00 CT, subject to explicit overrides.
- Weekly: the ordered daily sessions for one CME trading week, without
  combining instrument IDs.

All six bars are built directly from canonical trades. Higher timeframes are
not recursively aggregated from lower bars, which avoids propagating a partial
lower-timeframe decision.

### 7.2 Ordering and finalization

The aggregator maintains a bounded reorder heap per stream. Its watermark is
`max_seen_event_time - allowed_lateness`. Events at or before the watermark are
processed in deterministic order. Equal timestamps are ordered by venue
sequence, receive timestamp, then canonical record bytes while preserving
source multiplicity. Bars with `end_ns <= watermark` are emitted once and
cannot be revised.

An event for an already finalized interval is quarantined. End-of-history
flushes all buffered events and marks populated but not source-closed bars
degraded. Trusted provider progress finalizes scheduled closes as complete.
An explicit contract close flushes remaining populated bars as degraded.

### 7.3 Gaps

SP1 never fabricates prices. Coverage analysis emits gap facts only for
declared trading intervals and distinguishes maintenance/weekend/calendar
closure from missing input. SP2 must be able to suppress evaluation when its
required bar window is incomplete.

## 8. Public Boundaries

SP2/SP3 may import:

- immutable instrument, timeframe, trade, bar, issue, and cursor types;
- session-calendar and aggregation protocols;
- iterators of `FinalBar`.

They may not import:

- Databento SDK record types or clients;
- mutable bar builders or live callbacks;
- credentials;
- education, model, strategy-authoring, broker, ledger, or backtest code.

Backtesting consumes the same bars but cannot configure or alter live
aggregation semantics.

## 9. Configuration and Portability

- Python 3.14 and `pathlib` on Mac, WSL, and Linux.
- All timestamps UTC internally; Pacific conversion only at UI/report edges.
- `DATABENTO_API_KEY` is the only live credential environment variable.
- Calendar version, lateness, symbols, and source files are explicit config.
- Production calendar manifests fingerprint coverage, overrides, and
  provenance.
- Unit tests use no network, wall clock, locale, random source, or hardware
  feature.

## 10. Acceptance Criteria

- Local DBN metadata and a bounded sample load successfully.
- Historical and live-shaped records normalize identically.
- All six timeframes produce exact deterministic bars.
- Redundant file coverage does not double volume; equal-time, multi-price, and
  byte-identical legitimate trades are preserved.
- Late records cannot mutate a finalized bar.
- DST, maintenance, weekend, and calendar-override tests pass.
- Contract rolls never combine instrument IDs.
- Unknown symbols, bad metadata, nonpositive sizes, and off-tick prices fail.
- Canonical replay produces byte-identical output across repeated runs.
- Tests prove no model, network, backtest, broker, or execution dependency can
  enter the SP2-facing interface.
- `VISION.md` remains unchanged.

## 11. Decisions

- [ADR-0005](../../architecture/adr/0005-canonical-market-event-and-bar-contract.md)
- [ADR-0006](../../architecture/adr/0006-event-time-finalization-and-session-calendar.md)
- [ADR-0007](../../architecture/adr/0007-continuous-futures-roll-boundary.md)
