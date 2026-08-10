"""Unit tests for stoic.judgment — hand-built fixtures only, no disk or network access.

D-29: the close must sit beyond its reference by >= 10% of the **parent bar's** high-low range.
Every fixture below sizes the parent bar so the threshold is a round number, and each positive case
is paired with a negative control that fails it by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stoic.judgment import (
    MEANINGFUL_FRACTION,
    MIN_BASE_CANDLES,
    attach_parent_pos,
    decided_judgment,
    find_base,
    is_meaningful_break,
    is_meaningful_close,
    select_boundary_from_base,
)
from stoic.sequence import BaseSpan, HorizontalBoundary
from stoic.structure import Direction


def _bars(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    sma10: list[float] | None = None,
    sma20: list[float] | None = None,
) -> pd.DataFrame:
    n = len(highs)
    index = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    index.name = "ts_event"
    frame = pd.DataFrame(
        {
            "high": highs,
            "low": lows,
            "close": closes,
            "sma_10": sma10 if sma10 is not None else [np.nan] * n,
            "sma_20": sma20 if sma20 is not None else [np.nan] * n,
        },
        index=index,
    )
    return attach_parent_pos(frame)


# ---------------------------------------------------------------------------
# The threshold itself
# ---------------------------------------------------------------------------


def test_fraction_is_the_recorded_decision():
    """D-29's number. If this changes, the §11 row and docs/STATE.md change with it."""
    assert MEANINGFUL_FRACTION == 0.10


# ---------------------------------------------------------------------------
# is_meaningful_close — measured from the boundary (§2.3.4)
# ---------------------------------------------------------------------------
# bar0 is the parent: high=100, low=0 -> range 100 -> threshold 10.0
# bar1 is the confirming bar, not inside bar0, so its parent is bar0.


def test_bullish_close_clears_ten_percent_of_parent_range():
    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 121.0])
    assert bars["parent_pos"].iat[1] == 0
    # boundary 110, close 121 -> excursion 11.0 >= 10.0
    assert is_meaningful_close(bars, 1, HorizontalBoundary(110.0), Direction.BULLISH) is True


def test_bullish_close_short_of_the_threshold_is_not_meaningful():
    """Negative control: same bars, excursion 9.0 < 10.0. Beyond the boundary, still not enough."""
    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 119.0])
    assert is_meaningful_close(bars, 1, HorizontalBoundary(110.0), Direction.BULLISH) is False


def test_bullish_close_exactly_at_the_threshold_confirms():
    """`>=`, not `>` — stated so the boundary case is a decision and not an accident."""
    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 120.0])
    assert is_meaningful_close(bars, 1, HorizontalBoundary(110.0), Direction.BULLISH) is True


def test_bearish_close_mirrors_the_bullish_case():
    bars = _bars(highs=[100.0, 30.0], lows=[0.0, -30.0], closes=[50.0, -21.0])
    # boundary -10, close -21 -> excursion 11.0 >= 10.0
    assert is_meaningful_close(bars, 1, HorizontalBoundary(-10.0), Direction.BEARISH) is True


def test_bearish_close_short_of_the_threshold_is_not_meaningful():
    bars = _bars(highs=[100.0, 30.0], lows=[0.0, -30.0], closes=[50.0, -19.0])
    assert is_meaningful_close(bars, 1, HorizontalBoundary(-10.0), Direction.BEARISH) is False


def test_close_on_the_wrong_side_of_the_boundary_is_never_meaningful():
    """Excursion is signed, so asking before the mechanical precondition holds returns False."""
    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 105.0])
    assert is_meaningful_close(bars, 1, HorizontalBoundary(110.0), Direction.BULLISH) is False


def test_sloping_boundary_is_evaluated_at_this_bar():
    """§2.2.7: the boundary need not be horizontal. level_at(pos) is the whole contract."""

    class _Sloped:
        def level_at(self, pos: int) -> float:
            return 100.0 + 10.0 * pos

    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 121.0])
    # at pos 1 the level is 110 -> excursion 11.0 >= 10.0
    assert is_meaningful_close(bars, 1, _Sloped(), Direction.BULLISH) is True


# ---------------------------------------------------------------------------
# The parent bar is the yardstick, not the previous bar
# ---------------------------------------------------------------------------


