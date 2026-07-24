# ADR-0012: Use a Conservative Causal One-minute Fill Model

- Status: Accepted
- Date: 2026-07-24

## Context

SP2 signals are known at a closed-bar timestamp. OHLC bars do not reveal
intrabar path, and the repository has no approved broker, fee, or order-type
contract. Filling on the decision bar or resolving ambiguity favorably would
introduce lookahead and optimistic bias.

## Decision

SP3 begins fill observation strictly after the signal timestamp, using complete
one-minute bars from the exact physical lineage. Entry requires a range touch.
Stop wins ambiguous bars; an entry-bar target is ignored unless confirmed
later. Stop gaps receive the worse open and targets receive no favorable gap
improvement. Planned levels determine touches. Entry and exit slippage and
round-turn fees are separate explicit non-negative integer tick values;
simulated fill prices include slippage and net results subtract fees once.

Non-Position session flatten requires the exact complete one-minute bar whose
end converts to 13:58:00 America/Los_Angeles. Missing, degraded, or gapped
evidence produces an unresolved record. Pending observations expire unresolved
at the cutoff; Position observations are cutoff-exempt. Every Type becomes
unresolved at a physical contract roll rather than crossing contracts.

## Consequences

- Simulation assumptions are deterministic, conservative, and auditable.
- Tick/R results are available; dollar P/L waits for an approved contract
  economics manifest.
- Assumptions may understate favorable fills but cannot silently overstate them.

## Compliance

Long/short, decision-bar, tie, gap-through, cost, degraded/gap, DST, and missing
cutoff tests cover every lifecycle transition.
