"""Unit tests for stoic.sequence -- hand-built fixtures only, no disk or network access.

The four injected predicates are stubbed locally, never imported from `stoic/`. `Recorder` wraps a
plain function and records every call's args, so tests can assert both the return value used and
whether (and with what `view`) a predicate was actually called.
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from stoic.sequence import (
    BaseSpan,
    Event,
    HorizontalBoundary,
    Judgment,
    SequenceMachine,
    Stage,
    replay,
)
from stoic.structure import Direction


def _bars(rows: list[dict[str, float]]) -> pd.DataFrame:
    """rows: dicts with high/low/close/sma_10/sma_20 (open defaults to close)."""
    index = pd.date_range("2026-01-05", periods=len(rows), freq="5min", tz="UTC")
    index.name = "ts_event"
    return pd.DataFrame(
        {
            "open": [r.get("open", r["close"]) for r in rows],
            "high": [r["high"] for r in rows],
            "low": [r["low"] for r in rows],
            "close": [r["close"] for r in rows],
            "sma_10": [r["sma_10"] for r in rows],
            "sma_20": [r["sma_20"] for r in rows],
        },
        index=index,
    )


class Recorder:
    """Wraps a stub function, recording every call's positional args."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.fn(*args)


def _never_true(*_args) -> bool:
    return False


def _never_base(*_args):
    return None


def _never_boundary(*_args):
    return None


def _judgment(
    is_meaningful_break=_never_true,
    find_base=_never_base,
    select_boundary=_never_boundary,
    is_meaningful_close=_never_true,
) -> Judgment:
    """Build a Judgment with Recorder-wrapped stubs; unset predicates say no / find nothing."""
    return Judgment(
        is_meaningful_break=Recorder(is_meaningful_break),
        find_base=Recorder(find_base),
        select_boundary=Recorder(select_boundary),
        is_meaningful_close=Recorder(is_meaningful_close),
    )


def _run(bars: pd.DataFrame, direction: Direction, judgment: Judgment) -> list:
    machine = SequenceMachine(direction, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    return events


# ---------------------------------------------------------------------------
# Step 1 (§2.1)
# ---------------------------------------------------------------------------


def test_step1_wick_only_does_not_fire_and_predicate_not_called():
    bars = _bars(
        [
            {"high": 95, "low": 90, "close": 92, "sma_10": 100, "sma_20": 100},
            # wick beyond both MAs, closes back inside -- not Step 1 (§2.1.2, §2.1.3)
            {"high": 105, "low": 94, "close": 98, "sma_10": 100, "sma_20": 100},
        ]
    )
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    events = _run(bars, Direction.BULLISH, judgment)

    assert not any(e.event == Event.STEP_1 for e in events)
    assert judgment.is_meaningful_break.calls == []


def test_step1_meaningful_close_beyond_both_mas_fires_and_calls_predicate():
    bars = _bars([{"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100}])
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    events = _run(bars, Direction.BULLISH, judgment)

    assert [e.event for e in events] == [Event.STEP_1]
    assert events[0].direction == Direction.BULLISH
    assert len(judgment.is_meaningful_break.calls) == 1


def test_step1_not_meaningful_does_not_fire_though_predicate_is_asked():
    bars = _bars([{"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100}])
    judgment = _judgment(is_meaningful_break=lambda *_: False)
    events = _run(bars, Direction.BULLISH, judgment)

    assert events == []
    assert len(judgment.is_meaningful_break.calls) == 1


def test_step1_direction_bearish():
    bars = _bars([{"high": 99, "low": 94, "close": 95, "sma_10": 100, "sma_20": 100}])
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    events = _run(bars, Direction.BEARISH, judgment)

    assert [e.event for e in events] == [Event.STEP_1]
    assert events[0].direction == Direction.BEARISH


# ---------------------------------------------------------------------------
# Step 3 break (§2.3.1, §2.3.2) and Confirmed Step 3 (§2.3.4, §2.3.7)
# ---------------------------------------------------------------------------


def _bullish_base_selected_judgment(
    base: BaseSpan, boundary: HorizontalBoundary, *, meaningful_close
):
    """A Judgment that fires Step 1 immediately, then selects `base`/`boundary` on the very next
    call to find_base/select_boundary (i.e. as soon as they're asked)."""
    return _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda *_: base,
        select_boundary=lambda *_: boundary,
        is_meaningful_close=meaningful_close,
    )


def test_step3_break_on_trade_through():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: False)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            {"high": 112, "low": 105, "close": 109, "sma_10": 100, "sma_20": 100},  # trade-through
        ]
    )
    events = _run(bars, Direction.BULLISH, judgment)
    breaks = [e for e in events if e.event == Event.STEP_3_BREAK]
    assert len(breaks) == 1
    assert breaks[0].pos == 2
    assert breaks[0].boundary_level == 110.0


def test_step3_break_on_gap_bar():
    """A bar opening beyond the boundary, never trading below it, still breaks (§2.3.2)."""
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: False)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            # gap: opens and stays above the boundary the whole bar
            {"open": 115, "high": 117, "low": 114, "close": 116, "sma_10": 100, "sma_20": 100},
        ]
    )
    events = _run(bars, Direction.BULLISH, judgment)
    breaks = [e for e in events if e.event == Event.STEP_3_BREAK]
    assert len(breaks) == 1
    assert breaks[0].pos == 2


