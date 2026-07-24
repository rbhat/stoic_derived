# ADR-0002: Bind Human Approval to Rulebook Content

- Status: Accepted
- Date: 2026-07-24

## Context

Source mining can propose rules, but an agent or model must not silently turn
ambiguous education into live strategy. A name-only approval becomes stale
after edits, while an unsigned digest can still be fabricated by the same
process that authored the candidate.

## Decision

We will require a human approval containing reviewer email, UTC timestamp, the
canonical candidate SHA-256, the approver-key fingerprint, and a
domain-separated Ed25519 signature. Publication and SP2 release loading verify
the signature against a public key pinned outside the authoring artifact and
release. Any semantic change invalidates approval.

## Consequences

- A manual signing/publication step is required after strategy review.
- Candidate research can continue without affecting live behavior.
- Approval is reproducible, authenticated, and auditable rather than
  conversational.
- The approval private key must be managed as a secret and never committed.

## Compliance

The publisher recomputes the digest, verifies the key fingerprint and signature,
and refuses to write a release on mismatch. The SP2 loader also requires both
the externally pinned release SHA-256 and approver public key.
