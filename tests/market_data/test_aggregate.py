"""Fitness tests for deterministic event-time multi-timeframe aggregation."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from stoic_derived.market_data.aggregate import (
    AggregationSpec,
    MultiTimeframeAggregator,
)
from stoic_derived.market_data.calendar import CmeEquityIndexCalendar
from stoic_derived.market_data.model import (
    InstrumentSpec,
    IssueCode,
    MarketDataValidationError,
    QualityState,
    Timeframe,
    TradeEvent,
)


def make_calendar(*, version: str) -> CmeEquityIndexCalendar:
    return CmeEquityIndexCalendar(
        version=version,
        coverage_start=date(2025, 1, 1),
        coverage_end=date(2027, 1, 1),
        provenance=("test-fixture",),
    )


def ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000_000) + delta.microseconds * 1_000


def trade(
    ts_event_ns: int,
    price_ticks: int,
    *,
    size: int = 1,
    instrument_id: int = 101,
    sequence: int = 1,
) -> TradeEvent:
    return TradeEvent(
        source="databento:GLBX.MDP3:trades",
        instrument=InstrumentSpec(root="NQ", continuous_symbol="NQ.c.0"),
        publisher_id=1,
        instrument_id=instrument_id,
        ts_event_ns=ts_event_ns,
        ts_recv_ns=ts_event_ns + 100,
        price_ticks=price_ticks,
        size=size,
        action="trade",
        aggressor_side="ask",
        flags=0,
        depth=0,
        sequence=sequence,
    )


def one_minute_spec(*, allowed_lateness_ns: int = 0) -> AggregationSpec:
    return AggregationSpec(
        timeframes=(Timeframe.ONE_MINUTE,),
        allowed_lateness_ns=allowed_lateness_ns,
    )


def test_ohlcv_uses_half_open_boundaries_and_preserves_identical_trades() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    start = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))
    first = trade(start, 100, size=2, sequence=1)

    aggregator.push(first)
    aggregator.push(first)
    aggregator.push(trade(start + 20_000_000_000, 104, size=3, sequence=2))
    aggregator.push(trade(start + 40_000_000_000, 99, size=1, sequence=3))
    boundary = aggregator.push(trade(start + 60_000_000_000, 101, sequence=4))

    assert len(boundary.bars) == 1
    bar = boundary.bars[0]
    assert (bar.open_ticks, bar.high_ticks, bar.low_ticks, bar.close_ticks) == (100, 104, 99, 99)
    assert bar.volume == 8
    assert bar.trade_count == 4
    assert bar.start_ns == start
    assert bar.end_ns == start + 60_000_000_000

    tail = aggregator.finish()
    assert len(tail.bars) == 1
    assert tail.bars[0].open_ticks == 101


def test_out_of_order_events_within_lateness_produce_the_same_bar() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    start = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))
    events = (
        trade(start + 1, 100, sequence=1),
        trade(start + 10, 102, sequence=2),
        trade(start + 20, 101, sequence=3),
    )
    spec = one_minute_spec(allowed_lateness_ns=30)

    ordered = MultiTimeframeAggregator(calendar, spec)
    permuted = MultiTimeframeAggregator(calendar, spec)
    for event in events:
        ordered.push(event)
    for event in (events[2], events[0], events[1]):
        permuted.push(event)

    ordered_bar = ordered.finish().bars[0]
    permuted_result = permuted.finish()
    assert ordered_bar.canonical_bytes() == permuted_result.bars[0].canonical_bytes()


def test_equal_timestamp_open_and_close_use_canonical_sequence_not_arrival() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    timestamp = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))
    sequence_one = trade(timestamp, 100, sequence=1)
    sequence_two = trade(timestamp, 101, sequence=2)

    ordered = MultiTimeframeAggregator(calendar, one_minute_spec())
    reversed_arrival = MultiTimeframeAggregator(calendar, one_minute_spec())
    for event in (sequence_one, sequence_two):
        ordered.push(event)
    for event in (sequence_two, sequence_one):
        reversed_arrival.push(event)

    ordered_bar = ordered.finish().bars[0]
    reversed_bar = reversed_arrival.finish().bars[0]
    assert ordered_bar.canonical_bytes() == reversed_bar.canonical_bytes()
    assert (ordered_bar.open_ticks, ordered_bar.close_ticks) == (100, 101)


def test_late_event_is_quarantined_and_does_not_mutate_final_bar() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    start = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))

    aggregator.push(trade(start + 1, 100))
    finalized = aggregator.push(trade(start + 60_000_000_000, 101))
    late = aggregator.push(trade(start + 30_000_000_000, 999))

    assert finalized.bars[0].high_ticks == 100
    assert late.bars == ()
    assert [issue.code for issue in late.issues] == [
        IssueCode.EVENT_TIME_REGRESSION,
        IssueCode.LATE_EVENT_AFTER_FINALIZATION,
    ]
    assert aggregator.finish().bars[0].high_ticks == 101


def test_event_behind_watermark_is_quarantined_before_it_can_reorder_an_open_bar() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(
        calendar,
        one_minute_spec(allowed_lateness_ns=5),
    )
    start = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))

    aggregator.push(trade(start + 20, 100))
    result = aggregator.push(trade(start + 10, 999))
    bar = aggregator.finish().bars[0]

    assert [issue.code for issue in result.issues] == [
        IssueCode.EVENT_TIME_REGRESSION,
        IssueCode.EVENT_BEHIND_WATERMARK,
    ]
    assert bar.high_ticks == 100


def test_direct_aggregation_builds_all_vision_timeframes_without_mixing_contracts() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar)
    timestamp = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))

    first = aggregator.push(trade(timestamp, 100, instrument_id=101))
    rolled = aggregator.push(trade(timestamp + 1, 200, instrument_id=202))
    result = aggregator.finish()
    bars = rolled.bars + result.bars

    assert first.bars == ()
    assert [issue.code for issue in rolled.issues] == [IssueCode.CONTRACT_BOUNDARY]
    assert {bar.timeframe for bar in bars} == set(Timeframe)
    assert {bar.instrument_id for bar in bars} == {101, 202}
    assert all(bar.open_ticks == bar.close_ticks for bar in bars)
    assert all(
        bar.quality is QualityState.DEGRADED for bar in rolled.bars if bar.instrument_id == 101
    )


def test_trusted_watermark_finalizes_a_quiet_live_bar_without_wall_clock_access() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    start = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))

    assert aggregator.push(trade(start + 1, 100)).bars == ()
    advanced = aggregator.advance_watermark("NQ", 101, start + 60_000_000_000)

    assert len(advanced.bars) == 1
    assert advanced.bars[0].quality is QualityState.COMPLETE
    behind = aggregator.push(trade(start + 2, 999))
    assert [issue.code for issue in behind.issues] == [IssueCode.EVENT_BEHIND_WATERMARK]


def test_event_outside_reviewed_calendar_horizon_is_a_typed_issue() -> None:
    calendar = CmeEquityIndexCalendar(
        version="one-day",
        coverage_start=date(2026, 6, 8),
        coverage_end=date(2026, 6, 9),
        provenance=("test-fixture",),
    )
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    outside = ns(datetime(2026, 6, 9, 22, 0, tzinfo=UTC))

    result = aggregator.push(trade(outside, 100))

    assert [issue.code for issue in result.issues] == [IssueCode.UNSUPPORTED_CALENDAR_RANGE]
    assert result.bars == ()


def test_trade_during_declared_pause_emits_issue_and_no_bar() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    pause = ns(datetime(2026, 3, 9, 20, 20, tzinfo=UTC))

    result = aggregator.push(trade(pause, 100))

    assert result.bars == ()
    assert [issue.code for issue in result.issues] == [IssueCode.TRADE_OUTSIDE_SESSION]
    assert aggregator.finish().bars == ()


def test_finish_is_idempotent_and_closes_the_finite_stream() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    aggregator = MultiTimeframeAggregator(calendar, one_minute_spec())
    timestamp = ns(datetime(2026, 6, 8, 13, 30, tzinfo=UTC))
    event = trade(timestamp, 100)
    aggregator.push(event)

    assert len(aggregator.finish().bars) == 1
    assert aggregator.finish().bars == ()
    with pytest.raises(MarketDataValidationError, match="finished"):
        aggregator.push(event)