def test_confirmed_step3_requires_close_beyond_boundary():
    """A break that closes back inside does not confirm, and is_meaningful_close is not asked."""
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            # trades through 110 but closes back inside -- break, no confirm (§2.3.7)
            {"high": 112, "low": 105, "close": 108, "sma_10": 100, "sma_20": 100},
        ]
    )
    events = _run(bars, Direction.BULLISH, judgment)
    assert any(e.event == Event.STEP_3_BREAK for e in events)
    assert not any(e.event == Event.STEP_3_CONFIRMED for e in events)
    assert judgment.is_meaningful_close.calls == []


def test_confirmed_step3_fires_on_meaningful_close_beyond():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},  # break+confirm
        ]
    )
    events = _run(bars, Direction.BULLISH, judgment)
    confirmed = [e for e in events if e.event == Event.STEP_3_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].pos == 2
    assert len(judgment.is_meaningful_close.calls) == 1


# ---------------------------------------------------------------------------
# Reset (§2.4.3, D-15) -- bare, no strength qualifier, unlike §5.4.7b
# ---------------------------------------------------------------------------


def test_reset_fires_on_bare_close_beyond_both_mas_even_when_5_4_7b_would_not():
    """A close that fails 5.4.7b's 10% threshold still resets the bare count (O-15)."""
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    # high-low = 100, so 10% of range = 10. Close sits 1 below sma_floor (100 - 99 = 1 < 10):
    # 5.4.7b's strength test would NOT fire on this bar, but the bare reset test has no threshold.
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 149, "low": 49, "close": 99, "sma_10": 100, "sma_20": 100},  # bare reset only
        ]
    )
    events = _run(bars, Direction.BULLISH, judgment)
    assert [e.event for e in events] == [Event.STEP_1, Event.RESET]

    machine = SequenceMachine(Direction.BULLISH, judgment)
    machine.step(bars, 0)
    machine.step(bars, 1)
    assert machine.state.stage == Stage.WAITING_STEP1


def test_no_reset_while_waiting_for_step1():
    judgment = _judgment()
    bars = _bars([{"high": 95, "low": 90, "close": 92, "sma_10": 100, "sma_20": 100}])
    events = _run(bars, Direction.BULLISH, judgment)
    assert events == []


# ---------------------------------------------------------------------------
# Directional state (§2.5, D-21) and Step 3 High/Low (§3.4-3.7, D-16, D-21)
# ---------------------------------------------------------------------------


def test_directional_state_opens_at_confirmed_and_survives_until_reset():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},  # confirm
            {"high": 120, "low": 112, "close": 118, "sma_10": 100, "sma_20": 100},  # still running
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars)):
        machine.step(bars, pos)
        if pos >= 2:
            assert machine.state.stage == Stage.CONFIRMED
    assert machine.state.stage == Stage.CONFIRMED


def test_step3_high_running_max_advances_through_continuation():
    """One series per state, not one per entry (§3.7, D-21): it just keeps advancing."""
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},  # confirm hi=112
            {"high": 108, "low": 107, "close": 107, "sma_10": 100, "sma_20": 100},  # pullback
            {"high": 125, "low": 110, "close": 124, "sma_10": 100, "sma_20": 100},  # new hi=125
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    extremes = []
    for pos in range(len(bars)):
        machine.step(bars, pos)
        extremes.append(machine.state.step3_extreme)

    assert extremes[2] == 112.0  # initial value at the confirming bar
    assert extremes[3] == 112.0  # pullback bar's high (108) does not raise it
    assert extremes[4] == 125.0  # advances through the "continuation" leg -- same series


# ---------------------------------------------------------------------------
# Step 2 swing (D-20, §6.3a-c) -- the fib anchor
# ---------------------------------------------------------------------------


def test_step2_swing_is_lowest_low_between_step1_and_base_end_bullish():
    """A fixture where the lowest low sits OUTSIDE [step1_pos, base.end] proves the span is
    respected: bar 0 (before Step 1) has a lower low than anything inside the span, and must be
    ignored."""
    base = BaseSpan(start=2, end=3)
    boundary = HorizontalBoundary(price=999.0)  # never breaks in this test
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda view, *_: base if len(view) > base.end else None,
        select_boundary=lambda *_: boundary,
    )
    bars = _bars(
        [
            {"high": 90, "low": 10, "close": 88, "sma_10": 200, "sma_20": 200},  # outside; low=10
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1, pos=1
            # MAs held low here so the pullback close doesn't trip the bare reset (close would
            # need to close below BOTH to reset; kept above both throughout Step 2).
            {"high": 100, "low": 95, "close": 98, "sma_10": 90, "sma_20": 90},  # span low, low=95
            {"high": 102, "low": 97, "close": 99, "sma_10": 90, "sma_20": 90},  # base end, low=97
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events: list = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))

    selected = [e for e in events if e.event == Event.BASE_SELECTED]
    assert len(selected) == 1
    assert selected[0].step2_swing_pos == 2
    assert selected[0].step2_swing_price == 95.0


def test_step2_swing_is_highest_high_between_step1_and_base_end_bearish():
    base = BaseSpan(start=2, end=3)
    boundary = HorizontalBoundary(price=1.0)
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda view, *_: base if len(view) > base.end else None,
        select_boundary=lambda *_: boundary,
    )
    bars = _bars(
        [
            {"high": 300, "low": 250, "close": 260, "sma_10": 100, "sma_20": 100},  # outside span
            {"high": 99, "low": 94, "close": 95, "sma_10": 100, "sma_20": 100},  # Step 1, pos=1
            # MAs held high here so the bounce close doesn't trip the bare reset (close would need
            # to close above BOTH to reset; kept below both throughout Step 2).
            {"high": 105, "low": 100, "close": 102, "sma_10": 110, "sma_20": 110},  # span high=105
            {"high": 103, "low": 98, "close": 101, "sma_10": 110, "sma_20": 110},  # base end
        ]
    )
    machine = SequenceMachine(Direction.BEARISH, judgment)
    events: list = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))

    selected = [e for e in events if e.event == Event.BASE_SELECTED]
    assert len(selected) == 1
    assert selected[0].step2_swing_pos == 2
    assert selected[0].step2_swing_price == 105.0


