"""Unit tests for stoic.bars — hand-built fixtures only, no disk or network access.

Real-parquet integration checks (60m vs vendor 1h, coverage counts, DST boundaries) live in
scripts/check_bar_spine.py, not here — this file is the fast, hermetic unit layer.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from stoic.bars import load_1m, resample
from stoic.sessions import ET


def _et(y: int, m: int, d: int, hh: int, mm: int = 0) -> pd.Timestamp:
    """Build a UTC Timestamp from a wall-clock instant in America/New_York."""
    return pd.Timestamp(datetime(y, m, d, hh, mm, tzinfo=ET)).tz_convert("UTC")


def _frame(index: pd.DatetimeIndex, **columns: list) -> pd.DataFrame:
    """A minimal 1m-bar-shaped frame: symbol/open/high/low/close/volume, indexed by ts_event."""
    frame = pd.DataFrame({"symbol": "TEST", **columns}, index=index)
    frame.index.name = "ts_event"
    return frame


# ---------------------------------------------------------------------------
# 1m passthrough
# ---------------------------------------------------------------------------


def test_resample_1m_returns_source_unchanged():
    frame = _frame(
        pd.DatetimeIndex([pd.Timestamp("2026-01-05", tz="UTC")]),
        open=[1.0],
        high=[1.0],
        low=[1.0],
        close=[1.0],
        volume=[1],
    )
    assert resample(frame, "1m") is frame


# ---------------------------------------------------------------------------
# hole handling + OHLC aggregation correctness
# ---------------------------------------------------------------------------


@pytest.fixture
def bars_with_hole() -> pd.DataFrame:
    """15 minutes of 1m bars: 00:00-04 (bucket A), a hole at 00:05-09, 00:10-14 (bucket C).

    Bucket A's OHLC fields are deliberately sourced from four different rows: open from minute 0,
    high from minute 2, low from minute 3, close from minute 4 — so a bug that reused one row for
    multiple fields would be caught.
    """
    base = pd.Timestamp("2026-01-05 00:00", tz="UTC")
    bucket_a = _frame(
        pd.date_range(base, periods=5, freq="1min"),
        open=[100.0, 100.0, 101.0, 102.0, 101.0],
        high=[101.0, 102.0, 105.0, 103.0, 104.0],
        low=[99.0, 99.0, 100.0, 90.0, 95.0],
        close=[100.0, 101.0, 102.0, 101.0, 98.0],
        volume=[10, 10, 10, 10, 10],
    )
    bucket_c = _frame(
        pd.date_range(base + pd.Timedelta(minutes=10), periods=5, freq="1min"),
        open=[200.0] * 5,
        high=[200.0] * 5,
        low=[200.0] * 5,
        close=[200.0] * 5,
        volume=[5] * 5,
    )
    frame = pd.concat([bucket_a, bucket_c]).sort_index()
    frame.index.name = "ts_event"
    return frame


def test_resample_drops_bucket_with_no_source_bars(bars_with_hole):
    out = resample(bars_with_hole, "5m")
    hole_bucket = pd.Timestamp("2026-01-05 00:05", tz="UTC")
    assert hole_bucket not in out.index
    assert len(out) == 2


def test_resample_ohlc_aggregation_from_distinct_bars(bars_with_hole):
    out = resample(bars_with_hole, "5m")
    bucket_a = out.loc[pd.Timestamp("2026-01-05 00:00", tz="UTC")]
    assert bucket_a["open"] == 100.0  # minute 0
    assert bucket_a["high"] == 105.0  # minute 2
    assert bucket_a["low"] == 90.0  # minute 3
    assert bucket_a["close"] == 98.0  # minute 4
    assert bucket_a["volume"] == 50
    assert bucket_a["source"] == "resampled-1m"

    bucket_c = out.loc[pd.Timestamp("2026-01-05 00:10", tz="UTC")]
    assert (bucket_c[["open", "high", "low", "close"]] == 200.0).all()
    assert bucket_c["volume"] == 25


# ---------------------------------------------------------------------------
# weekly grouping
# ---------------------------------------------------------------------------


def test_resample_weekly_groups_sunday_evening_through_friday():
    """Mon-Fri sessions land in one ISO-week bar; the next Sunday evening starts a new one."""
    # 10:00 ET on 2026-01-05..09 (Mon-Fri): session_date = same date, all ISO week (2026, 2).
    weekday_index = pd.DatetimeIndex([_et(2026, 1, d, 10) for d in range(5, 10)])
    # Sunday 2026-01-11, 18:00 ET is the instant the Monday 2026-01-12 session opens: ISO week
    # (2026, 3), even though the raw timestamp itself falls on a Sunday.
    sunday_evening = pd.DatetimeIndex([_et(2026, 1, 11, 18, 0)])
    index = weekday_index.append(sunday_evening).sort_values()

    frame = _frame(
        index,
        open=[100.0] * 6,
        high=[101.0] * 6,
        low=[99.0] * 6,
        close=[100.0] * 6,
        volume=[1] * 6,
    )

    daily = resample(frame, "1D")
    assert len(daily) == 6  # 5 weekday sessions + the Sunday-evening (-> Monday) session

    weekly = resample(frame, "1W")
    assert len(weekly) == 2
    assert weekly["week_start"].tolist() == [date(2026, 1, 5), date(2026, 1, 12)]


# ---------------------------------------------------------------------------
# validation: raise, don't warn
# ---------------------------------------------------------------------------


def test_resample_raises_on_invalid_ohlc():
    """resample validates its own output and raises rather than returning bad data."""
    frame = _frame(
        pd.DatetimeIndex([pd.Timestamp("2026-01-05 00:00", tz="UTC")]),
        open=[100.0],
        high=[95.0],  # high < low: invalid
        low=[105.0],
        close=[100.0],
        volume=[1],
    )
    with pytest.raises(ValueError, match="low <= open,close <= high"):
        resample(frame, "5m")


# ---------------------------------------------------------------------------
# argument validation
# ---------------------------------------------------------------------------


def test_load_1m_rejects_unknown_symbol():
    with pytest.raises(ValueError, match="unknown symbol"):
        load_1m("XX")


def test_resample_rejects_unknown_timeframe():
    frame = _frame(
        pd.date_range("2026-01-05", periods=2, freq="1min", tz="UTC"),
        open=[1.0, 1.0],
        high=[1.0, 1.0],
        low=[1.0, 1.0],
        close=[1.0, 1.0],
        volume=[1, 1],
    )
    with pytest.raises(ValueError, match="unknown timeframe"):
        resample(frame, "3m")
