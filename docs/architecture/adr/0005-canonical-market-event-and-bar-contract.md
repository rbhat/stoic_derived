# ADR-0005: Canonical Market Event and Bar Contract

- Status: Accepted
- Date: 2026-07-24

## Context

Historical replay, live ingestion, the signal engine, and backtesting must see
the same market facts. Databento prices are fixed-point integers, while Python
floats and vendor-specific objects would make equality and replay auditing
fragile.

## Decision

The market-data module owns immutable `TradeEvent` and `FinalBar` contracts.
Timestamps are UTC integer nanoseconds, prices are integer 0.25-point ticks,
sizes and counts are integers, and intervals are half-open `[start, end)`.
Databento SDK objects never cross the adapter boundary.

Only finalized bars are exposed to SP2 and SP3. Every serialized record carries
a schema version, source identity, instrument ID, logical NQ/ES root, timeframe,
calendar fingerprint, and aggregation fingerprint. A derived `series_id` binds
the source, continuous symbol, timeframe, calendar, and algorithm semantics
without hiding the physical contract ID carried by each bar.

Canonical bar open/close order is event time, venue sequence, receive time,
then canonical record bytes. This total order is independent of arrival order
while preserving byte-identical source-record multiplicity.

## Consequences

- Historical and live records use one normalization and aggregation path.
- Price arithmetic is exact and portable.
- Consumers cannot observe or mutate an in-progress candle.
- Adapters must reject malformed, unknown, or off-tick input instead of
  coercing it.

## Compliance

Fitness tests replay equivalent trade streams through historical and live
adapter fakes and compare canonical serialized bars byte for byte.