# ---------------------------------------------------------------------------
# §2.2.8 no-hindsight control (load-bearing)
# ---------------------------------------------------------------------------


def test_find_base_and_select_boundary_never_see_beyond_pos():
    seen_lengths: list[int] = []

    def find_base(view, step1_pos, direction):
        seen_lengths.append(len(view))
        return None

    def select_boundary(view, base, direction):
        seen_lengths.append(len(view))
        return None

    judgment = _judgment(
        is_meaningful_break=lambda *_: True, find_base=find_base, select_boundary=select_boundary
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 107, "low": 103, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 108, "low": 103, "close": 106, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars)):
        machine.step(bars, pos)
        assert all(n <= pos + 1 for n in seen_lengths)


def test_negative_control_boundary_selection_is_blind_to_the_future():
    """F3: the selector must depend on its *window*, not a fixed position within it, or a control
    that mutates only strictly-after-the-base bars is tautological (both frames would agree at
    that fixed position regardless of truncation). This selector reads `view["high"].max()` --
    genuinely sensitive to what the window contains -- so it doubles as the honest case and, if
    `select_boundary`'s view were ever widened past `base.end + 1` (F2), the fault: bars_a and
    bars_b differ only at bar 2, strictly after the base (base.end == 1), with high 500 vs 999.
    A selector that could see bar 2 would answer 500.0 vs 999.0; the real (correctly truncated)
    selector cannot see it and answers 110.0 in both cases."""
    base = BaseSpan(start=1, end=1)

    def find_base(view, step1_pos, direction):
        return base if len(view) >= 2 else None

    def window_dependent_select_boundary(view, base_span, direction):
        return HorizontalBoundary(price=float(view["high"].max()))

    bars_a = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 110, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base end
            {"high": 500, "low": 103, "close": 106, "sma_10": 100, "sma_20": 100},  # future, var A
        ]
    )
    bars_b = bars_a.copy()
    bars_b.iloc[2, bars_b.columns.get_loc("high")] = 999.0  # mutate strictly after the base end

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=window_dependent_select_boundary,
    )

    events_a = []
    machine_a = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars_a)):
        events_a.extend(machine_a.step(bars_a, pos))

    events_b = []
    machine_b = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars_b)):
        events_b.extend(machine_b.step(bars_b, pos))

    selected_a = next(e for e in events_a if e.event == Event.BASE_SELECTED)
    selected_b = next(e for e in events_b if e.event == Event.BASE_SELECTED)
    assert selected_a.boundary_level == selected_b.boundary_level == 110.0


# ---------------------------------------------------------------------------
# Invalidations (§5.4.7)
# ---------------------------------------------------------------------------


def _confirmed_bullish_machine(boundary_price: float = 110.0):
    boundary = HorizontalBoundary(price=boundary_price)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars)):
        machine.step(bars, pos)
    assert machine.state.stage == Stage.CONFIRMED
    return machine, boundary


