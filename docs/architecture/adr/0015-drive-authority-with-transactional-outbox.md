# ADR-0015: Use Drive Authority with a Transactional Local Outbox

- Status: Accepted
- Date: 2026-07-24

## Context

Google Drive is the required shared source of truth, but a remote upload can
succeed while its response is lost. Service accounts also cannot own ordinary
Drive files. Treating Drive RPC as a local atomic write would lose events or
create unverifiable duplicates during partial failure.

## Decision

SP4 commits canonical event bytes and an outbound delivery in one
full-synchronous SQLite transaction. The dispatcher persists a Drive
pre-generated file ID, uploads an immutable ordinary file, retries bounded
transient failures, and verifies `409 Conflict` responses against the exact
remote bytes and metadata before acknowledging delivery.

Authentication uses Application Default Credentials. Production may use an
attached service account only with an explicitly configured shared drive; the
alternative is explicitly declared delegated-user ownership. Readiness
verifies the principal, ownership mode, and four Type folders before writes.

## Consequences

- A committed local event survives restart until Drive verifies it.
- Success-with-response-loss is retry-safe.
- Duplicate physical objects can exist only with identical semantic event
  identity and reconcile harmlessly.
- Deployments must provision Drive ownership and folder IDs before becoming
  ready.
- SQLite is durable local transport state, not shared ledger authority.

## Compliance

Transaction, crash-reopen, collision, file-ID persistence, timeout, retry,
`409`, metadata/byte mismatch, paging, capability, and ownership-mode tests
enforce the decision.
