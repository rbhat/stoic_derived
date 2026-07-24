"""Independently invocable 13:58 Pacific observational watchdog."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from stoic_derived.market_data.codec import normalize_batches
from stoic_derived.market_data.model import FinalBar, QualityState, Timeframe
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import CoverageGap, MarketLineage, SignalType

from .model import EventKind, LedgerError, LedgerEvent, LedgerLimits, LedgerState
from .outbox import LedgerOutbox
from .reconcile import reconcile_events

PACIFIC = ZoneInfo("America/Los_Angeles")
CUTOFF_TIME = time(13, 58)


def cutoff_utc_ns(session_date: date) -> int:
    """Resolve a Pacific session date through zoneinfo, including DST."""
    if not isinstance(session_date, date):
        raise LedgerError("session_date must be a date")
    local = datetime.combine(session_date, CUTOFF_TIME, tzinfo=PACIFIC)
    return int(local.astimezone(UTC).timestamp()) * 1_000_000_000


def coalesce_cutoff_batches(
    batches: Iterable[FinalizedSeriesBatch],
    *,
    session_date: date,
    limits: LedgerLimits | None = None,
) -> tuple[FinalizedSeriesBatch, ...]:
    """Retain exact cutoff evidence across later watermark-only batches."""
    selected_limits = limits or LedgerLimits()
    normalized = normalize_batches(batches)
    if len(normalized) > selected_limits.max_market_observations:
        raise LedgerError("watchdog input exceeds max_market_observations")
    cutoff_ns = cutoff_utc_ns(session_date)
    grouped: dict[
        str,
        tuple[
            MarketLineage,
            int,
            dict[str, FinalBar],
            dict[str, CoverageGap],
        ],
    ] = {}
    for batch in normalized:
        existing = grouped.get(batch.lineage.identity)
        if existing is None:
            bars: dict[str, FinalBar] = {}
            gaps: dict[str, CoverageGap] = {}
            watermark = batch.finalized_through_ns
        else:
            _, watermark, bars, gaps = existing
            watermark = max(watermark, batch.finalized_through_ns)
        for bar in batch.bars:
            if bar.timeframe is Timeframe.ONE_MINUTE and bar.end_ns == cutoff_ns:
                bars[bar.identity] = bar
        for gap in batch.gaps:
            if (
                gap.timeframe is Timeframe.ONE_MINUTE
                and gap.start_ns < cutoff_ns
                and cutoff_ns - 60_000_000_000 < gap.end_ns
            ):
                gaps[gap.identity] = gap
        grouped[batch.lineage.identity] = (batch.lineage, watermark, bars, gaps)

    coalesced: list[FinalizedSeriesBatch] = []
    for lineage_id in sorted(grouped):
        lineage, watermark, bars, gaps = grouped[lineage_id]
        if watermark < cutoff_ns:
            continue
        coalesced.append(
            FinalizedSeriesBatch(
                lineage,
                watermark,
                tuple(bars.values()),
                tuple(gaps.values()),
            )
        )
    return tuple(coalesced)


def cutoff_events(
    events: Iterable[LedgerEvent],
    batch: FinalizedSeriesBatch,
    *,
    session_date: date,
    source: str,
    fence_token: int,
    limits: LedgerLimits | None = None,
) -> tuple[LedgerEvent, ...]:
    """Create idempotent cutoff evidence from one committed physical lineage."""
    selected_limits = limits or LedgerLimits()
    event_values = tuple(events)
    if not isinstance(batch, FinalizedSeriesBatch):
        raise LedgerError("batch must be a FinalizedSeriesBatch")
    if not source:
        raise LedgerError("source must be non-empty")
    if not isinstance(fence_token, int) or isinstance(fence_token, bool) or fence_token <= 0:
        raise LedgerError("fence_token must be a positive integer")
    cutoff_ns = cutoff_utc_ns(session_date)
    exact_bars = tuple(
        bar
        for bar in batch.bars
        if bar.timeframe is Timeframe.ONE_MINUTE and bar.end_ns == cutoff_ns
    )
    if len(exact_bars) > 1:  # FinalizedSeriesBatch normally prevents this.
        raise LedgerError("multiple one-minute bars claim the cutoff interval")
    exact_bar = exact_bars[0] if exact_bars else None
    cutoff_gap = any(
        gap.timeframe is Timeframe.ONE_MINUTE
        and gap.start_ns < cutoff_ns
        and cutoff_ns - 60_000_000_000 < gap.end_ns
        for gap in batch.gaps
    )
    evidence_ready = exact_bar is not None or batch.finalized_through_ns >= cutoff_ns
    if not evidence_ready:
        raise LedgerError("batch watermark has not reached the requested cutoff")

    result = reconcile_events(event_values, limits=selected_limits)
    created: list[LedgerEvent] = []
    for view in result.views:
        if view.signal_type is SignalType.POSITION:
            continue
        for record in view.records:
            if (
                record.signal.lineage != batch.lineage
                or record.state not in {LedgerState.PENDING, LedgerState.ACTIVE}
                or record.signal.signal_ts_ns >= cutoff_ns
            ):
                continue
            if (
                exact_bar is not None
                and exact_bar.quality is QualityState.COMPLETE
                and not cutoff_gap
            ):
                if record.state is LedgerState.ACTIVE:
                    created.append(
                        LedgerEvent.for_market(
                            kind=EventKind.SESSION_FLATTEN_OBSERVED,
                            signal=record.signal,
                            predecessor_semantic_id=record.current_semantic_id,
                            market_bar=exact_bar,
                            price_ticks=exact_bar.close_ticks,
                            source=source,
                            fence_token=fence_token,
                        )
                    )
                else:
                    created.append(
                        LedgerEvent.for_unresolved(
                            record.signal,
                            predecessor_semantic_id=record.current_semantic_id,
                            observed_ts_ns=cutoff_ns,
                            reason="pending_at_session_cutoff",
                            source=source,
                            market_bar=exact_bar,
                            fence_token=fence_token,
                        )
                    )
                continue

            if exact_bar is None:
                reason = "missing_cutoff_bar"
                evidence_bar: FinalBar | None = None
            elif exact_bar.quality is not QualityState.COMPLETE:
                reason = "degraded_cutoff_bar"
                evidence_bar = exact_bar
            else:
                reason = "cutoff_coverage_gap"
                evidence_bar = exact_bar
            created.append(
                LedgerEvent.for_unresolved(
                    record.signal,
                    predecessor_semantic_id=record.current_semantic_id,
                    observed_ts_ns=cutoff_ns,
                    reason=reason,
                    source=source,
                    market_bar=evidence_bar,
                    fence_token=fence_token,
                )
            )
    if len(created) + len(event_values) > selected_limits.max_events_per_reconcile:
        raise LedgerError("watchdog output exceeds max_events_per_reconcile")
    return tuple(sorted(created, key=lambda event: event.event_id))


def enqueue_cutoff(
    events: Iterable[LedgerEvent],
    batch: FinalizedSeriesBatch,
    outbox: LedgerOutbox,
    *,
    session_date: date,
    source: str,
    owner: str,
    now_utc_ns: int,
    lease_ttl_ns: int,
    limits: LedgerLimits | None = None,
) -> tuple[LedgerEvent, ...]:
    """Acquire a fenced local lease and durably enqueue cutoff evidence."""
    lease_key = f"cutoff:{session_date.isoformat()}:{batch.lineage.identity}"
    token = outbox.acquire_lease(
        lease_key,
        owner=owner,
        now_utc_ns=now_utc_ns,
        ttl_ns=lease_ttl_ns,
    )
    generated = cutoff_events(
        events,
        batch,
        session_date=session_date,
        source=source,
        fence_token=token,
        limits=limits,
    )
    outbox.enqueue(generated, lease_key=lease_key, fence_token=token)
    return generated


__all__ = [
    "CUTOFF_TIME",
    "PACIFIC",
    "coalesce_cutoff_batches",
    "cutoff_events",
    "cutoff_utc_ns",
    "enqueue_cutoff",
]