def _confirmed_bearish_machine(boundary_price: float = 90.0):
    boundary = HorizontalBoundary(price=boundary_price)
    base = BaseSpan(start=1, end=1)
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda *_: base,
        select_boundary=lambda *_: boundary,
        is_meaningful_close=lambda *_: True,
    )
    bars = _bars(
        [
            {"high": 99, "low": 94, "close": 95, "sma_10": 100, "sma_20": 100},
            {"high": 97, "low": 94, "close": 96, "sma_10": 100, "sma_20": 100},
            {"high": 95, "low": 88, "close": 89, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BEARISH, judgment)
    for pos in range(len(bars)):
        machine.step(bars, pos)
    assert machine.state.stage == Stage.CONFIRMED
    return machine, boundary


def test_nothing_invalidates_before_state_opens():
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    bars = _bars([{"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100}])
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events = machine.step(bars, 0)
    assert not any(e.event.startswith("invalidated") for e in events)


def test_invalidation_a_confirmed_opposite_step3():
    machine, _ = _confirmed_bullish_machine()
    bars = _bars([{"high": 105, "low": 100, "close": 102, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0, opposite_confirmed_this_bar=True)
    assert any(e.event == Event.INVALIDATED_OPPOSITE_STEP_3 for e in events)


def test_invalidation_b_strong_close_beyond_ma_10_percent_discriminates():
    # range = 100, 10% = 10. sma floor = 100.
    machine_low, _ = _confirmed_bullish_machine()
    bars_9pct = _bars([{"high": 150, "low": 50, "close": 91.0, "sma_10": 100, "sma_20": 100}])
    events_9 = machine_low.step(bars_9pct, 0)
    assert not any(e.event == Event.INVALIDATED_MA_CLOSE for e in events_9)

    machine_high, _ = _confirmed_bullish_machine()
    bars_11pct = _bars([{"high": 150, "low": 50, "close": 89.0, "sma_10": 100, "sma_20": 100}])
    events_11 = machine_high.step(bars_11pct, 0)
    assert any(e.event == Event.INVALIDATED_MA_CLOSE for e in events_11)


def test_invalidation_b_zero_range_bar_any_close_beyond_invalidates():
    """A high == low bar makes the 10% threshold 0; a close beyond the MA by any amount then
    satisfies >= 0. Pinned as written, not special-cased."""
    machine, _ = _confirmed_bullish_machine()
    bars = _bars([{"high": 99.999, "low": 99.999, "close": 99.999, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0)
    assert any(e.event == Event.INVALIDATED_MA_CLOSE for e in events)


def test_invalidation_c_is_close_only_wick_through_does_not_invalidate():
    machine, _boundary = _confirmed_bullish_machine(boundary_price=110.0)
    # wick trades through the boundary but closes back above it
    bars = _bars([{"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0)
    assert not any(e.event == Event.INVALIDATED_BOUNDARY_CLOSE for e in events)


def test_invalidation_c_fires_on_close_beyond_boundary():
    machine, _boundary = _confirmed_bullish_machine(boundary_price=110.0)
    bars = _bars([{"high": 112, "low": 105, "close": 108, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0)
    assert any(e.event == Event.INVALIDATED_BOUNDARY_CLOSE for e in events)


def test_negative_control_trade_through_variant_does_not_match_close_based_c():
    """Implement a trade-through reading of 5.4.7c inline and show it WOULD fire on a wick-only
    fixture, while the real (close-based) implementation does not -- proving the fixture
    discriminates."""
    machine, boundary = _confirmed_bullish_machine(boundary_price=110.0)
    bars = _bars([{"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100}])

    low = float(bars["low"].iat[0])
    level = boundary.level_at(0)
    trade_through_variant_fires = low < level  # the wrong reading: any wick beyond invalidates
    assert trade_through_variant_fires is True

    real_events = machine.step(bars, 0)
    assert not any(e.event == Event.INVALIDATED_BOUNDARY_CLOSE for e in real_events)


# ---------------------------------------------------------------------------
# F1 -- invalidation scope must outlive the reset
# ---------------------------------------------------------------------------


def _cross_link_fixture():
    """A bullish sequence confirms (boundary 80), the count resets, and a bearish sequence forms
    and confirms (boundary 85) several bars later. Both directions share one `Judgment`, branching
    on `direction` -- exactly the "maximally permissive Judgment" the fix list's fault injection
    used, which found 0 `invalidated_opposite_step_3` rows through the old Stage-gated model."""

    def find_base(view, step1_pos, direction):
        if direction == Direction.BULLISH:
            return BaseSpan(1, 1) if len(view) > 1 else None
        return BaseSpan(4, 4) if len(view) > 4 else None

    def select_boundary(view, base, direction):
        return HorizontalBoundary(80.0) if direction == Direction.BULLISH else HorizontalBoundary(
            85.0
        )

    judgment = Judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=select_boundary,
        is_meaningful_close=lambda *_: True,
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # 0 bull Step1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # 1 bull base
            {"high": 112, "low": 85, "close": 111, "sma_10": 100, "sma_20": 100},  # 2 bull confirm
            {"high": 150, "low": 40, "close": 95, "sma_10": 100, "sma_20": 100},  # 3 bull RESET
            #                                                                       3 bear Step1
            {"high": 150, "low": 40, "close": 93, "sma_10": 95, "sma_20": 95},  # 4 bear base
            {"high": 150, "low": 40, "close": 88, "sma_10": 95, "sma_20": 95},  # 5 bear break only
            {"high": 150, "low": 20, "close": 83, "sma_10": 95, "sma_20": 95},  # 6 bear confirm
        ]
    )
    return judgment, bars


def test_invalidated_opposite_step3_fires_through_replay_after_reset_and_many_bars():
    """The defect F1 fixes: the bullish reset predicate (close < both MAs) is character-identical
    to the bearish Step 1 predicate, so under the old Stage-gated model, bullish's Stage.CONFIRMED
    -- and with it the old invalidation check -- was wiped on the very bar the opposite Step 1
    started, many bars before the opposite Step 3 could confirm. The invalidatable sequence must
    outlive the reset. This goes through `replay`, never `step(..., opposite_confirmed_this_bar=
    True)` -- driving the flag by hand is what hid the defect originally."""
    judgment, bars = _cross_link_fixture()
    result = replay(bars, judgment)

    bullish_invalidated = result[
        (result["direction"] == Direction.BULLISH)
        & (result["event"] == Event.INVALIDATED_OPPOSITE_STEP_3)
    ]
    assert list(bullish_invalidated["pos"]) == [6]

    # Sanity: the count did reset in between, and a fresh bearish count is what confirmed.
    resets = result[(result["direction"] == Direction.BULLISH) & (result["event"] == Event.RESET)]
    assert list(resets["pos"]) == [3]
    bear_confirms = result[
        (result["direction"] == Direction.BEARISH) & (result["event"] == Event.STEP_3_CONFIRMED)
    ]
    assert list(bear_confirms["pos"]) == [6]


def test_invalidation_condition_holding_several_bars_emits_exactly_one_event():
    """A boundary-close condition holding for several consecutive bars must emit exactly one
    event (F1) -- close-on-first-fire, not a separate latch."""
    machine, _boundary = _confirmed_bullish_machine(boundary_price=110.0)
    fired = []
    for close in (105.0, 104.0, 103.0, 102.0):
        bars = _bars([{"high": 106, "low": 101, "close": close, "sma_10": 100, "sma_20": 100}])
        fired.extend(machine.step(bars, 0))
    boundary_events = [e for e in fired if e.event == Event.INVALIDATED_BOUNDARY_CLOSE]
    assert len(boundary_events) == 1
    assert machine.state.invalidatable is None


def test_invalidatable_sequence_survives_reset_and_fires_later():
    """The invalidatable sequence outlives the §2.4.3 reset; a later §5.4.7c fire still comes out
    even though `Stage` has long since gone back to `WAITING_STEP1` (F1)."""
    machine, _boundary = _confirmed_bullish_machine(boundary_price=80.0)

    reset_bars = _bars([{"high": 150, "low": 30, "close": 95, "sma_10": 100, "sma_20": 100}])
    reset_events = machine.step(reset_bars, 0)
    assert [e.event for e in reset_events] == [Event.RESET]
    assert machine.state.stage == Stage.WAITING_STEP1
    assert machine.state.invalidatable is not None

    later_bars = _bars([{"high": 100, "low": 50, "close": 75.0, "sma_10": 95, "sma_20": 95}])
    later_events = machine.step(later_bars, 0)
    assert any(e.event == Event.INVALIDATED_BOUNDARY_CLOSE for e in later_events)


def test_second_confirmed_step3_same_direction_replaces_boundary_and_rearms():
    """A later `STEP_3_CONFIRMED` in the same direction replaces the invalidatable sequence's
    boundary and re-arms it (F1)."""
    boundary_box = [HorizontalBoundary(130.0)]

    def find_base(view, step1_pos, direction):
        # Ends at pos-1, per D-34. A span ending at `pos` can never be broken -- F5 enforces
        # §2.2.5's "markable before the break" -- and since D-34 re-asks this predicate on every
        # bar, a stub that always returned `pos` would leave the count stuck at BASE_SELECTED.
        if len(view) < 2:
            return None
        return BaseSpan(len(view) - 2, len(view) - 2)

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=lambda *_: boundary_box[0],
        is_meaningful_close=lambda *_: True,
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars1 = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 135, "low": 105, "close": 132, "sma_10": 100, "sma_20": 100},
        ]
    )
    for pos in range(len(bars1)):
        machine.step(bars1, pos)
    assert machine.state.stage == Stage.CONFIRMED
    assert machine.state.invalidatable.boundary.level_at(0) == 130.0

    reset_bars = _bars([{"high": 150, "low": 30, "close": 90, "sma_10": 100, "sma_20": 100}])
    machine.step(reset_bars, 0)
    assert machine.state.stage == Stage.WAITING_STEP1

    boundary_box[0] = HorizontalBoundary(80.0)
    bars2 = _bars(
        [
            {"high": 65, "low": 55, "close": 60, "sma_10": 50, "sma_20": 50},
            {"high": 64, "low": 57, "close": 59, "sma_10": 50, "sma_20": 50},
            {"high": 90, "low": 82, "close": 85, "sma_10": 50, "sma_20": 50},
        ]
    )
    for pos in range(len(bars2)):
        machine.step(bars2, pos)
    assert machine.state.stage == Stage.CONFIRMED
    assert machine.state.invalidatable.boundary.level_at(0) == 80.0

    # Discriminator: a close of 100 would invalidate under the OLD (130) boundary but not under
    # the NEW (80) one -- proving the new boundary, not the old, now governs.
    check_bars = _bars([{"high": 105, "low": 95, "close": 100, "sma_10": 50, "sma_20": 50}])
    events = machine.step(check_bars, 0)
    assert not any(e.event == Event.INVALIDATED_BOUNDARY_CLOSE for e in events)


def _replay_reordered(bars, judgment, *, bear_first: bool):
    """Same two-pass logic as `replay`, but with the two machines' processing order swapped, to
    test that the order is not observable in the output (F1)."""
    bull = SequenceMachine(Direction.BULLISH, judgment)
    bear = SequenceMachine(Direction.BEARISH, judgment)
    records = []
    for pos in range(len(bars)):
        if bear_first:
            bear_count = bear.step_count(bars, pos)
            bull_count = bull.step_count(bars, pos)
        else:
            bull_count = bull.step_count(bars, pos)
            bear_count = bear.step_count(bars, pos)
        records.extend(bull_count)
        records.extend(bear_count)

        bull_confirmed = any(e.event == Event.STEP_3_CONFIRMED for e in bull_count)
        bear_confirmed = any(e.event == Event.STEP_3_CONFIRMED for e in bear_count)

        if bear_first:
            records.extend(
                bear.step_invalidations(bars, pos, opposite_confirmed_this_bar=bull_confirmed)
            )
            records.extend(
                bull.step_invalidations(bars, pos, opposite_confirmed_this_bar=bear_confirmed)
            )
        else:
            records.extend(
                bull.step_invalidations(bars, pos, opposite_confirmed_this_bar=bear_confirmed)
            )
            records.extend(
                bear.step_invalidations(bars, pos, opposite_confirmed_this_bar=bull_confirmed)
            )
    return records


def test_replay_output_independent_of_machine_processing_order():
    judgment, bars = _cross_link_fixture()
    forward = _replay_reordered(bars, judgment, bear_first=False)
    reversed_ = _replay_reordered(bars, judgment, bear_first=True)

    def key(r):
        return (r.pos, str(r.direction), str(r.event))

    assert sorted(key(r) for r in forward) == sorted(key(r) for r in reversed_)
    assert len(forward) == len(reversed_) > 0


# ---------------------------------------------------------------------------
# F5 -- same-bar cascade is wrong when base.end == pos
# ---------------------------------------------------------------------------


def test_step3_break_does_not_fire_on_the_bar_the_base_is_selected():
    """§2.2.5: the boundary must be markable BEFORE the break. A base recognised exactly on the
    bar it completes (base.end == pos) cannot also break on that same bar."""
    boundary = HorizontalBoundary(price=90.0)  # below this bar's high -- would break if allowed
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda view, *_: BaseSpan(len(view) - 1, len(view) - 1),
        select_boundary=lambda *_: boundary,
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base==pos1
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    assert [e.event for e in events] == [Event.STEP_1, Event.BASE_SELECTED]
    assert machine.state.stage == Stage.BASE_SELECTED


def test_step3_break_fires_on_recognition_bar_when_base_end_is_earlier():
    """A late-recognised base (base.end < pos on the bar it is first reported) legitimately
    breaks on that same recognition bar -- F5 does not blanket-ban same-bar breaks."""
    boundary = HorizontalBoundary(price=90.0)
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        # base completed at bar 1, but find_base only "notices" it once 3 bars are visible.
        find_base=lambda view, *_: BaseSpan(1, 1) if len(view) >= 3 else None,
        select_boundary=lambda *_: boundary,
        is_meaningful_close=lambda *_: False,
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            # recognised late, on this bar -- and this bar also trades through 90. MAs kept low
            # so the pullback close doesn't trip the bare reset (needs close below BOTH).
            {"high": 95, "low": 92, "close": 93, "sma_10": 90, "sma_20": 90},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    assert [e.event for e in events] == [Event.STEP_1, Event.BASE_SELECTED, Event.STEP_3_BREAK]
    assert events[1].pos == 2 and events[2].pos == 2  # same bar, base.end(1) < pos(2)


# ---------------------------------------------------------------------------
# F6 -- a re-break of a still-pending base emits STEP_3_BREAK again
# ---------------------------------------------------------------------------


def test_re_break_of_still_pending_base_emits_step_3_break_again():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: False)
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},  # base bar
            {"high": 112, "low": 105, "close": 108, "sma_10": 100, "sma_20": 100},  # break
            {"high": 109, "low": 106, "close": 108, "sma_10": 100, "sma_20": 100},  # no break
            {"high": 113, "low": 105, "close": 109, "sma_10": 100, "sma_20": 100},  # re-break
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    breaks = [e for e in events if e.event == Event.STEP_3_BREAK]
    assert len(breaks) == 2
    assert [b.pos for b in breaks] == [2, 4]
    assert machine.state.stage == Stage.STEP3_BROKEN


# ---------------------------------------------------------------------------
# F2 -- select_boundary's view is truncated at base.end, not pos
# ---------------------------------------------------------------------------


def test_select_boundary_view_length_is_always_base_end_plus_1():
    seen: list[int] = []

    def find_base(view, step1_pos, direction):
        # recognised late: base ends at bar 1, but is only reported once 4 bars are visible.
        return BaseSpan(1, 1) if len(view) >= 4 else None

    def select_boundary(view, base, direction):
        seen.append(len(view))
        return None  # keep re-asking (§2.2.9) so it's called on every remaining bar too

    judgment = _judgment(
        is_meaningful_break=lambda *_: True, find_base=find_base, select_boundary=select_boundary
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 107, "low": 103, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 108, "low": 103, "close": 106, "sma_10": 100, "sma_20": 100},
            {"high": 109, "low": 103, "close": 107, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    for pos in range(len(bars)):
        machine.step(bars, pos)
    # base.end == 1, so select_boundary's view must always be exactly 2 bars, on every call --
    # including the late-recognition bar (pos 3) and every re-ask after it (pos 4).
    assert seen == [2, 2]


# ---------------------------------------------------------------------------
# F4 -- Step 2 swing window validation
# ---------------------------------------------------------------------------


def test_find_base_invalid_span_raises_value_error():
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        # base.end (5) > pos (1) -- invalid, ends after the bar being evaluated (lookahead).
        find_base=lambda *_: BaseSpan(0, 5),
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    machine.step(bars, 0)
    with pytest.raises(ValueError, match="invalid span"):
        machine.step(bars, 1)


# ---------------------------------------------------------------------------
# F7 -- negative controls for five previously-unpinned clauses
# ---------------------------------------------------------------------------


def test_step1_requires_both_mas_not_either():
    """A buggy `or` in place of `and` would fire here; every other fixture in this file sets
    sma_10 == sma_20, which cannot discriminate the two."""
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    bars = _bars([{"high": 108, "low": 102, "close": 105, "sma_10": 100, "sma_20": 110}])
    events = _run(bars, Direction.BULLISH, judgment)
    assert not any(e.event == Event.STEP_1 for e in events)


def test_bearish_reset_requires_both_mas_not_either():
    """A buggy `or` in the bearish reset would fire here. There was previously no bearish reset
    test at all."""
    judgment = _judgment(is_meaningful_break=lambda *_: True)
    bars = _bars(
        [
            {"high": 99, "low": 94, "close": 95, "sma_10": 100, "sma_20": 100},  # bearish Step 1
            # close (105) > sma_10 (100) but NOT > sma_20 (110) -- correct AND does not reset.
            {"high": 108, "low": 102, "close": 105, "sma_10": 100, "sma_20": 110},
        ]
    )
    machine = SequenceMachine(Direction.BEARISH, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    assert not any(e.event == Event.RESET for e in events)
    assert machine.state.stage == Stage.AFTER_STEP1


def test_bearish_invalidation_b_uses_max_not_min_of_the_mas():
    """A buggy `min` in place of `max` for the bearish MA ceiling would invalidate here; there was
    previously no bearish invalidation test at all."""
    machine, _boundary = _confirmed_bearish_machine()
    # close (105) is between the two MAs: > min (100) but not > max (110).
    bars = _bars([{"high": 108, "low": 102, "close": 105, "sma_10": 100, "sma_20": 110}])
    events = machine.step(bars, 0)
    assert not any(e.event == Event.INVALIDATED_MA_CLOSE for e in events)


def test_reset_fires_and_clears_stage_from_confirmed():
    """No existing fixture ever reset a state that was already `Stage.CONFIRMED`, so the claim in
    `test_directional_state_opens_at_confirmed_and_survives_until_reset`'s own name was untested."""
    machine, _boundary = _confirmed_bullish_machine()
    bars = _bars([{"high": 99, "low": 96, "close": 97, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0)
    assert any(e.event == Event.RESET for e in events)
    assert machine.state.stage == Stage.WAITING_STEP1


def test_step2_swing_window_ignores_lows_after_late_recognized_base_end():
    """A buggy `[step1_pos : pos + 1]` window (instead of `[: base.end + 1]`) would pick up the
    lower low placed AFTER base.end, on the late-recognition bar itself."""
    base = BaseSpan(start=1, end=1)

    def find_base(view, step1_pos, direction):
        # recognised late: base ends at bar 1, reported once 3 bars are visible.
        return base if len(view) >= 3 else None

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=lambda *_: HorizontalBoundary(price=999.0),  # never breaks
    )
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},  # Step 1
            {"high": 106, "low": 95, "close": 104, "sma_10": 100, "sma_20": 100},  # base end low=95
            # recognition bar, AFTER base.end -- a much lower low that must be ignored.
            {"high": 105, "low": 10, "close": 103, "sma_10": 100, "sma_20": 100},
        ]
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))
    selected = next(e for e in events if e.event == Event.BASE_SELECTED)
    assert selected.step2_swing_pos == 1
    assert selected.step2_swing_price == 95.0


# ---------------------------------------------------------------------------
# F8 -- notes
# ---------------------------------------------------------------------------


def test_reset_row_carries_extreme_from_before_the_reset_bar_not_its_own_high():
    machine, _boundary = _confirmed_bullish_machine()  # confirms with high=112 at pos 2
    bars = _bars([{"high": 140, "low": 98, "close": 97, "sma_10": 100, "sma_20": 100}])
    events = machine.step(bars, 0)
    resets = [e for e in events if e.event == Event.RESET]
    assert len(resets) == 1
    assert resets[0].step3_extreme == 112.0


def test_step_raises_on_missing_smas_directly_not_only_via_replay():
    judgment = _judgment()
    bars = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
        index=pd.date_range("2026-01-05", periods=1, freq="5min", tz="UTC"),
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)
    with pytest.raises(ValueError, match="add_smas"):
        machine.step(bars, 0)


def test_replay_positional_and_index_columns_are_nullable_int64():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},
        ]
    )
    result = replay(bars, judgment)
    for col in ("pos", "base_start", "base_end", "step2_swing_pos"):
        assert str(result[col].dtype) == "Int64"


def test_replay_empty_frame_has_same_schema_as_non_empty():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)
    non_empty_bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},
        ]
    )
    non_empty = replay(non_empty_bars, judgment)

    empty_bars = _bars([{"high": 95, "low": 90, "close": 92, "sma_10": 100, "sma_20": 100}])
    empty_judgment = _judgment()
    empty = replay(empty_bars, empty_judgment)
    assert len(empty) == 0

    assert list(empty.columns) == list(non_empty.columns)
    for col in non_empty.columns:
        assert empty[col].dtype == non_empty[col].dtype


# ---------------------------------------------------------------------------
# Injection discipline
# ---------------------------------------------------------------------------


def test_judgment_missing_predicate_raises_type_error():
    with pytest.raises(TypeError):
        Judgment(
            is_meaningful_break=lambda *_: True,
            find_base=lambda *_: None,
            select_boundary=lambda *_: None,
            # is_meaningful_close omitted
        )


def test_sequence_module_ships_no_default_predicate():
    import stoic.sequence as seq_module

    members = inspect.getmembers(seq_module, inspect.isfunction)
    module_level = [name for name, fn in members if fn.__module__ == seq_module.__name__]
    assert not any(name.startswith("default_") for name in module_level)


# ---------------------------------------------------------------------------
# replay() -- ValueError on missing SMAs, and end-to-end wiring
# ---------------------------------------------------------------------------


def test_replay_raises_on_missing_smas():
    bars = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
        index=pd.date_range("2026-01-05", periods=1, freq="5min", tz="UTC"),
    )
    judgment = _judgment()
    with pytest.raises(ValueError, match="add_smas"):
        replay(bars, judgment)


