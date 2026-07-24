# ADR-0008: Require Two-Stage Strategy Readiness

- Status: Accepted
- Date: 2026-07-24

## Context

A signed SP0 release can be structurally complete while SP2 still lacks an
unambiguous binding for Trade Type, timeframe role, or a deterministic feature
calculator. The current contract also lacks a confidence threshold,
signed confidence output range, explicit constant units, repeated-setup rearm
policy, and signed market-data profile binding. Guessing those meanings would
change the taught strategy.

## Decision

Live evaluation requires both SP0 publication readiness and SP2 semantic
readiness. SP2 compiles only pinned published JSON and rejects any missing,
ambiguous, duplicate, or unsupported semantic dependency. Test-only programs
are isolated from the production compiler and cannot become live releases.

## Consequences

- The current rulebook produces zero live signals by design.
- Engine mechanics can be implemented and tested independently.
- A future human-reviewed schema/release must supply the missing semantic
  bindings before live signals appear.

## Compliance

Tests prove that the repository candidate, draft YAML, and semantically
incomplete releases cannot produce a production compiled program or signal.
