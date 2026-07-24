# ADR-0016: Use an Independent Observational Cutoff Watchdog

- Status: Accepted
- Date: 2026-07-24

## Context

Scalp, Day, and Swing observations must close at 13:58 Pacific even if the
earlier live process died. Position is exempt. SP4 has no broker and cannot
claim a fill or invent a price.

## Decision

An independently scheduled watchdog reconstructs ledger state and consumes the
exact complete one-minute market bar ending at 13:58 in
`America/Los_Angeles`. It emits immutable `session_flatten_observed` events at
that bar's close for active non-Position signals and unresolved events for
pending or provably missing-price cases. It never sends an order.

Local SQLite leases carry monotonically increasing fencing tokens to reject
stale local holders. Cross-machine correctness comes from content identity and
fail-closed reconciliation, not lease clocks or wall-clock ordering.

## Consequences

- Earlier process death cannot suppress an independently supplied cutoff
  observation.
- Position remains cutoff-exempt.
- Missing exact market evidence is visible as unresolved rather than a
  fabricated close.
- Deployment must schedule and monitor the watchdog separately in SP6.

## Compliance

DST, exact-cutoff, missing/degraded/gapped price, pending, Position exemption,
dead-process restart, duplicate invocation, stale-fence, and no-execution tests
enforce the decision.
