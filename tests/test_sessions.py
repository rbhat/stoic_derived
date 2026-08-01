"""Unit tests for stoic.sessions — hand-built fixtures only, no disk or network access."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from stoic.sessions import (
    ET,
    PT,
    flatten_cutoff_utc,
    label_sessions,
    london_open_utc,
    ny_open_utc,
    session_close_utc,
    session_date,
    session_open_utc,
)


def _et(y: int, m: int, d: int, hh: int, mm: int = 0) -> pd.Timestamp:
    """Build a UTC Timestamp from a wall-clock instant in America/New_York."""
    return pd.Timestamp(datetime(y, m, d, hh, mm, tzinfo=ET)).tz_convert("UTC")


# ---------------------------------------------------------------------------
# session_date
# ---------------------------------------------------------------------------


def test_session_date_sunday_open_is_monday():
    """The session opening Sunday 18:00 ET has session_date equal to that Monday (spec example)."""
    index = pd.DatetimeIndex([_et(2026, 1, 4, 18, 0)])  # Sunday 18:00 ET
    result = session_date(index)
    assert result.iloc[0] == date(2026, 1, 5)


def test_session_date_shifts_at_1700_et():
    """Just before 17:00 ET stays on the same date; at/after 17:00 ET rolls to the next date."""
    index = pd.DatetimeIndex(
        [
            _et(2026, 1, 6, 16, 59),
            _et(2026, 1, 6, 17, 0),
            _et(2026, 1, 6, 17, 1),
        ]
    )
    result = session_date(index)
    assert list(result) == [date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 7)]


def test_session_date_across_fall_back_sunday():
    """Regression: the +1-day shift must land on the next calendar date even on the 25h fall-back
    day. A tz-aware `+ Timedelta(days=1)` instead adds 24 *real* hours, which on 2025-11-02 (US
    falls back) lands at 23:00 the *same* date rather than 00:00 the next one — both the 17:00 ET
    closing bar and the 18:00 ET opening bar were misdated to 2025-11-02 instead of 2025-11-03."""
    index = pd.DatetimeIndex([_et(2025, 11, 2, 17, 0), _et(2025, 11, 2, 18, 0)])
    result = session_date(index)
    assert list(result) == [date(2025, 11, 3), date(2025, 11, 3)]


def test_session_date_across_spring_forward_sunday():
    """Same boundary, the spring-forward direction (2026-03-08, a 23h day) — unaffected by the
    bug above, but asserted so a regression on either transition is caught symmetrically."""
    index = pd.DatetimeIndex([_et(2026, 3, 8, 17, 0), _et(2026, 3, 8, 18, 0)])
    result = session_date(index)
    assert list(result) == [date(2026, 3, 9), date(2026, 3, 9)]


def test_past_flatten_false_for_fall_back_sunday_opening_bar():
    """The 18:00 ET bar that opens the fall-back Sunday's session is nowhere near the 16:58 ET
    flatten cutoff of *its own* (correctly dated) session — this fails if session_date() misdates
    the bar back onto 2025-11-02, whose flatten cutoff it would then be long past."""
    index = pd.DatetimeIndex([_et(2025, 11, 2, 18, 0)])
    labels = label_sessions(index, bar_span=pd.Timedelta(minutes=5))
    assert labels["session_date"].iloc[0] == date(2025, 11, 3)
    assert not labels["past_flatten"].iloc[0]


# ---------------------------------------------------------------------------
# session phase / rth boundaries — exact instant and one minute either side
# ---------------------------------------------------------------------------


def test_session_phase_boundaries():
    # (year, month, day, hour, minute) -> expected (session, rth), on a plain non-DST Tuesday.
    cases = [
        # 18:00 ET: closed -> asia
        ((2026, 1, 6, 17, 59), "closed", False),
        ((2026, 1, 6, 18, 0), "asia", False),
        ((2026, 1, 6, 18, 1), "asia", False),
        # 03:00 ET: asia -> london
        ((2026, 1, 7, 2, 59), "asia", False),
        ((2026, 1, 7, 3, 0), "london", False),
        ((2026, 1, 7, 3, 1), "london", False),
        # 09:30 ET: london -> newyork, and rth turns on
        ((2026, 1, 7, 9, 29), "london", False),
        ((2026, 1, 7, 9, 30), "newyork", True),
        ((2026, 1, 7, 9, 31), "newyork", True),
        # 16:00 ET: rth turns off, still newyork
        ((2026, 1, 7, 15, 59), "newyork", True),
        ((2026, 1, 7, 16, 0), "newyork", False),
        ((2026, 1, 7, 16, 1), "newyork", False),
        # 17:00 ET: newyork -> closed
        ((2026, 1, 7, 16, 59), "newyork", False),
        ((2026, 1, 7, 17, 0), "closed", False),
        ((2026, 1, 7, 17, 1), "closed", False),
    ]
    index = pd.DatetimeIndex([_et(*ts) for ts, _, _ in cases])
    labels = label_sessions(index, bar_span=pd.Timedelta(minutes=1))

    for (ts, expected_session, expected_rth), (_, actual_session, actual_rth) in zip(
        cases, zip(index, labels["session"], labels["rth"], strict=True), strict=True
    ):
        assert actual_session == expected_session, f"{ts}: expected session {expected_session}"
        assert actual_rth == expected_rth, f"{ts}: expected rth {expected_rth}"


# ---------------------------------------------------------------------------
# is_ny_open containment on a 60m grid — must be exactly 1, and the 13:00/14:00 UTC bar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected_hour"),
    [
        ((2026, 1, 6), 14),  # January: ET is EST (UTC-5) -> 09:30 ET = 14:30 UTC
        ((2026, 7, 6), 13),  # July: ET is EDT (UTC-4) -> 09:30 ET = 13:30 UTC
    ],
)
def test_is_ny_open_marks_exactly_one_60m_bar(day, expected_hour):
    start = pd.Timestamp(*day, tz="UTC")
    index = pd.date_range(start, periods=24, freq="60min")
    labels = label_sessions(index, bar_span=pd.Timedelta(minutes=60))

    assert labels["is_ny_open"].sum() == 1
    marked = labels.index[labels["is_ny_open"]]
    assert marked[0].hour == expected_hour

    # The containment-vs-equality point the flag exists for: 09:30 ET carries a ":30", so the ET-UTC
    # offset (always a whole number of hours) never lands it on a 60m UTC grid line. An
    # equality-based check finds nothing; containment finds exactly the one bar.
    ny_instant = ny_open_utc(labels["session_date"].to_numpy())
    assert (index == ny_instant).sum() == 0


def test_is_london_open_marks_exactly_one_60m_bar():
    """03:00 ET *does* land on a 60m UTC grid line (whole-hour ET times always do) — containment
    still finds exactly the one bar the equality case would also happen to find here."""
    start = pd.Timestamp(2026, 1, 6, tz="UTC")
    index = pd.date_range(start, periods=24, freq="60min")
    labels = label_sessions(index, bar_span=pd.Timedelta(minutes=60))
    assert labels["is_london_open"].sum() == 1


# ---------------------------------------------------------------------------
# DST, both directions, on real transition dates
# ---------------------------------------------------------------------------


def test_ny_open_utc_dst_fall_back_2025_11_02():
    dates = [date(2025, 11, 1), date(2025, 11, 3)]
    result = ny_open_utc(dates)
    assert result[0] == pd.Timestamp("2025-11-01 13:30:00", tz="UTC")
    assert result[1] == pd.Timestamp("2025-11-03 14:30:00", tz="UTC")


def test_ny_open_utc_dst_spring_forward_2026_03_08():
    dates = [date(2026, 3, 6), date(2026, 3, 9)]
    result = ny_open_utc(dates)
    assert result[0] == pd.Timestamp("2026-03-06 14:30:00", tz="UTC")
    assert result[1] == pd.Timestamp("2026-03-09 13:30:00", tz="UTC")


def test_flatten_cutoff_utc_dst_both_directions():
    dates = [
        date(2025, 11, 1),  # before fall-back: PDT
        date(2025, 11, 3),  # after fall-back: PST
        date(2026, 3, 6),  # before spring-forward: PST
        date(2026, 3, 9),  # after spring-forward: PDT
    ]
    result = flatten_cutoff_utc(dates)
    assert result[0] == pd.Timestamp("2025-11-01 20:58:00", tz="UTC")  # PDT
    assert result[1] == pd.Timestamp("2025-11-03 21:58:00", tz="UTC")  # PST
    assert result[2] == pd.Timestamp("2026-03-06 21:58:00", tz="UTC")  # PST
    assert result[3] == pd.Timestamp("2026-03-09 20:58:00", tz="UTC")  # PDT


def test_trading_day_span_across_dst_transitions():
    """Open->close real-time span: 24h across fall-back, 22h across spring-forward, 23h normally."""
    normal = date(2025, 11, 1)
    fall_back = date(2025, 11, 2)
    spring_forward = date(2026, 3, 8)

    def span_hours(d: date) -> float:
        opened = session_open_utc([d])[0]
        closed = session_close_utc([d])[0]
        return (closed - opened).total_seconds() / 3600

    assert span_hours(normal) == 23.0
    assert span_hours(fall_back) == 24.0
    assert span_hours(spring_forward) == 22.0


def test_flatten_cutoff_is_two_minutes_before_close():
    """13:58 PT is always exactly 2 minutes before the 17:00 ET close, DST or not."""
    for d in (date(2025, 6, 15), date(2025, 12, 15)):
        gap = session_close_utc([d])[0] - flatten_cutoff_utc([d])[0]
        assert gap == pd.Timedelta(minutes=2)


# ---------------------------------------------------------------------------
# label_sessions bar_span inference / validation
# ---------------------------------------------------------------------------


def test_label_sessions_requires_bar_span_below_two_rows():
    index = pd.DatetimeIndex([_et(2026, 1, 6, 12, 0)])
    with pytest.raises(ValueError, match="bar_span"):
        label_sessions(index)


def test_label_sessions_infers_bar_span_from_modal_diff():
    index = pd.date_range(pd.Timestamp(2026, 1, 6, tz="UTC"), periods=5, freq="5min")
    inferred = label_sessions(index)
    explicit = label_sessions(index, bar_span=pd.Timedelta(minutes=5))
    pd.testing.assert_frame_equal(inferred, explicit)


def test_london_open_utc_matches_ny_open_utc_offset():
    """03:00 ET and 09:30 ET on the same session_date are 6h30m apart, DST notwithstanding."""
    d = [date(2026, 1, 6)]
    assert ny_open_utc(d)[0] - london_open_utc(d)[0] == pd.Timedelta(hours=6, minutes=30)


def test_pt_zone_used_for_flatten_not_hardcoded_offset():
    """Sanity check that PT is the America/Los_Angeles zone the module claims to use."""
    assert PT.key == "America/Los_Angeles"
