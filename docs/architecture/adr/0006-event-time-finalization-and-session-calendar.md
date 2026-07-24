# ADR-0006: Event-Time Finalization and Versioned Session Calendar

- Status: Accepted
- Date: 2026-07-24

## Context

Live delivery can reconnect, overlap, or arrive late. CME sessions cross UTC
dates and daylight-saving transitions, and holiday hours can change after a
calendar is first published. Wall-clock-driven or implicit calendar behavior
would make replay differ from live operation.

## Decision

Aggregation uses event time and an explicit bounded lateness watermark. A bar
is emitted only after its end is behind the watermark and is immutable after
emission. Later events are quarantined as typed quality issues.

Session assignment uses `America/Chicago` and a versioned CME equity-index
calendar: regular Globex hours are 17:00 to 16:00 CT with the daily maintenance
halt, the regular equity-index pause is 15:15 to 15:30 CT, and the
cash-reference window is 08:30 to 15:00 CT. Holiday and
early-close changes are explicit overrides whose canonical digest becomes the
calendar fingerprint. Production calendars load strict committed manifests
whose reviewed coverage, overrides, and source provenance are also
fingerprinted. Ad hoc or uncovered schedules fail closed for all aggregation.

Provider heartbeat and replay-completed timestamps are trusted live progress.
Consumers project those source timestamps onto mapped physical contracts and
explicitly advance the pure aggregator watermark. Wall time is never a
finalization input.

Pacific time is display-only.

## Consequences

- Replay is independent of machine clock, locale, and DST offset.
- The live path trades bounded latency for immutable closed bars.
- Quiet bars can close from provider progress without another trade.
- Calendar changes are reviewable and invalidate downstream fingerprints.
- Quality issues remain evidence; they never silently rewrite a published bar.

## Compliance

Tests cover half-open boundaries, spring/fall DST, weekends, maintenance,
calendar overrides, late events, and deterministic finalization.
