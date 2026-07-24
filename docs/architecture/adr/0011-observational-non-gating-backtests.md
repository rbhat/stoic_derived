# ADR-0011: Keep Backtesting Observational and Non-gating

- Status: Accepted
- Date: 2026-07-24

## Context

The Vision requires backtest, walk-forward, and paper measurement in parallel
with live signals. It forbids changing the Stoic strategy and explicitly says
validation does not gate the signals/dashboard milestone.

## Decision

SP3 consumes only immutable SP1 batches and public SP2 decisions from one
pinned release. It has no optimizer, fitting, promotion, publication, strategy
override, or live-readiness API. Results are descriptive artifacts. A blocked
SP2 release produces zero simulated trades. Historical chronological folds are
labeled `retrospective_replay`, never genuine out-of-sample. Incremental paper
observations are labeled `paper_forward`.

## Consequences

- Historical performance cannot change a live signal.
- Context/evaluation folds measure one frozen rule release.
- Current strategy-neutral fixtures prove mechanics but provide no edge claim.
- Evidence labels prevent retrospective replay from being presented as genuine
  forward validation.

## Compliance

Boundary and sentinel tests verify forbidden imports/APIs, release immutability,
evidence labels, and identical live decisions after both strong and poor
simulated outcomes.
