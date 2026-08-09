"""Unit tests for stoic.structure — hand-built fixtures only, no disk or network access."""

from __future__ import annotations

import pandas as pd
import pytest

from stoic.candles import candle_structure
from stoic.structure import Direction, Phase, find_pullback_start, leg_phases, opens_pullback


def _bars(highs: list[float], lows: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=len(highs), freq="1D", tz="UTC")
    index.name = "ts_event"
    return pd.DataFrame({"high": highs, "low": lows}, index=index)


# ---------------------------------------------------------------------------
# opens_pullback -- BULLISH: lower high + lower low opens; any other shape does not
# ---------------------------------------------------------------------------


def test_bullish_lower_high_and_lower_low_opens():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 85.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is True


def test_bullish_lower_high_only_does_not_open():
    # low stays above the parent's low -- not a lower low.
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 92.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


def test_bullish_lower_low_only_does_not_open():
    # high matches the parent's high exactly -- not strictly lower.
    bars = _bars(highs=[110.0, 110.0], lows=[90.0, 85.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


def test_bullish_higher_high_and_higher_low_does_not_open():
    bars = _bars(highs=[110.0, 115.0], lows=[90.0, 95.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


# ---------------------------------------------------------------------------
# opens_pullback -- BEARISH: the four mirrors
# ---------------------------------------------------------------------------


def test_bearish_higher_low_and_higher_high_opens():
    bars = _bars(highs=[110.0, 115.0], lows=[90.0, 95.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is True


def test_bearish_higher_low_only_does_not_open():
    bars = _bars(highs=[110.0, 110.0], lows=[90.0, 95.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is False


def test_bearish_higher_high_only_does_not_open():
    bars = _bars(highs=[110.0, 115.0], lows=[90.0, 90.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is False


def test_bearish_lower_low_and_lower_high_does_not_open():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 85.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is False


# ---------------------------------------------------------------------------
# Inside bar and outside bar never open a pullback, either direction
# ---------------------------------------------------------------------------


def test_inside_bar_does_not_open_bullish():
    # lower high, but NOT a lower low (low >= parent low) -- the classic inside bar.
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 95.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


def test_outside_bar_does_not_open_bullish():
    # higher high AND lower low -- still makes a new extreme in the bullish direction.
    bars = _bars(highs=[110.0, 120.0], lows=[90.0, 80.0])
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


def test_inside_bar_does_not_open_bearish():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 95.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is False


def test_outside_bar_does_not_open_bearish():
    bars = _bars(highs=[110.0, 120.0], lows=[90.0, 80.0])
    assert opens_pullback(bars, 1, Direction.BEARISH) is False


# ---------------------------------------------------------------------------
# D-28 discrimination -- the load-bearing negative control.
#
# The material operationalises "the first candle that goes the other way" three ways:
#   (a) breaches the previous extreme  -- one side only, e.g. bullish: low[pos] < low[parent]
#   (b) fails to extend                -- one side only, e.g. bullish: high[pos] < high[parent]
#   (c) both                           -- D-28's reading, what opens_pullback implements
# The three readings differ exactly on inside and outside bars. Show each rejected reading WOULD
# open a pullback on the fixture built for it, and that opens_pullback does not -- proving this
# implementation is (c), not (a) and not (b).
# ---------------------------------------------------------------------------


def test_d28_discrimination_inside_bar_reading_b_would_open_but_ours_does_not():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 95.0])  # inside bar
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    parent = 0

    reading_a_breaches_previous_extreme = bool(low[1] < low[parent])
    reading_b_fails_to_extend = bool(high[1] < high[parent])

    assert reading_a_breaches_previous_extreme is False  # no breach on an inside bar
    assert reading_b_fails_to_extend is True  # (b) would wrongly open here
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


def test_d28_discrimination_outside_bar_reading_a_would_open_but_ours_does_not():
    bars = _bars(highs=[110.0, 120.0], lows=[90.0, 80.0])  # outside bar
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    parent = 0

    reading_a_breaches_previous_extreme = bool(low[1] < low[parent])
    reading_b_fails_to_extend = bool(high[1] < high[parent])

    assert reading_a_breaches_previous_extreme is True  # (a) would wrongly open here
    assert reading_b_fails_to_extend is False  # it extends -- higher high
    assert opens_pullback(bars, 1, Direction.BULLISH) is False


# ---------------------------------------------------------------------------
# Parent-bar reference: D-28's "one extension beyond the passage"
# ---------------------------------------------------------------------------


def test_parent_bar_reference_run_of_inside_bars_mid_leg():
    # bar0: parent bar (high=110, low=90)
    # bar1, bar2: a run of inside bars, both pointing at bar0
    # bar3: lower than bar1/bar2 on both extremes, but NOT lower than bar0's low
    bars = _bars(
        highs=[110.0, 105.0, 103.0, 102.0],
        lows=[90.0, 95.0, 97.0, 92.0],
    )
    structure = candle_structure(bars)
    assert structure["parent_pos"].tolist() == [-1, 0, 0, 0]

    assert opens_pullback(bars, 3, Direction.BULLISH, structure=structure) is False

    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    naive_open_vs_immediate_left = bool(high[3] < high[2] and low[3] < low[2])
    assert naive_open_vs_immediate_left is True  # against bar2 it would wrongly open


# ---------------------------------------------------------------------------
# Bounds validation
# ---------------------------------------------------------------------------


def test_opens_pullback_negative_pos_raises_instead_of_wrapping():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 85.0])
    with pytest.raises(ValueError):
        opens_pullback(bars, -1, Direction.BULLISH)


def test_opens_pullback_out_of_range_positive_pos_raises():
    bars = _bars(highs=[110.0, 105.0], lows=[90.0, 85.0])
    with pytest.raises(ValueError):
        opens_pullback(bars, 5, Direction.BULLISH)


def test_find_pullback_start_end_beyond_len_is_clamped():
    bars = _bars(
        highs=[110.0, 95.0, 130.0, 90.0],
        lows=[90.0, 80.0, 100.0, 70.0],
    )
    # end far beyond len(bars) must behave the same as end=None (defaults to len(bars)), not
    # scan past the frame.
    assert find_pullback_start(bars, Direction.BULLISH, start=1, end=1000) == 3
    assert find_pullback_start(bars, Direction.BULLISH, start=1, end=1000) == find_pullback_start(
        bars, Direction.BULLISH, start=1
    )


# ---------------------------------------------------------------------------
# find_pullback_start
# ---------------------------------------------------------------------------


def test_find_pullback_start_returns_none_when_leg_never_pulls_back():
    bars = _bars(
        highs=[100.0, 105.0, 110.0, 115.0, 120.0],
        lows=[90.0, 95.0, 100.0, 105.0, 110.0],
    )
    assert find_pullback_start(bars, Direction.BULLISH, start=0) is None


def test_find_pullback_start_excludes_start_and_respects_end():
    bars = _bars(
        highs=[110.0, 95.0, 130.0, 90.0],
        lows=[90.0, 80.0, 100.0, 70.0],
    )
    # bar1 (== start) would itself open a pullback against bar0, but start is excluded.
    assert opens_pullback(bars, 1, Direction.BULLISH) is True
    assert find_pullback_start(bars, Direction.BULLISH, start=1) == 3

    # bar3 is the only qualifying bar; end=3 cuts it out of the scan.
    assert find_pullback_start(bars, Direction.BULLISH, start=1, end=3) is None


# ---------------------------------------------------------------------------
# leg_phases
# ---------------------------------------------------------------------------


def test_leg_phases_labels_expansion_then_pullback():
    bars = _bars(highs=[100.0, 110.0, 90.0], lows=[90.0, 100.0, 80.0])
    phases = leg_phases(bars, Direction.BULLISH, start=0)
    assert phases.tolist() == [Phase.EXPANSION, Phase.EXPANSION, Phase.PULLBACK]
    assert list(phases.index) == list(bars.index)


def test_leg_phases_all_expansion_when_leg_never_pulls_back():
    bars = _bars(
        highs=[100.0, 105.0, 110.0],
        lows=[90.0, 95.0, 100.0],
    )
    phases = leg_phases(bars, Direction.BULLISH, start=0)
    assert phases.tolist() == [Phase.EXPANSION, Phase.EXPANSION, Phase.EXPANSION]