def test_replay_end_to_end_emits_full_sequence():
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    judgment = _bullish_base_selected_judgment(base, boundary, meaningful_close=lambda *_: True)
    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 103, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 112, "low": 105, "close": 111, "sma_10": 100, "sma_20": 100},
        ]
    )
    result = replay(bars, judgment)
    assert list(result["event"]) == [
        Event.STEP_1,
        Event.BASE_SELECTED,
        Event.STEP_3_BREAK,
        Event.STEP_3_CONFIRMED,
    ]
    assert list(result.columns) == [
        "pos",
        "ts",
        "event",
        "direction",
        "boundary_level",
        "base_start",
        "base_end",
        "step2_swing_pos",
        "step2_swing_price",
        "step3_extreme",
    ]


# ---------------------------------------------------------------------------
# D-34: the base is a state, re-asked every bar while unbroken
# ---------------------------------------------------------------------------


def _step1_then(rows: list[dict[str, float]]) -> pd.DataFrame:
    """A bullish Step 1 on bar 0, then `rows` -- all closing above the MAs so nothing resets."""
    return _bars([{"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100}, *rows])


def _quiet(n: int) -> list[dict[str, float]]:
    return [{"high": 106, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100}] * n


def test_base_extends_every_bar_and_base_selected_is_emitted_once():
    """D-34: the span grows by a candle at a time and the line is re-read, but the event fires
    only on entry to the stage -- STEP_3_BREAK carries the level actually broken."""

    def find_base(view, step1_pos, direction):
        return BaseSpan(1, len(view) - 2) if len(view) >= 4 else None

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        # a level no bar reaches, so the base is never broken and never freezes
        select_boundary=lambda _bars, base, _dir: HorizontalBoundary(1000.0 + base.end),
        is_meaningful_close=lambda *_: False,
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars = _step1_then(_quiet(5))
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))

    assert [e.pos for e in events if e.event == Event.BASE_SELECTED] == [3]
    assert machine.state.stage == Stage.BASE_SELECTED
    assert machine.state.base == BaseSpan(1, len(bars) - 2)
    assert machine.state.boundary.level_at(0) == 1000.0 + (len(bars) - 2)


def test_base_is_cancelled_when_the_leg_resumes():
    """D-34: `None` means the leg resumed. The base is cancelled, not frozen -- and since it
    never confirmed a Step 3, nothing is emitted."""
    live = [True]

    def find_base(view, step1_pos, direction):
        if not live[0] or len(view) < 4:
            return None
        return BaseSpan(1, len(view) - 2)

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=lambda *_: HorizontalBoundary(1000.0),
        is_meaningful_close=lambda *_: False,
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars = _step1_then(_quiet(5))
    for pos in range(4):
        machine.step(bars, pos)
    assert machine.state.stage == Stage.BASE_SELECTED

    live[0] = False
    events = machine.step(bars, 4)
    assert events == []
    assert machine.state.stage == Stage.AFTER_STEP1
    assert machine.state.base is None
    assert machine.state.boundary is None
    assert machine.state.step2_swing_pos is None


def test_a_base_that_reforms_after_cancellation_emits_again():
    """The second BASE_SELECTED is a genuinely new selection, not the first one growing."""
    live = [True]

    def find_base(view, step1_pos, direction):
        if not live[0] or len(view) < 4:
            return None
        return BaseSpan(1, len(view) - 2)

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=lambda *_: HorizontalBoundary(1000.0),
        is_meaningful_close=lambda *_: False,
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars = _step1_then(_quiet(5))
    events = []
    for pos in range(len(bars)):
        if pos == 4:
            live[0] = False
        if pos == 5:
            live[0] = True
        events.extend(machine.step(bars, pos))

    assert [e.pos for e in events if e.event == Event.BASE_SELECTED] == [3, 5]


def test_boundary_freezes_once_the_base_has_been_broken():
    """§2.3.1's "pre-selected", and F6: a re-break of a still-pending base must re-break the
    *same* line, so the base stops being re-asked once STEP3_BROKEN."""
    def _base(view, step1_pos, direction):
        return BaseSpan(1, len(view) - 2) if len(view) >= 3 else None

    recorder = Recorder(_base)
    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=recorder,
        select_boundary=lambda *_: HorizontalBoundary(110.0),
        is_meaningful_close=lambda *_: False,  # breaks but never confirms
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 120, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 121, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
        ]
    )
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))

    assert machine.state.stage == Stage.STEP3_BROKEN
    assert [e.pos for e in events if e.event == Event.STEP_3_BREAK] == [3, 4]
    calls_after_break = [c for c in recorder.calls if len(c[0]) - 1 > 3]
    assert calls_after_break == []
    assert machine.state.base == BaseSpan(1, 2)


