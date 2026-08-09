"""Unit tests for stoic.candles — hand-built fixtures only, no disk or network access."""

from __future__ import annotations

import pandas as pd

from stoic.candles import candle_structure, inside_flags, parent_positions


def _bars(highs: list[float], lows: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=len(highs), freq="1D", tz="UTC")
    index.name = "ts_event"
    return pd.DataFrame({"high": highs, "low": lows}, index=index)


# ---------------------------------------------------------------------------
# The IBD shape: parent, inside, inside, breakout
# ---------------------------------------------------------------------------


def test_ibd_shape_parent_inside_inside_breakout():
    # bar0: parent (high=110, low=90)
    # bar1: inside bar0 (high=105, low=95)
    # bar2: inside bar0, but NOT inside bar1 (high=108, low=92) -- proves parent-bar reference
    # bar3: breaks out above bar0 (high=115, low=100)
    bars = _bars(
        highs=[110.0, 105.0, 108.0, 115.0],
        lows=[90.0, 95.0, 92.0, 100.0],
    )
    out = candle_structure(bars)
    assert out["is_inside"].tolist() == [False, True, True, False]
    assert out["parent_pos"].tolist() == [-1, 0, 0, 0]


def test_ibd_negative_control_naive_immediate_left_reading_differs():
    """The exact fault §5.2.8a exists to prevent: measuring 'inside' against the bar immediately
    to the left instead of the parent bar. bar2 here is inside the parent (bar0) but NOT inside its
    immediate left neighbour (bar1), so the two readings must disagree on bar2."""
    bars = _bars(
        highs=[110.0, 105.0, 108.0, 115.0],
        lows=[90.0, 95.0, 92.0, 100.0],
    )
    out = candle_structure(bars)

    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    naive_inside = [False] + [
        bool(high[i] <= high[i - 1] and low[i] >= low[i - 1]) for i in range(1, len(bars))
    ]

    assert naive_inside[2] is False  # bar2 is NOT inside bar1 (immediate left)
    assert bool(out["is_inside"].iloc[2]) is True  # but IS inside its parent, bar0
    assert naive_inside != out["is_inside"].tolist()


def test_outside_bar_is_not_inside():
    # bar1 has higher high AND lower low than bar0 -- an outside bar, never inside.
    bars = _bars(highs=[110.0, 120.0], lows=[90.0, 80.0])
    out = candle_structure(bars)
    assert out["is_inside"].tolist() == [False, False]
    assert out["parent_pos"].tolist() == [-1, 0]


def test_exact_equality_bar_is_inside_by_convention():
    # bar1 has the SAME high and low as bar0 -- pinned as inside per the module's documented
    # convention for the exact-equality case (not addressed by the material).
    bars = _bars(highs=[110.0, 110.0], lows=[90.0, 90.0])
    out = candle_structure(bars)
    assert out["is_inside"].tolist() == [False, True]
    assert out["parent_pos"].tolist() == [-1, 0]


def test_first_bar_is_never_inside_and_has_no_parent():
    bars = _bars(highs=[110.0], lows=[90.0])
    out = candle_structure(bars)
    assert out["is_inside"].tolist() == [False]
    assert out["parent_pos"].tolist() == [-1]


# ---------------------------------------------------------------------------
# thin accessors
# ---------------------------------------------------------------------------


def test_inside_flags_and_parent_positions_delegate_to_candle_structure():
    bars = _bars(
        highs=[110.0, 105.0, 108.0, 115.0],
        lows=[90.0, 95.0, 92.0, 100.0],
    )
    structure = candle_structure(bars)
    pd.testing.assert_series_equal(
        inside_flags(bars), structure["is_inside"], check_names=False
    )
    pd.testing.assert_series_equal(
        parent_positions(bars), structure["parent_pos"], check_names=False
    )
