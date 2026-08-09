"""Unit tests for stoic.levels — hand-built fixtures only, no disk or network access.

Fixtures stand in for the frames `stoic.bars.resample(bars, "1D" / "1W")` produce: a `session_date`
column (daily) / `week_start` column (weekly), OHLC columns, indexed by an arbitrary monotonic
UTC DatetimeIndex — these functions never read the index itself, only the session_date/week_start
columns and OHLC.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stoic.levels import (
    MONTHS_LOOKBACK,
    htf_levels,
    month_close_extremes,
    previous_day_levels,
    previous_week_levels,
)


def _daily(
    dates: list[date], high: list[float], low: list[float], close: list[float]
) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates], name="ts_event")
    return pd.DataFrame(
        {"session_date": dates, "high": high, "low": low, "close": close}, index=index
    )


def _weekly(
    week_starts: list[date], high: list[float], low: list[float], close: list[float]
) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in week_starts], name="ts_event")
    return pd.DataFrame(
        {"week_start": week_starts, "high": high, "low": low, "close": close}, index=index
    )


# ---------------------------------------------------------------------------
# previous_day_levels
# ---------------------------------------------------------------------------


def test_previous_day_levels_over_4_sessions():
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8)]
    daily = _daily(
        dates,
        high=[100.0, 110.0, 105.0, 120.0],
        low=[90.0, 95.0, 98.0, 101.0],
        close=[95.0, 108.0, 103.0, 115.0],
    )
    out = previous_day_levels(daily)

    assert pd.isna(out.loc[dates[0], "pdh"])
    assert pd.isna(out.loc[dates[0], "pdl"])
    assert pd.isna(out.loc[dates[0], "pdc"])

    assert out.loc[dates[1], "pdh"] == pytest.approx(100.0)
    assert out.loc[dates[1], "pdl"] == pytest.approx(90.0)
    assert out.loc[dates[1], "pdc"] == pytest.approx(95.0)

    assert out.loc[dates[2], "pdh"] == pytest.approx(110.0)
    assert out.loc[dates[2], "pdl"] == pytest.approx(95.0)
    assert out.loc[dates[2], "pdc"] == pytest.approx(108.0)

    assert out.loc[dates[3], "pdh"] == pytest.approx(105.0)
    assert out.loc[dates[3], "pdl"] == pytest.approx(98.0)
    assert out.loc[dates[3], "pdc"] == pytest.approx(103.0)


def test_previous_day_levels_no_lookahead_truncation_unchanged():
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8)]
    daily = _daily(
        dates,
        high=[100.0, 110.0, 105.0, 120.0],
        low=[90.0, 95.0, 98.0, 101.0],
        close=[95.0, 108.0, 103.0, 115.0],
    )
    full = previous_day_levels(daily)
    k = 3
    truncated = previous_day_levels(daily.iloc[:k])
    pd.testing.assert_frame_equal(full.iloc[:k], truncated)


# ---------------------------------------------------------------------------
# previous_week_levels
# ---------------------------------------------------------------------------


def test_previous_week_levels_skipped_holiday_week_resolves_to_previous_present_week():
    # ISO weeks: Jan5 -> week2, Jan12 -> week3, Jan19 -> week4 (MISSING/holiday, no row),
    # Jan26 -> week5.
    weekly = _weekly(
        week_starts=[date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 26)],
        high=[110.0, 120.0, 130.0],
        low=[90.0, 95.0, 100.0],
        close=[105.0, 115.0, 125.0],
    )
    # A session inside week5 (Jan26's ISO week) -- its previous week is week4, which does not
    # exist as a row (holiday); the previous *present* week is week3.
    daily = _daily(
        [date(2026, 1, 27)],
        high=[999.0],
        low=[999.0],
        close=[999.0],
    )
    out = previous_week_levels(daily, weekly)
    row = out.loc[date(2026, 1, 27)]
    assert row["pwc"] == pytest.approx(115.0)
    assert row["pwh"] == pytest.approx(120.0)
    assert row["plow"] == pytest.approx(95.0)


def test_previous_week_levels_first_week_is_nan():
    weekly = _weekly(
        week_starts=[date(2026, 1, 5), date(2026, 1, 12)],
        high=[110.0, 120.0],
        low=[90.0, 95.0],
        close=[105.0, 115.0],
    )
    daily = _daily([date(2026, 1, 5)], high=[999.0], low=[999.0], close=[999.0])
    out = previous_week_levels(daily, weekly)
    row = out.loc[date(2026, 1, 5)]
    assert pd.isna(row["pwc"])
    assert pd.isna(row["pwh"])
    assert pd.isna(row["plow"])


# ---------------------------------------------------------------------------
# month_close_extremes
# ---------------------------------------------------------------------------


def _month_extremes_fixture() -> pd.DataFrame:
    # January: highest HIGH (130) and lowest LOW (80) land on different sessions from the
    # highest/lowest CLOSE (112 / 97). February: a single session to read month_1 off of.
    dates = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 2, 2),
    ]
    high = [110.0, 130.0, 120.0, 115.0, 999.0]
    low = [95.0, 90.0, 80.0, 98.0, 999.0]
    close = [100.0, 105.0, 112.0, 97.0, 999.0]
    return _daily(dates, high, low, close)


def test_hcom_lcom_negative_control_uses_close_not_high_low():
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)
    feb_row = out.loc[date(2026, 2, 2)]

    assert feb_row["month_1"] == pd.Period("2026-01", freq="M")
    assert feb_row["hcom_m1"] == pytest.approx(112.0)  # highest CLOSE
    assert feb_row["lcom_m1"] == pytest.approx(97.0)  # lowest CLOSE

    # explicit: these differ from the high/low-based reading a "simplification" might produce
    assert feb_row["hcom_m1"] != pytest.approx(130.0)  # highest HIGH
    assert feb_row["lcom_m1"] != pytest.approx(80.0)  # lowest LOW


def test_hcom_mtd_nan_on_first_session_equals_prior_close_on_second():
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)

    first = out.loc[date(2026, 1, 5)]
    assert pd.isna(first["hcom_mtd"])
    assert pd.isna(first["lcom_mtd"])

    second = out.loc[date(2026, 1, 6)]
    assert second["hcom_mtd"] == pytest.approx(100.0)  # Jan 5's close
    assert second["lcom_mtd"] == pytest.approx(100.0)


def test_hcom_mtd_resets_at_month_boundary_no_carry_over():
    # Feb 2 is February's first session, with January's history behind it. hcom_mtd/lcom_mtd
    # must not carry January's running extremes across the month boundary.
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)
    feb_first = out.loc[date(2026, 2, 2)]
    assert pd.isna(feb_first["hcom_mtd"])
    assert pd.isna(feb_first["lcom_mtd"])


def test_hcom_mtd_is_nan_tolerant_running_extreme():
    # closes [100, 105, NaN, 97, 110] within one month. hcom_mtd/lcom_mtd is the running
    # extreme of *prior* closes, and must skip over the NaN close rather than propagating it
    # forward as NaN into later sessions.
    dates = [
        date(2026, 3, 2),
        date(2026, 3, 3),
        date(2026, 3, 4),
        date(2026, 3, 5),
        date(2026, 3, 6),
    ]
    daily = _daily(
        dates,
        high=[100.0, 105.0, 100.0, 97.0, 110.0],
        low=[100.0, 105.0, 100.0, 97.0, 110.0],
        close=[100.0, 105.0, float("nan"), 97.0, 110.0],
    )
    out = month_close_extremes(daily)
    assert pd.isna(out.loc[dates[0], "hcom_mtd"])
    assert out.loc[dates[1], "hcom_mtd"] == pytest.approx(100.0)
    assert out.loc[dates[2], "hcom_mtd"] == pytest.approx(105.0)
    # the row that follows the NaN close: must still be 105, not NaN carried forward from it.
    assert out.loc[dates[3], "hcom_mtd"] == pytest.approx(105.0)
    assert out.loc[dates[4], "hcom_mtd"] == pytest.approx(105.0)

    assert pd.isna(out.loc[dates[0], "lcom_mtd"])
    assert out.loc[dates[1], "lcom_mtd"] == pytest.approx(100.0)
    assert out.loc[dates[2], "lcom_mtd"] == pytest.approx(100.0)
    assert out.loc[dates[3], "lcom_mtd"] == pytest.approx(100.0)
    assert out.loc[dates[4], "lcom_mtd"] == pytest.approx(97.0)


def test_month_1_and_month_2_nan_where_history_does_not_reach():
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)
    first = out.loc[date(2026, 1, 5)]
    assert pd.isna(first["hcom_m1"])
    assert pd.isna(first["lcom_m1"])
    assert pd.isna(first["hcom_m2"])
    assert pd.isna(first["lcom_m2"])


def test_month_close_extremes_carries_exactly_months_lookback_slots():
    # MONTHS_LOOKBACK (D-8) governs the number of month slots: month/month_1/month_2 and no more.
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)
    assert MONTHS_LOOKBACK == 3
    month_cols = [c for c in out.columns if c == "month" or c.startswith("month_")]
    assert len(month_cols) == MONTHS_LOOKBACK
    assert set(month_cols) == {"month", "month_1", "month_2"}


def test_month_column_is_calendar_month_of_session_date():
    daily = _month_extremes_fixture()
    out = month_close_extremes(daily)
    assert out.loc[date(2026, 1, 5), "month"] == pd.Period("2026-01", freq="M")
    assert out.loc[date(2026, 2, 2), "month"] == pd.Period("2026-02", freq="M")


# ---------------------------------------------------------------------------
# htf_levels
# ---------------------------------------------------------------------------


def test_htf_levels_joins_all_three():
    dates = [date(2026, 1, 5), date(2026, 1, 6)]
    daily = _daily(dates, high=[100.0, 110.0], low=[90.0, 95.0], close=[95.0, 108.0])
    weekly = _weekly([date(2026, 1, 5)], high=[110.0], low=[90.0], close=[105.0])

    out = htf_levels(daily, weekly)
    for col in ("pdh", "pdl", "pdc", "pwc", "pwh", "plow", "hcom_mtd", "lcom_mtd", "month"):
        assert col in out.columns
    assert len(out) == 2


def test_htf_levels_no_lookahead_truncation_unchanged():
    # Covers month_close_extremes and previous_week_levels, which (unlike previous_day_levels)
    # had no no-lookahead gate: a leak in either would hide here.
    dates = [
        date(2026, 1, 5),  # week starting 2026-01-05
        date(2026, 1, 6),
        date(2026, 1, 12),  # week starting 2026-01-12
        date(2026, 1, 13),
        date(2026, 1, 20),  # week starting 2026-01-19
        date(2026, 1, 26),  # week starting 2026-01-26
        date(2026, 2, 2),  # week starting 2026-02-02
        date(2026, 2, 3),
        date(2026, 2, 9),  # week starting 2026-02-09
        date(2026, 2, 10),
    ]
    daily = _daily(
        dates,
        high=[100.0, 110.0, 105.0, 120.0, 115.0, 125.0, 130.0, 118.0, 122.0, 128.0],
        low=[90.0, 95.0, 98.0, 101.0, 100.0, 108.0, 112.0, 105.0, 110.0, 115.0],
        close=[95.0, 108.0, 103.0, 115.0, 109.0, 119.0, 124.0, 111.0, 117.0, 121.0],
    )
    week_starts = [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
        date(2026, 2, 2),
        date(2026, 2, 9),
    ]
    weekly = _weekly(
        week_starts,
        high=[110.0, 120.0, 115.0, 125.0, 130.0, 122.0],
        low=[90.0, 98.0, 100.0, 108.0, 112.0, 110.0],
        close=[108.0, 115.0, 109.0, 119.0, 124.0, 117.0],
    )

    full = htf_levels(daily, weekly)

    # Truncate daily after session k=7 (through 2026-02-02); the weekly fixture is truncated to
    # weeks starting at or before that last kept session's own ISO Monday (2026-02-02).
    k = 7
    last_kept_week_start = date(2026, 2, 2)
    daily_truncated = daily.iloc[:k]
    weekly_truncated = weekly[weekly["week_start"] <= last_kept_week_start]

    truncated = htf_levels(daily_truncated, weekly_truncated)
    pd.testing.assert_frame_equal(full.iloc[:k], truncated)


def test_htf_levels_rejects_duplicate_session_date():
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 6), date(2026, 1, 8)]
    daily = _daily(
        dates,
        high=[100.0, 110.0, 105.0, 120.0],
        low=[90.0, 95.0, 98.0, 101.0],
        close=[95.0, 108.0, 103.0, 115.0],
    )
    weekly = _weekly([date(2026, 1, 5)], high=[110.0], low=[90.0], close=[105.0])
    with pytest.raises(ValueError):
        htf_levels(daily, weekly)
