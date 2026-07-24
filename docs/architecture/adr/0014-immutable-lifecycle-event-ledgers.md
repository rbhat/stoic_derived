# ADR-0014: Use Immutable Lifecycle Event Ledgers

- Status: Accepted
- Date: 2026-07-24

## Context

Four Signal Types need separately viewable ledgers while multiple systems may
write concurrently. Updating a shared CSV, JSON document, or database export
would admit lost updates and make exact signal/contract lineage difficult to
audit.

## Decision

SP4 stores one canonical immutable object per lifecycle event, partitioned by
Signal Type and logical source. Event content determines its identity.
Reconciliation is a deterministic semantic-chain fold that ignores arrival
time and Drive ordering. Equivalent concurrent evidence converges; incompatible
forks retain every event and yield an unresolved view.

## Consequences

- Writers never contend by editing a shared ledger file.
- Exact duplicate publication is harmless.
- Audit and replay are deterministic.
- Conflicts are visible and fail closed rather than being overwritten.
- Retained event counts require explicit safety bounds and future archival
  policy before those bounds are reached.

## Compliance

Type-placement, source-partition, canonical identity, duplicate, permutation,
fork, predecessor, cross-contract, and bound tests enforce the decision.
