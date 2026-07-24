# ADR-0010: Use Complete Content-Addressed Signal Records

- Status: Accepted
- Date: 2026-07-24

## Context

At-least-once replay and multiple signal Types can legitimately produce equal
timestamps and market values. Value-based or timestamp-based deduplication can
lose distinct trades, while partial records violate the Vision.

## Decision

A signal is emitted only with every required field plus release, rule, engine,
physical-contract, and causal-bar provenance. Prices are integer ticks, R is
exact rational arithmetic, and time is the execute bar's UTC close. The signal
ID is SHA-256 of canonical record content excluding the ID.

## Consequences

- Exact replay is idempotent.
- Distinct Types, rules, directions, and contracts retain distinct identities.
- Consumers can audit a signal back to immutable inputs and signed rules.

## Compliance

Contract tests cover completeness, exact arithmetic, stable canonical bytes,
replay deduplication, and distinct-provenance identity.
