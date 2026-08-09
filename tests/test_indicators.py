"""Unit tests for stoic.indicators — hand-built fixtures only, no disk or network access."""

from __future__ import annotations

import pandas as pd
import pytest

from stoic.indicators import SMA_PERIODS, add_smas, sma


def _closes(values: list[float]) -> pd.Series:
    index = pd.date_range("2026-01-05", periods=len(values), freq="1D", tz="UTC")
    index.name = "ts_event"
    return pd.Series(values, index=index, name="close")


# ---------------------------------------------------------------------------
# sma
# ---------------------------------------------------------------------------


def test_sma_hand_computed_values():
    close = _closes([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(close, 3)
    # warm-up: first 2 NaN, then rolling mean of 3
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)  # mean(1,2,3)
    assert out.iloc[3] == pytest.approx(3.0)  # mean(2,3,4)
    assert out.iloc[4] == pytest.approx(4.0)  # mean(3,4,5)


def test_sma_warmup_is_exactly_period_minus_one_leading_nans():
    close = _closes([10.0, 20.0, 30.0, 40.0])
    period = 3
    out = sma(close, period)
    assert out.iloc[: period - 1].isna().all()
    assert out.iloc[period - 1:].notna().all()
    assert out.iloc[period - 1] == pytest.approx(sum([10.0, 20.0, 30.0]) / 3)


def test_sma_no_lookahead_truncation_is_bit_identical():
    close = _closes([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    period = 3
    full = sma(close, period)
    k = 5
    truncated = sma(close.iloc[:k], period)
    pd.testing.assert_series_equal(full.iloc[:k], truncated, check_names=False)


def test_sma_negative_control_min_periods_1_differs_on_first_value():
    """The fault this gate exists to catch: a partial-window average silently standing in for the
    real one. min_periods=1 produces a *different* first value than our warm-up-preserving sma."""
    close = _closes([1.0, 2.0, 3.0, 4.0, 5.0])
    period = 3
    correct = sma(close, period)
    faulty = close.rolling(period, min_periods=1).mean()
    assert not pd.isna(faulty.iloc[0])
    assert pd.isna(correct.iloc[0])
    assert faulty.iloc[0] != pytest.approx(correct.iloc[period - 1])


def test_sma_period_less_than_one_raises():
    close = _closes([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        sma(close, 0)


def test_sma_period_longer_than_frame_is_all_nan():
    close = _closes([1.0, 2.0, 3.0])
    out = sma(close, 10)
    assert out.isna().all()
    assert len(out) == 3


# ---------------------------------------------------------------------------
# add_smas
# ---------------------------------------------------------------------------


def _bars(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=len(closes), freq="1D", tz="UTC")
    index.name = "ts_event"
    return pd.DataFrame({"close": closes}, index=index)


def test_add_smas_adds_expected_columns():
    bars = _bars([float(i) for i in range(1, 25)])
    out = add_smas(bars, periods=(2, 3))
    assert "sma_2" in out.columns
    assert "sma_3" in out.columns
    assert out["sma_2"].iloc[1] == pytest.approx(1.5)


def test_add_smas_default_periods_match_spec():
    bars = _bars([float(i) for i in range(1, 210)])
    out = add_smas(bars)
    for period in SMA_PERIODS:
        assert f"sma_{period}" in out.columns


def test_add_smas_does_not_mutate_argument():
    bars = _bars([float(i) for i in range(1, 25)])
    pre_copy = bars.copy(deep=True)
    add_smas(bars, periods=(2, 3))
    pd.testing.assert_frame_equal(bars, pre_copy)
