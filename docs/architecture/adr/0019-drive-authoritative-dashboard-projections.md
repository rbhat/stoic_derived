# ADR-0019: Drive-Authoritative Dashboard Projections

- Status: accepted
- Date: 2026-07-24

## Context

SP4 defines Drive as the shared ledger authority and the local outbox as
durable transport state. A dashboard cache or fixture must not become a second
source of production truth.

## Decision

Check signed-release readiness before ledger reads. When ready, verify
acknowledged Drive objects, read the complete bounded Drive event set, add only
undelivered local outbox events, decode through the SP4 codec, and reconcile
through SP4. When readiness is blocked, return zero observations.

Project separate open, closed, and unresolved collections. Derive exact
direction-aware tick P/L and rational R only for closed observations. Never
derive dollar P/L or claim fills/executions.

## Consequences

Dashboard refresh may fail when Drive authority cannot be proven; it does not
fall back to acknowledged local bytes. Tests use explicit dependency-injected
fakes that are absent from production composition.
