"""Unit tests for stoic.gating (L4) -- hand-built fixtures only, no disk or network access.

Only the two MA gates: the 50 SMA direction gate (§7.1.2, D-19) and the 200 SMA rule (§7.1.4),
symmetric since decision D-31. Every gate here gets a negative control per `coding_rules.md`:
inject the fault it exists to catch and confirm it fails.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stoic.gating import GateDecision, GateReason, gate, gate_frame
from stoic.structure import Direction


def _bars(
    closes: list[float],
    sma_50: list[float] | None = None,
    sma_200: list[float] | None = None,
    *,
    omit_sma_50: bool = False,
    omit_sma_200: bool = False,
) -> pd.DataFrame:
    n = len(closes)
    index = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    index.name = "ts_event"
    data: dict[str, list[float]] = {"close": closes}
    if not omit_sma_50:
        data["sma_50"] = sma_50 if sma_50 is not None else [np.nan] * n
    if not omit_sma_200:
        data["sma_200"] = sma_200 if sma_200 is not None else [np.nan] * n
    return pd.DataFrame(data, index=index)


# ---------------------------------------------------------------------------
# Gate 1 -- the 50 SMA direction gate (§7.1.2, D-19)
# ---------------------------------------------------------------------------


def test_close_above_50_bullish_passes_bearish_blocked():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    bull = gate(bars, 0, Direction.BULLISH, fast_chart=False)
    bear = gate(bars, 0, Direction.BEARISH, fast_chart=False)
    assert bull.passed is True
    assert bear.passed is False
    assert bear.blocked_by == (GateReason.TREND_50,)


def test_close_below_50_mirrors():
    bars = _bars(closes=[90.0], sma_50=[100.0])
    bull = gate(bars, 0, Direction.BULLISH, fast_chart=False)
    bear = gate(bars, 0, Direction.BEARISH, fast_chart=False)
    assert bull.passed is False
    assert bull.blocked_by == (GateReason.TREND_50,)
    assert bear.passed is True


def test_close_exactly_at_50_blocks_both_directions():
    """Convention 1: a tie is neither "staying above" nor "staying below"."""
    bars = _bars(closes=[100.0], sma_50=[100.0])
    bull = gate(bars, 0, Direction.BULLISH, fast_chart=False)
    bear = gate(bars, 0, Direction.BEARISH, fast_chart=False)
    assert bull.blocked_by == (GateReason.TREND_50,)
    assert bear.blocked_by == (GateReason.TREND_50,)


def test_nan_sma_50_blocks_both_directions():
    """Convention 3: warm-up has no yardstick, so no candidate can be shown to pass."""
    bars = _bars(closes=[110.0], sma_50=[np.nan])
    bull = gate(bars, 0, Direction.BULLISH, fast_chart=False)
    bear = gate(bars, 0, Direction.BEARISH, fast_chart=False)
    assert bull.blocked_by == (GateReason.TREND_50,)
    assert bear.blocked_by == (GateReason.TREND_50,)


def test_trend_50_negative_control():
    """Build a fixture where every bullish candidate passes gate 1; assert that. Then inject the
    fault -- raise the 50 above every close -- and confirm every bullish candidate is now blocked.
    A check never observed failing is not evidence of anything."""
    closes = [110.0, 120.0, 130.0]
    passing = _bars(closes=closes, sma_50=[100.0, 100.0, 100.0])
    for pos in range(len(closes)):
        assert gate(passing, pos, Direction.BULLISH, fast_chart=False).passed is True

    faulted = _bars(closes=closes, sma_50=[200.0, 200.0, 200.0])
    for pos in range(len(closes)):
        decision = gate(faulted, pos, Direction.BULLISH, fast_chart=False)
        assert decision.passed is False
        assert GateReason.TREND_50 in decision.blocked_by


# ---------------------------------------------------------------------------
# Gate 2 -- the 200 SMA rule, symmetric since D-31 (§7.1.4)
# ---------------------------------------------------------------------------


def test_200_sma_blocks_bullish_below_on_fast_chart():
    bars = _bars(closes=[90.0], sma_50=[80.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    assert decision.blocked_by == (GateReason.INTO_200,)


def test_200_sma_does_not_block_bullish_above_on_fast_chart():
    bars = _bars(closes=[110.0], sma_50=[80.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    assert GateReason.INTO_200 not in decision.blocked_by


def test_200_sma_exact_tie_blocks_bullish_on_fast_chart():
    """Convention 2: at the 200 is still longing into it -- `<=`, not `<`."""
    bars = _bars(closes=[100.0], sma_50=[80.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    assert decision.blocked_by == (GateReason.INTO_200,)


def test_nan_sma_200_blocks_both_directions_on_fast_chart():
    """Convention 3, since D-31: NaN blocks both directions, not bullish only."""
    bars = _bars(closes=[110.0], sma_50=[80.0], sma_200=[np.nan])
    bull = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    bear = gate(bars, 0, Direction.BEARISH, fast_chart=True)
    assert GateReason.INTO_200 in bull.blocked_by
    assert GateReason.INTO_200 in bear.blocked_by


@pytest.mark.parametrize(
    ("close", "sma_200", "expect_blocked"),
    [
        (90.0, 100.0, False),  # below -- passes
        (100.0, 100.0, True),  # at -- blocks (convention 2, mirrored)
        (110.0, 100.0, True),  # above -- blocks
        (110.0, np.nan, True),  # NaN -- blocks (convention 3)
    ],
)
def test_200_sma_rule_mirrors_for_shorts(close: float, sma_200: float, expect_blocked: bool):
    """D-31: "just like we look for longs above 50/200sma, we look for shorts below it" -- a
    bearish candidate is blocked at or above the 200 and passes below it, across the same
    {below, at, above, NaN} cases the old long-only test covered."""
    bars = _bars(closes=[close], sma_50=[close], sma_200=[sma_200])
    decision = gate(bars, 0, Direction.BEARISH, fast_chart=True)
    assert (GateReason.INTO_200 in decision.blocked_by) is expect_blocked


def test_fast_chart_false_never_emits_into_200():
    bars = _bars(
        closes=[90.0, 100.0, 110.0],
        sma_50=[80.0, 80.0, 80.0],
        sma_200=[100.0, 100.0, 100.0],
    )
    for pos in range(3):
        for direction in (Direction.BULLISH, Direction.BEARISH):
            decision = gate(bars, pos, direction, fast_chart=False)
            assert GateReason.INTO_200 not in decision.blocked_by


def test_200_sma_negative_control():
    """Same discipline as the 50's negative control: a passing baseline, then the injected fault --
    for both directions, since D-31 makes the gate symmetric. A check never observed failing is
    not evidence of anything."""
    closes = [110.0, 120.0, 130.0]
    passing_bull = _bars(closes=closes, sma_50=[80.0] * 3, sma_200=[100.0] * 3)
    for pos in range(len(closes)):
        decision = gate(passing_bull, pos, Direction.BULLISH, fast_chart=True)
        assert GateReason.INTO_200 not in decision.blocked_by

    faulted_bull = _bars(closes=closes, sma_50=[80.0] * 3, sma_200=[200.0] * 3)
    for pos in range(len(closes)):
        decision = gate(faulted_bull, pos, Direction.BULLISH, fast_chart=True)
        assert decision.blocked_by == (GateReason.INTO_200,)

    # Mirror: a bearish baseline below the 200 passes; inverting the 200 below every close
    # blocks all of them.
    bear_closes = [90.0, 80.0, 70.0]
    passing_bear = _bars(closes=bear_closes, sma_50=[200.0] * 3, sma_200=[100.0] * 3)
    for pos in range(len(bear_closes)):
        decision = gate(passing_bear, pos, Direction.BEARISH, fast_chart=True)
        assert GateReason.INTO_200 not in decision.blocked_by

    faulted_bear = _bars(closes=bear_closes, sma_50=[200.0] * 3, sma_200=[50.0] * 3)
    for pos in range(len(bear_closes)):
        decision = gate(faulted_bear, pos, Direction.BEARISH, fast_chart=True)
        assert decision.blocked_by == (GateReason.INTO_200,)


def test_bearish_below_50_and_below_200_passes_both_gates_on_fast_chart():
    """New since D-31: the 200 now bites on shorts too, so a bearish candidate below both MAs
    must still pass cleanly."""
    bars = _bars(closes=[70.0], sma_50=[80.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BEARISH, fast_chart=True)
    assert decision.passed is True
    assert decision.blocked_by == ()


def test_bearish_below_50_but_above_200_blocked_by_into_200_alone():
    """New since D-31: below the 50 passes gate 1, but at/above the 200 still blocks gate 2."""
    bars = _bars(closes=[110.0], sma_50=[120.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BEARISH, fast_chart=True)
    assert decision.blocked_by == (GateReason.INTO_200,)


# ---------------------------------------------------------------------------
# Both gates together
# ---------------------------------------------------------------------------


def test_bar_that_trips_both_gates_names_both_in_declaration_order():
    bars = _bars(closes=[90.0], sma_50=[100.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    assert decision.blocked_by == (GateReason.TREND_50, GateReason.INTO_200)


@pytest.mark.parametrize(
    ("close", "sma_50", "sma_200", "fast_chart"),
    [
        (110.0, 100.0, 100.0, True),
        (90.0, 100.0, 100.0, True),
        (100.0, 100.0, 100.0, True),
        (110.0, 100.0, np.nan, True),
        (110.0, 100.0, 100.0, False),
    ],
)
def test_passed_iff_blocked_by_is_empty(
    close: float, sma_50: float, sma_200: float, fast_chart: bool
):
    bars = _bars(closes=[close], sma_50=[sma_50], sma_200=[sma_200])
    for direction in (Direction.BULLISH, Direction.BEARISH):
        decision = gate(bars, 0, direction, fast_chart=fast_chart)
        assert decision.passed == (decision.blocked_by == ())


# ---------------------------------------------------------------------------
# Wiring -- missing columns
# ---------------------------------------------------------------------------


def test_missing_sma_50_raises():
    bars = _bars(closes=[110.0], sma_200=[100.0], omit_sma_50=True)
    with pytest.raises(ValueError, match="sma_50"):
        gate(bars, 0, Direction.BULLISH, fast_chart=False)


def test_missing_sma_200_raises_only_when_fast_chart_true():
    bars = _bars(closes=[110.0], sma_50=[100.0], omit_sma_200=True)
    with pytest.raises(ValueError, match="sma_200"):
        gate(bars, 0, Direction.BULLISH, fast_chart=True)
    # does not raise when fast_chart is False
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=False)
    assert decision is not None


# ---------------------------------------------------------------------------
# gate_frame agrees with gate, bar for bar
# ---------------------------------------------------------------------------


def test_gate_frame_agrees_with_gate_bar_for_bar():
    bars = _bars(
        closes=[np.nan, 90.0, 100.0, 100.0, 110.0, 110.0],
        sma_50=[100.0, 100.0, 100.0, 100.0, 100.0, np.nan],
        sma_200=[100.0, 100.0, 100.0, np.nan, 100.0, 100.0],
    )
    for direction in (Direction.BULLISH, Direction.BEARISH):
        for fast_chart in (True, False):
            frame = gate_frame(bars, direction, fast_chart=fast_chart)
            assert list(frame.index) == list(bars.index)
            for pos in range(len(bars)):
                decision = gate(bars, pos, direction, fast_chart=fast_chart)
                assert frame["passed"].iat[pos] == decision.passed
                assert frame["blocked_by"].iat[pos] == decision.blocked_by


def test_gate_decision_fields_are_positional_and_typed():
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[100.0])
    decision = gate(bars, 0, Direction.BULLISH, fast_chart=True)
    assert isinstance(decision, GateDecision)
    assert decision.pos == 0
    assert decision.direction is Direction.BULLISH
