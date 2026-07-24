# ADR-0020: Transactional, Audited Dashboard Controls

- Status: accepted
- Date: 2026-07-24

## Context

SP5 mutates user/control state and invokes bounded external operations. Admin
actions require durable evidence, while secrets must never pass through the
dashboard.

## Decision

Store users, sessions, connection state, rotation workflows, and audit records
in an exactly verified strict SQLite schema. Use `BEGIN IMMEDIATE` for
mutations. Append a hash-chained audit row in the same transaction as local
admin changes. Protect audit updates/deletes with triggers and hard row bounds.

For Drive/provider operations, append an intent record before invocation and a
sanitized result afterward. Rotation workflows never accept a key: the key is
changed at the SP6 secret boundary and SP5 only verifies the active credential.

## Consequences

Control state is portable and restart-safe. Audit exhaustion blocks new admin
mutations. External operations may have an intent without a completion after a
crash, which is truthful recoverable evidence rather than a fabricated result.
