# ADR-0009: Evaluate Committed Causal Multi-Timeframe Snapshots

- Status: Accepted
- Date: 2026-07-24

## Context

Multi-timeframe bars may arrive in different orders or share a close
timestamp. Joining by logical series or arrival order can leak future data,
cross a physical contract roll, or make replay nondeterministic.

## Decision

SP2 consumes committed batches with a monotonic finalization watermark,
waits until that watermark is strictly beyond an execute close, processes
equal-end bars atomically even when fragmented across batches, and selects only
complete bars ending no later than the execute close. Every selected bar must
share source, logical instrument, physical instrument ID, calendar,
aggregation, and schema lineage. Structured coverage gaps and insufficient
history suppress evaluation. Same-timeframe bars may not overlap. A gap is
pruned only after its end is no later than the earliest retained bar start for
that timeframe; a hard gap-count bound fails closed under pathological input.
The engine admits at most four active physical lineages and requires an
explicit retirement call after an old roll lineage is fully drained.

## Consequences

- Future and cross-roll bars cannot enter a signal.
- Equivalent committed input permutations produce identical output.
- SP1/live composition must supply explicit finalization and structured gaps.
- Gap scans and physical-lineage state remain bounded during long-running
  operation.

## Compliance

Alignment tests cover future bars, equal-close permutations, contract rolls,
fragmented equal-close delivery, lineage mismatches, degraded data, gap
pressure and long-horizon pruning, active-lineage retirement, missing context,
and duplicate replay.
