# ADR-0007: Preserve Futures Contract Boundaries

- Status: Accepted
- Date: 2026-07-24

## Context

The local DBN files use Databento continuous symbols `NQ.c.0` and `ES.c.0`.
Those symbols map to different instrument IDs over time, and their prices are
unadjusted across rolls. Combining contracts inside an OHLC bar would create a
synthetic price move.

## Decision

Every trade and bar retains both the logical root and Databento instrument ID.
Aggregation keys include instrument ID, so a transition finalizes the old
contract independently as a degraded boundary split and starts the new one.
Roll resubscription is refused while an emitted old-contract trade is
unacknowledged. A fresh mapping retires the old recovery cursor. SP1 does not
back-adjust, splice, or infer a raw contract symbol absent definition data.

Overlapping historical coverage uses the named, input-order-independent
`widest-coverage-then-path/v1` policy. Redundant contained coverage is
excluded; equal intervals use lexical path precedence; unresolved partial
overlap fails closed. Individual trade records are never set-deduplicated
because distinct or even byte-identical records can be legitimate venue
events.

## Consequences

- Roll gaps remain visible and auditable.
- Weekly or daily output can contain an explicit contract-boundary split.
- A future continuous-series presentation layer may adjust prices, but it
  cannot feed the deterministic live engine without a new decision.

## Compliance

Tests exercise overlapping coverage, same-sequence multi-price trades,
byte-identical legitimate trades, and instrument changes at bucket boundaries.