def test_inside_bar_run_does_not_shrink_the_yardstick():
    """The reason D-29 says *parent*, not *previous*.

    bar0 parent (range 100 -> threshold 10). bar1 and bar2 are inside it with tiny ranges. bar3
    breaks out; its parent is still bar0, so the threshold stays 10.0 rather than collapsing to
    0.2 (10% of bar2's range).
    """
    bars = _bars(
        highs=[100.0, 60.0, 56.0, 130.0],
        lows=[0.0, 40.0, 54.0, 100.0],
        closes=[50.0, 50.0, 55.0, 119.0],
    )
    assert list(bars["parent_pos"]) == [-1, 0, 0, 0]
    # excursion 9.0 against the parent's threshold of 10.0 -> not meaningful.
    assert is_meaningful_close(bars, 3, HorizontalBoundary(110.0), Direction.BULLISH) is False
    # Negative control for the rejected reading: had the *previous* bar (range 2.0) been the
    # yardstick, the threshold would be 0.2 and this same bar would have confirmed.
    prev_span = bars["high"].iat[2] - bars["low"].iat[2]
    assert MEANINGFUL_FRACTION * prev_span <= 119.0 - 110.0


def test_first_bar_has_no_parent_and_cannot_confirm():
    """Convention 1: no yardstick -> False, never a pass."""
    bars = _bars(highs=[100.0], lows=[0.0], closes=[99.0])
    assert bars["parent_pos"].iat[0] == -1
    assert is_meaningful_close(bars, 0, HorizontalBoundary(10.0), Direction.BULLISH) is False


def test_non_finite_parent_range_cannot_confirm():
    """Convention 2: a NaN yardstick is unevaluable, not permissive."""
    bars = _bars(highs=[np.nan, 130.0], lows=[np.nan, 100.0], closes=[50.0, 121.0])
    assert is_meaningful_close(bars, 1, HorizontalBoundary(110.0), Direction.BULLISH) is False


# ---------------------------------------------------------------------------
# is_meaningful_break — measured from the further MA (§2.1.1)
# ---------------------------------------------------------------------------


def test_bullish_break_measures_from_the_higher_ma():
    """"Beyond both" means the binding reference is max(sma_10, sma_20)."""
    bars = _bars(
        highs=[100.0, 130.0],
        lows=[0.0, 100.0],
        closes=[50.0, 121.0],
        sma10=[np.nan, 105.0],
        sma20=[np.nan, 110.0],
    )
    # further MA is 110 -> excursion 11.0 >= 10.0
    assert is_meaningful_break(bars, 1, Direction.BULLISH) is True


def test_bullish_break_fails_when_only_the_nearer_ma_is_cleared_well():
    """Negative control: 121 clears sma_10 (105) by 16 but sma_20 (110) by only 9."""
    bars = _bars(
        highs=[100.0, 130.0],
        lows=[0.0, 100.0],
        closes=[50.0, 119.0],
        sma10=[np.nan, 105.0],
        sma20=[np.nan, 110.0],
    )
    assert MEANINGFUL_FRACTION * 100.0 <= 119.0 - 105.0  # would pass against the nearer MA
    assert is_meaningful_break(bars, 1, Direction.BULLISH) is False


def test_bearish_break_measures_from_the_lower_ma():
    bars = _bars(
        highs=[100.0, 30.0],
        lows=[0.0, -30.0],
        closes=[50.0, -21.0],
        sma10=[np.nan, -5.0],
        sma20=[np.nan, -10.0],
    )
    # further MA is -10 -> excursion 11.0 >= 10.0
    assert is_meaningful_break(bars, 1, Direction.BEARISH) is True