def test_step_3_break_carries_the_span_and_swing_that_actually_drove_it():
    """BASE_SELECTED fires once, on the first bar a base exists, while the span keeps growing
    behind it (D-34). So the break must carry the live span and D-20's swing, or the only
    recorded fib anchor would be the first-bar one."""

    def find_base(view, step1_pos, direction):
        return BaseSpan(1, len(view) - 2) if len(view) >= 3 else None

    judgment = _judgment(
        is_meaningful_break=lambda *_: True,
        find_base=find_base,
        select_boundary=lambda *_: HorizontalBoundary(110.0),
        is_meaningful_close=lambda *_: False,
    )
    machine = SequenceMachine(Direction.BULLISH, judgment)

    bars = _bars(
        [
            {"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 99, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 106, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
            {"high": 120, "low": 101, "close": 104, "sma_10": 100, "sma_20": 100},
        ]
    )
    events = []
    for pos in range(len(bars)):
        events.extend(machine.step(bars, pos))

    selected = next(e for e in events if e.event == Event.BASE_SELECTED)
    broke = next(e for e in events if e.event == Event.STEP_3_BREAK)

    # the span grew between the two events, and the break carries the later one
    assert (selected.base_start, selected.base_end) == (1, 1)
    assert (broke.base_start, broke.base_end) == (1, 3)
    # the swing moved with it: bar 2's low of 99 is the lowest in [step1_pos, base_end]
    assert selected.step2_swing_pos == 0
    assert broke.step2_swing_pos == 2
    assert broke.step2_swing_price == 99.0
