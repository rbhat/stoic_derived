# ADR-0003: Use a Bounded Declarative Rule Vocabulary

- Status: Accepted
- Date: 2026-07-24

## Context

Arbitrary code inside the rulebook would be expressive but difficult to audit
and could admit network/model calls, lookahead, or execution actions.

## Decision

We will represent validated predicates with a small allowlisted, typed,
closed-bar expression and bounded-sequence vocabulary. We will not permit code,
imports, callbacks, plugins, future references, or unbounded windows.

## Consequences

- Rule expression is less flexible than Python.
- Identical inputs can be evaluated predictably and inspected structurally.
- New operators require an explicit schema and engine change.

## Compliance

Static validation allowlists every operator and operand type, caps all
lookbacks, rejects future offsets, and scans actions for signals-only
semantics.