def test_bearish_break_short_of_the_threshold_is_not_meaningful():
    bars = _bars(
        highs=[100.0, 30.0],
        lows=[0.0, -30.0],
        closes=[50.0, -19.0],
        sma10=[np.nan, -5.0],
        sma20=[np.nan, -10.0],
    )
    assert is_meaningful_break(bars, 1, Direction.BEARISH) is False


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_missing_parent_pos_column_raises_rather_than_guessing():
    frame = pd.DataFrame(
        {"high": [100.0, 130.0], "low": [0.0, 100.0], "close": [50.0, 121.0]},
        index=pd.date_range("2026-01-05", periods=2, freq="5min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="parent_pos"):
        is_meaningful_close(frame, 1, HorizontalBoundary(110.0), Direction.BULLISH)


def test_attach_parent_pos_is_idempotent():
    bars = _bars(highs=[100.0, 130.0], lows=[0.0, 100.0], closes=[50.0, 121.0])
    again = attach_parent_pos(bars)
    assert list(again["parent_pos"]) == list(bars["parent_pos"])
    assert list(again.columns) == list(bars.columns)


def test_decided_judgment_fills_all_four_from_recorded_decisions():
    """Every default is a §11 decision: D-29, D-34, D-30. `find_base` gained its default when
    D-34 closed the last unquantified term — this test asserted the absence of one until then."""
    judgment = decided_judgment()

    assert judgment.is_meaningful_break is is_meaningful_break
    assert judgment.is_meaningful_close is is_meaningful_close
    assert judgment.find_base is find_base  # D-34's default
    assert judgment.select_boundary is select_boundary_from_base  # D-30's default


def test_decided_judgment_defaults_are_overridable():
    """§2.2.7's sloping case (O-18) and D-34's rejected rival constructions are supplied by
    substitution, not by a flag — which is what keeps them cheap to replay against this one."""
    sentinel_base, sentinel_boundary = object(), object()
    judgment = decided_judgment(sentinel_base, sentinel_boundary)
    assert judgment.find_base is sentinel_base
    assert judgment.select_boundary is sentinel_boundary


# ---------------------------------------------------------------------------
# select_boundary_from_base — the base's close extreme, Step 1 side (D-30)
# ---------------------------------------------------------------------------


def test_bullish_boundary_is_the_highest_close_of_the_base():
    bars = _bars(
        highs=[100.0, 118.0, 112.0, 100.0],
        lows=[90.0, 100.0, 100.0, 90.0],
        closes=[95.0, 109.0, 111.0, 95.0],
    )
    boundary = select_boundary_from_base(bars, BaseSpan(1, 2), Direction.BULLISH)
    assert boundary == HorizontalBoundary(111.0)


def test_bearish_boundary_is_the_lowest_close_of_the_base():
    bars = _bars(
        highs=[100.0, 118.0, 112.0, 100.0],
        lows=[90.0, 100.0, 100.0, 90.0],
        closes=[95.0, 109.0, 111.0, 95.0],
    )
    boundary = select_boundary_from_base(bars, BaseSpan(1, 2), Direction.BEARISH)
    assert boundary == HorizontalBoundary(109.0)


def test_boundary_uses_closes_not_wicks():
    """Negative control for the rejected reading (D-30, precedent §7.3 / D-8).

    The base's highest *high* is 118.0 but its highest *close* is 111.0. A wick-based line would
    sit 7 points higher and Step 3 would trigger later, so the two readings are not equivalent.
    """
    bars = _bars(
        highs=[100.0, 118.0, 112.0, 100.0],
        lows=[90.0, 100.0, 100.0, 90.0],
        closes=[95.0, 109.0, 111.0, 95.0],
    )
    boundary = select_boundary_from_base(bars, BaseSpan(1, 2), Direction.BULLISH)
    assert boundary.level_at(3) == 111.0
    assert bars["high"].iloc[1:3].max() == 118.0  # what the wick reading would have given


def test_boundary_span_is_inclusive_of_both_ends():
    bars = _bars(
        highs=[100.0] * 4,
        lows=[90.0] * 4,
        closes=[95.0, 96.0, 97.0, 98.0],
    )
    assert select_boundary_from_base(bars, BaseSpan(0, 3), Direction.BULLISH) == HorizontalBoundary(
        98.0
    )
    assert select_boundary_from_base(bars, BaseSpan(0, 1), Direction.BULLISH) == HorizontalBoundary(
        96.0
    )


def test_boundary_cannot_see_past_the_base():
    """§2.2.8 is enforced structurally, but the selector must not reach forward either."""
    bars = _bars(
        highs=[100.0] * 4,
        lows=[90.0] * 4,
        closes=[95.0, 96.0, 97.0, 999.0],  # bar 3 is outside the base
    )
    boundary = select_boundary_from_base(bars, BaseSpan(0, 2), Direction.BULLISH)
    assert boundary == HorizontalBoundary(97.0)


def test_degenerate_span_returns_none_rather_than_a_fallback():
    """§2.2.9 already defines the no-clean-answer case as *wait*."""
    bars = _bars(highs=[100.0, 100.0], lows=[90.0, 90.0], closes=[95.0, 96.0])
    assert select_boundary_from_base(bars, BaseSpan(1, 0), Direction.BULLISH) is None


def test_all_nan_closes_return_none():
    bars = _bars(highs=[100.0, 100.0], lows=[90.0, 90.0], closes=[np.nan, np.nan])
    assert select_boundary_from_base(bars, BaseSpan(0, 1), Direction.BULLISH) is None


def test_boundary_feeds_the_confirmation_test_end_to_end():
    """D-30 picks the line; D-29 then judges the close beyond it. The two compose."""
    # base = bars 0-1, highest close 100.0 -> boundary 100.0
    # bar 2 is the parent for bar 3 (range 40 -> threshold 4.0)
    bars = _bars(
        highs=[100.0, 100.0, 120.0, 130.0],
        lows=[90.0, 90.0, 80.0, 100.0],
        closes=[99.0, 100.0, 95.0, 104.5],
    )
    boundary = select_boundary_from_base(bars, BaseSpan(0, 1), Direction.BULLISH)
    assert boundary == HorizontalBoundary(100.0)
    assert bars["parent_pos"].iat[3] == 2
    # excursion 4.5 >= 0.10 * 40 = 4.0
    assert is_meaningful_close(bars, 3, boundary, Direction.BULLISH) is True
    # negative control: a close of 103.5 clears the boundary but not the threshold
    bars2 = _bars(
        highs=[100.0, 100.0, 120.0, 130.0],
        lows=[90.0, 90.0, 80.0, 100.0],
        closes=[99.0, 100.0, 95.0, 103.5],
    )
    assert is_meaningful_close(bars2, 3, boundary, Direction.BULLISH) is False


# ---------------------------------------------------------------------------
# find_base — the obvious base as the residual state (D-34, §2.2.5a)
#
# Trending = two consecutive NON-INSIDE candles extending the same way against the parent bar.
# Basing = anything else. Every fixture below is built from explicit highs/lows so the
# classification of each candle can be read off the numbers; closes are inert here.
# ---------------------------------------------------------------------------


def _hl(highs: list[float], lows: list[float]) -> pd.DataFrame:
    """A frame for find_base: only the extremes matter, so closes are the midpoints."""
    return _bars(highs, lows, [(h + low) / 2 for h, low in zip(highs, lows, strict=True)])


def test_find_base_none_while_the_leg_is_trending():
    """A monotone run of same-way extensions is trending, so there is no base. (D-34)"""
    bars = _hl([10, 11, 12, 13, 14, 15], [0, 1, 2, 3, 4, 5])
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_none_while_the_leg_is_trending_down():
    """Symmetric: a down-leg is trending too, so the return after Step 1 is not yet a base."""
    bars = _hl([15, 14, 13, 12, 11, 10], [5, 4, 3, 2, 1, 0])
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_is_the_trailing_run_of_basing_candles():
    """The base starts after the last trending candle and ends at pos-1."""
    #  0: seed          1: +1 (no grandparent)   2: +1 -> CONTINUES (last trending candle)
    #  3: -1 basing     4: +1 basing             5: -1 basing        6: the candle being tested
    bars = _hl([10, 11, 12, 11.5, 11.8, 11.6, 20], [0, 1, 2, 1.5, 1.8, 1.6, 0])
    base = find_base(bars, 0, Direction.BULLISH)
    assert base == BaseSpan(3, 5)


def test_find_base_span_always_ends_at_the_candle_before_the_one_tested():
    """§2.2.8, structurally: the boundary drawn from this span cannot have seen bar `pos`."""
    bars = _hl([10, 11, 12, 11.5, 11.8, 11.6, 20], [0, 1, 2, 1.5, 1.8, 1.6, 0])
    base = find_base(bars, 0, Direction.BULLISH)
    assert base is not None
    assert base.end == len(bars) - 2


def test_find_base_keeps_a_sweep_that_reverses_inside_the_base():
    """The human's rule: a candle may 'sweep a high or a low and then reverse' and still be
    basing. An outside bar extends neither way, so it is a basing candle -- which is why the
    containment reading D-34 names was rejected."""
    #  3: +1 CONTINUES   4: outside (sweeps both sides of 3) -> basing   5: +1 basing
    bars = _hl([10, 11, 12, 13, 14, 15, 20], [0, 1, 2, 3, 1, 4, 0])
    assert bool(bars["is_inside"].iat[4]) is False
    base = find_base(bars, 0, Direction.BULLISH)
    assert base == BaseSpan(4, 5)


def test_find_base_skips_inside_candles_so_the_leg_can_continue_through_them():
    """'There could be inside bars and then it continues.' A run of inside candles mid-leg is
    skipped, not read as a pause, so it cannot open a base."""
    #  3, 4: inside (contained by 2)    5: +1 against parent 2 -> CONTINUES
    bars = _hl([10, 11, 12, 11.5, 11.8, 13, 20], [0, 1, 2, 2.5, 2.2, 3, 0])
    assert list(bars["is_inside"]) == [False, False, False, True, True, False, False]
    assert bars["parent_pos"].iat[5] == 2  # the inside run shares one parent
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_needs_two_candles():
    """The human's floor, and the minimum for a range to exist at all."""
    #  4 CONTINUES, so the trailing basing run is bar 5 alone
    bars = _hl([10, 11, 12, 13, 14, 13.5, 20], [0, 1, 2, 3, 4, 3.5, 0])
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_never_includes_the_step_1_candle():
    """Convention 4: §2.2 puts the return after Step 1, and including it would let Step 1's own
    close set the boundary under D-30."""
    # every candle alternates, so nothing is trending and only `earliest` bounds the span
    bars = _hl([10, 9, 10.5, 9.5, 10.8, 9.8, 20], [0, -1, 0.5, -0.5, 0.8, -0.2, 0])
    assert find_base(bars, 0, Direction.BULLISH) == BaseSpan(1, 5)
    assert find_base(bars, 2, Direction.BULLISH) == BaseSpan(3, 5)


def test_find_base_treats_an_unclassifiable_candle_as_basing():
    """Convention 3: bar 1 has no grandparent, so it cannot be a continuation. Were the opposite
    convention taken, the trailing run would be one candle and this would return None."""
    bars = _hl([10, 11, 10.5, 20], [0, 1, 0.5, 0])
    assert bars["parent_pos"].iat[1] == 0
    assert bars["parent_pos"].iat[0] == -1
    assert find_base(bars, 0, Direction.BULLISH) == BaseSpan(1, 2)


def test_find_base_ignores_direction():
    """D-34 is symmetric -- a trend either way stops the basing -- so the answer cannot depend on
    the sequence direction. The parameter is kept for the Judgment protocol only."""
    bars = _hl([10, 11, 12, 11.5, 11.8, 11.6, 20], [0, 1, 2, 1.5, 1.8, 1.6, 0])
    assert find_base(bars, 0, Direction.BULLISH) == find_base(bars, 0, Direction.BEARISH)


def test_find_base_requires_the_structure_columns():
    """Same contract as the D-29 predicates: raise rather than guess."""
    raw = pd.DataFrame(
        {"high": [10.0, 11.0, 12.0], "low": [0.0, 1.0, 2.0], "close": [5.0, 6.0, 7.0]},
        index=pd.date_range("2026-01-05", periods=3, freq="5min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="attach_parent_pos"):
        find_base(raw, 0, Direction.BULLISH)


def test_find_base_returns_none_on_a_frame_too_short_to_hold_one():
    """No span, rather than a degenerate one."""
    bars = _hl([10, 11], [0, 1])
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_floor_counts_non_inside_candles_only():
    """A run of inside candles is not a base on its own. They are contained by a parent that is
    itself part of the trend, so counting them would make every inside-candle pause mid-leg a
    Step 2 -- the 'there could be inside bars and then it continues' case. §5.3.5a / D-23's
    precedent: an inside candle is skipped, not counted."""
    #  2 is the last trending candle; 3 and 4 are both inside it, and nothing else follows
    bars = _hl([10, 11, 12, 11.5, 11.8, 13], [0, 1, 2, 2.5, 2.2, 3])
    assert list(bars["is_inside"]) == [False, False, False, True, True, False]
    assert find_base(bars, 0, Direction.BULLISH) is None


def test_find_base_counts_a_span_holding_two_non_inside_candles():
    """The discriminator for the test above. Same last-trending candle and the same inside candle
    after it, but two non-inside basing candles follow -- so the floor is met and the inside
    candle rides along inside the span rather than being what the span is made of."""
    #  2 CONTINUES (last trending)   3 inside 2   4: -1 basing   5: +1 basing   6: tested
    bars = _hl([10, 11, 12, 11.5, 11.9, 12.1, 20], [0, 1, 2, 2.5, 1.5, 1.6, 0])
    assert list(bars["is_inside"]) == [False, False, False, True, False, False, False]
    base = find_base(bars, 0, Direction.BULLISH)
    assert base == BaseSpan(3, 5)
    assert int((~bars["is_inside"].iloc[3:6]).sum()) == MIN_BASE_CANDLES


def test_min_base_candles_is_the_recorded_decision():
    """D-34's floor. If this changes, the §11 row and docs/STATE.md change with it."""
    assert MIN_BASE_CANDLES == 2
