"""SP1 CME equity-index session-calendar tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from stoic_derived.market_data.calendar import (
    CmeEquityIndexCalendar,
    SessionOverride,
    load_calendar_manifest,
)
from stoic_derived.market_data.model import Timeframe, UnsupportedCalendarRangeError


def make_calendar(
    *,
    version: str,
    overrides: tuple[SessionOverride, ...] = (),
) -> CmeEquityIndexCalendar:
    return CmeEquityIndexCalendar(
        version=version,
        coverage_start=date(2025, 1, 1),
        coverage_end=date(2027, 1, 1),
        overrides=overrides,
        provenance=("test-fixture",),
    )


def ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000_000) + delta.microseconds * 1_000


def test_calendar_assigns_sunday_open_to_monday_trading_date_across_spring_dst() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    sunday_open = ns(datetime(2026, 3, 8, 22, 0, tzinfo=UTC))

    session = calendar.session_at(sunday_open)
    bucket = calendar.bucket_at(sunday_open, Timeframe.DAILY)

    assert session is not None
    assert session.trading_date == date(2026, 3, 9)
    assert session.start_ns == sunday_open
    assert bucket is not None
    assert bucket.start_ns == sunday_open
    assert bucket.end_ns == ns(datetime(2026, 3, 9, 21, 0, tzinfo=UTC))


def test_calendar_assigns_fall_dst_open_to_monday_without_a_fixed_utc_offset() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    sunday_open = ns(datetime(2026, 11, 1, 23, 0, tzinfo=UTC))

    session = calendar.session_at(sunday_open)

    assert session is not None
    assert session.trading_date == date(2026, 11, 2)
    assert session.start_ns == sunday_open
    assert session.end_ns == ns(datetime(2026, 11, 2, 22, 0, tzinfo=UTC))


def test_calendar_excludes_maintenance_pause_and_cash_reference_window_is_half_open() -> None:
    calendar = make_calendar(version="cme-equity-v1")
    pause = ns(datetime(2026, 3, 9, 20, 20, tzinfo=UTC))  # 15:20 CDT
    cash_start = ns(datetime(2026, 3, 9, 13, 30, tzinfo=UTC))
    cash_end = ns(datetime(2026, 3, 9, 20, 0, tzinfo=UTC))
    pause_end = ns(datetime(2026, 3, 9, 20, 30, tzinfo=UTC))
    maintenance = ns(datetime(2026, 3, 9, 21, 30, tzinfo=UTC))

    assert calendar.is_regular_trading(pause) is False
    assert calendar.is_regular_trading(pause_end) is True
    assert calendar.bucket_at(pause, Timeframe.ONE_MINUTE) is None
    assert calendar.is_cash_reference(cash_start) is True
    assert calendar.is_cash_reference(cash_end) is False
    assert calendar.session_at(maintenance) is None


def test_calendar_overrides_control_weekly_bucket_and_fingerprint() -> None:
    calendar = make_calendar(
        version="cme-equity-v1",
        overrides=(
            SessionOverride(trading_date=date(2026, 3, 16), close_time=None, reason="holiday"),
            SessionOverride(
                trading_date=date(2026, 3, 20), close_time=time(12, 15), reason="early"
            ),
        ),
    )
    tuesday = ns(datetime(2026, 3, 17, 14, 0, tzinfo=UTC))
    friday_before_close = ns(datetime(2026, 3, 20, 17, 14, tzinfo=UTC))
    friday_close = ns(datetime(2026, 3, 20, 17, 15, tzinfo=UTC))

    weekly = calendar.bucket_at(tuesday, Timeframe.WEEKLY)

    assert calendar.session_for_trading_date(date(2026, 3, 16)) is None
    assert weekly is not None
    assert weekly.start_ns == ns(datetime(2026, 3, 16, 22, 0, tzinfo=UTC))
    assert weekly.end_ns == ns(datetime(2026, 3, 20, 17, 15, tzinfo=UTC))
    assert weekly.trading_date == date(2026, 3, 16)
    assert calendar.session_at(friday_before_close) is not None
    assert calendar.session_at(friday_close) is None
    assert len(calendar.fingerprint) == 64


def test_intraday_bucket_is_clipped_to_an_early_session_close() -> None:
    calendar = make_calendar(
        version="cme-equity-v1",
        overrides=(
            SessionOverride(
                trading_date=date(2026, 3, 20),
                close_time=time(12, 15),
                reason="early",
            ),
        ),
    )
    before_close = ns(datetime(2026, 3, 20, 17, 14, tzinfo=UTC))

    bucket = calendar.bucket_at(before_close, Timeframe.SIXTY_MINUTES)

    assert bucket is not None
    assert bucket.start_ns == ns(datetime(2026, 3, 20, 17, 0, tzinfo=UTC))
    assert bucket.end_ns == ns(datetime(2026, 3, 20, 17, 15, tzinfo=UTC))


def test_calendar_uses_half_open_boundaries_and_order_independent_override_fingerprint() -> None:
    holiday = SessionOverride(trading_date=date(2026, 7, 3), close_time=None, reason="holiday")
    early = SessionOverride(trading_date=date(2026, 7, 2), close_time=time(12, 15), reason="early")
    calendar = make_calendar(version="cme-equity-v1", overrides=(holiday, early))
    reordered = make_calendar(version="cme-equity-v1", overrides=(early, holiday))
    before_sunday_open = ns(datetime(2026, 3, 8, 21, 59, 59, 999_999, tzinfo=UTC))
    sunday_open = ns(datetime(2026, 3, 8, 22, 0, tzinfo=UTC))
    friday_close = ns(datetime(2026, 3, 13, 21, 0, tzinfo=UTC))

    intraday = calendar.bucket_at(sunday_open, Timeframe.ONE_MINUTE)

    assert calendar.session_at(before_sunday_open) is None
    assert calendar.session_at(sunday_open) is not None
    assert calendar.session_at(friday_close) is None
    assert intraday is not None
    assert intraday.start_ns == sunday_open
    assert intraday.end_ns == sunday_open + 60_000_000_000
    assert calendar.fingerprint == reordered.fingerprint


def test_calendar_fails_closed_outside_its_reviewed_horizon() -> None:
    calendar = CmeEquityIndexCalendar(
        version="bounded",
        coverage_start=date(2026, 6, 8),
        coverage_end=date(2026, 6, 9),
        provenance=("test-fixture",),
    )

    with pytest.raises(UnsupportedCalendarRangeError, match="2026-06-09"):
        calendar.session_for_trading_date(date(2026, 6, 9))

    wider = CmeEquityIndexCalendar(
        version="bounded",
        coverage_start=date(2026, 6, 8),
        coverage_end=date(2026, 6, 10),
        provenance=("test-fixture",),
    )
    assert calendar.fingerprint != wider.fingerprint


def test_committed_tail_schedule_loads_and_does_not_claim_christmas_coverage() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    calendar = load_calendar_manifest(
        repository_root / "config/market_data/calendars/cme-equity-index-2026-06-tail-v1.json"
    )

    assert calendar.session_for_trading_date(date(2026, 6, 8)) is not None
    with pytest.raises(UnsupportedCalendarRangeError, match="2025-12-25"):
        calendar.session_for_trading_date(date(2025, 12, 25))


def test_arbitrary_calendar_range_without_provenance_is_not_publishable() -> None:
    calendar = CmeEquityIndexCalendar(
        version="unreviewed",
        coverage_start=date(2025, 1, 1),
        coverage_end=date(2027, 1, 1),
    )

    with pytest.raises(UnsupportedCalendarRangeError, match="no reviewed"):
        calendar.session_for_trading_date(date(2025, 12, 25))
