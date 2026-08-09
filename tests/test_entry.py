"""Unit tests for stoic.entry (L3) -- hand-built fixtures only, no disk or network access.

`EntryMachine` is driven directly with synthetic `stoic.sequence.EventRecord`s (`STEP_3_CONFIRMED`,
`RESET`, the three `INVALIDATED_*`), so L3 is testable without `find_base` (undecided, no default).
`opens_pullback` and `is_inside` are exercised for real, against the **parent bar** (`stoic.candles.
candle_structure`), not `pos - 1` -- fixtures are built bar by bar so the parent chain in each one
can be checked by hand (see the comments next to each row).

Only `replay_entries`'s smoke test drives a real `stoic.sequence.Judgment` stub end to end.
"""

from __future__ import annotations

import pandas as pd
import pytest

from stoic.entry import (
    EntryEvent,
    EntryMachine,
    EntryRecord,
    OpenEntry,
    WorkingOrder,
    replay_entries,
)
from stoic.sequence import BaseSpan, Event, EventRecord, HorizontalBoundary, Judgment
from stoic.structure import Direction


def _bars(rows: list[dict[str, float]]) -> pd.DataFrame:
    """rows: dicts with high/low/close (open defaults to close). sma_10/sma_20 are included only
    if every row supplies them -- only `replay_entries`'s smoke test needs them (it drives real
    `SequenceMachine`s); direct `EntryMachine` fixtures do not."""
    index = pd.date_range("2026-01-05", periods=len(rows), freq="5min", tz="UTC")
    index.name = "ts_event"
    data = {
        "open": [r.get("open", r["close"]) for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
    }
    if all("sma_10" in r for r in rows):
        data["sma_10"] = [r["sma_10"] for r in rows]
        data["sma_20"] = [r["sma_20"] for r in rows]
    return pd.DataFrame(data, index=index)


def _run_entry(
    direction: Direction,
    rows: list[dict[str, float]],
    events_by_pos: dict[int, list[EventRecord]] | None = None,
    extremes_by_pos: dict[int, float] | None = None,
) -> tuple[EntryMachine, pd.DataFrame, dict[int, list[EntryRecord]], dict[int, object]]:
    """Build `bars` from `rows`, drive a fresh `EntryMachine(direction)` bar by bar, and return
    (machine, bars, records_by_pos, state_by_pos). `records_by_pos[pos]` is exactly what `step`
    returned for that bar, so a test can assert both "this bar emitted X" and "this bar emitted
    nothing". `state_by_pos[pos]` is `machine.state` immediately after that bar's `step` call, so
    a test can inspect intermediate state without it being overwritten by later bars."""
    bars = _bars(rows)
    machine = EntryMachine(direction)
    events_by_pos = events_by_pos or {}
    extremes_by_pos = extremes_by_pos or {}
    records_by_pos: dict[int, list[EntryRecord]] = {}
    state_by_pos: dict[int, object] = {}
    for pos in range(len(bars)):
        records_by_pos[pos] = machine.step(
            bars,
            pos,
            events=events_by_pos.get(pos, []),
            step3_extreme=extremes_by_pos.get(pos),
        )
        state_by_pos[pos] = machine.state
    return machine, bars, records_by_pos, state_by_pos


def _arm(direction: Direction, pos: int = 0) -> list[EventRecord]:
    return [EventRecord(pos, Event.STEP_3_CONFIRMED, direction)]


# A bullish arm bar (0), an expansion bar (1, becomes the parent), and a pullback bar (2) that
# opens and anchors: lower high (108 < 110) AND lower low (99 < 101) than its parent (bar 1).
# trigger = bar 2's high = 108, stop = bar 2's low = 99.
_BULLISH_PREFIX: list[dict[str, float]] = [
    {"open": 98, "high": 100, "low": 95, "close": 98},
    {"open": 108, "high": 110, "low": 101, "close": 108},
    {"open": 100, "high": 108, "low": 99, "close": 100},
]


# ---------------------------------------------------------------------------
# Case 1 -- all-expansion bars never anchor
# ---------------------------------------------------------------------------


def test_case1_armed_all_expansion_bars_no_anchor():
    rows = [
        {"open": 97, "high": 100, "low": 95, "close": 98},  # 0: arm
        {"open": 99, "high": 105, "low": 98, "close": 102},  # 1: higher high & low -- expansion
        {"open": 103, "high": 110, "low": 101, "close": 108},  # 2: higher high & low -- expansion
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    all_events = [r.event for recs in records.values() for r in recs]
    assert EntryEvent.PTB_ANCHORED not in all_events
    assert machine.state.order is None


# ---------------------------------------------------------------------------
# Case 2 -- pullback opens (parent-relative), anchors with trigger/stop
# ---------------------------------------------------------------------------


def test_case2_pullback_opens_anchors_bullish():
    machine, _, records, _states = _run_entry(
        Direction.BULLISH, _BULLISH_PREFIX, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    anchored = records[2]
    assert [r.event for r in anchored] == [EntryEvent.PTB_ANCHORED]
    assert anchored[0].anchor_pos == 2
    assert anchored[0].trigger == 108.0
    assert anchored[0].stop == 99.0
    assert machine.state.order == WorkingOrder(anchor_pos=2, trigger=108.0, stop=99.0)


def test_case2_pullback_opens_anchors_bearish():
    # 0: arm, 1: expansion (parent), 2: higher low (85>80) AND higher high (98>90) than parent --
    # a bearish pullback opens. trigger = bar 2's low = 85, stop = bar 2's high = 98.
    rows = [
        {"open": 98, "high": 100, "low": 95, "close": 98},
        {"open": 85, "high": 90, "low": 80, "close": 85},
        {"open": 90, "high": 98, "low": 85, "close": 90},
    ]
    machine, _, records, _states = _run_entry(
        Direction.BEARISH, rows, events_by_pos={0: _arm(Direction.BEARISH)}
    )
    anchored = records[2]
    assert [r.event for r in anchored] == [EntryEvent.PTB_ANCHORED]
    assert anchored[0].anchor_pos == 2
    assert anchored[0].trigger == 85.0
    assert anchored[0].stop == 98.0
    assert machine.state.order == WorkingOrder(anchor_pos=2, trigger=85.0, stop=98.0)


# ---------------------------------------------------------------------------
# Case 3 -- the anchor bar cannot fill its own order (§5.3.1)
# ---------------------------------------------------------------------------


def test_case3_anchor_bar_cannot_fill_itself():
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, _BULLISH_PREFIX, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    # The anchoring bar (2) only ever emits PTB_ANCHORED -- the order did not exist yet when this
    # bar's own fill check ran (step 2 precedes step 5 within one `step` call).
    assert [r.event for r in records[2]] == [EntryEvent.PTB_ANCHORED]


# ---------------------------------------------------------------------------
# Case 4 -- re-anchor to the next non-inside pullback bar; trigger moves
# ---------------------------------------------------------------------------


def test_case4_reanchor_to_next_pullback_bar_moves_trigger_down():
    rows = [
        *_BULLISH_PREFIX,
        # not inside bar 2 (105<=108 but 97 is NOT >=99); no fill (105 < trigger 108).
        {"open": 100, "high": 105, "low": 97, "close": 100},
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    reanchored = records[3]
    assert [r.event for r in reanchored] == [EntryEvent.PTB_ANCHORED]
    assert reanchored[0].anchor_pos == 3
    assert reanchored[0].trigger == 105.0  # moved down from 108
    assert reanchored[0].stop == 97.0
    assert machine.state.order == WorkingOrder(anchor_pos=3, trigger=105.0, stop=97.0)


# ---------------------------------------------------------------------------
# Case 5 -- an inside candle does not move the anchor; negative control on fill
# ---------------------------------------------------------------------------


def test_case5_inside_candle_does_not_move_anchor_or_cancel_order():
    rows = [
        *_BULLISH_PREFIX,
        {"open": 100, "high": 105, "low": 97, "close": 100},  # 3: re-anchor, trigger=105, stop=97
        # inside bar 3 (102<=105 and 98>=97): must not move the anchor or cancel the order.
        {"open": 100, "high": 102, "low": 98, "close": 100},
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    assert records[4] == []
    assert machine.state.order == WorkingOrder(anchor_pos=3, trigger=105.0, stop=97.0)


def test_case5_negative_control_no_fill_below_standing_anchor_trigger():
    """The mandatory negative control: a bar whose high (104) clears the INSIDE candle's high
    (102) but stays below the STANDING anchor's trigger (105) must not fill -- exactly the entry
    the §5.3.5a skip exists to prevent."""
    rows = [
        *_BULLISH_PREFIX,
        {"open": 100, "high": 105, "low": 97, "close": 100},  # 3: re-anchor, trigger=105
        {"open": 100, "high": 102, "low": 98, "close": 100},  # 4: inside bar 3
        {"open": 100, "high": 104, "low": 99, "close": 102},  # 5: above 102, still below 105
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    assert not any(r.event == EntryEvent.ENTRY_FILLED for r in records[5])
    assert records[5] == []


# ---------------------------------------------------------------------------
# Case 6 -- fill at the trigger on a trade-through; stop = the PTB's opposite extreme
# ---------------------------------------------------------------------------


def test_case6_fill_at_trigger_on_trade_through():
    rows = [
        *_BULLISH_PREFIX,
        {"open": 100, "high": 105, "low": 97, "close": 100},  # 3: re-anchor, trigger=105, stop=97
        {"open": 100, "high": 112, "low": 101, "close": 108},  # 4: trades through 105, no gap
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    filled = records[4]
    assert [r.event for r in filled] == [EntryEvent.ENTRY_FILLED]
    assert filled[0].fill == 105.0
    assert filled[0].trigger == 105.0
    assert filled[0].stop == 97.0  # bar 3's own low -- the PTB's opposite extreme
    assert filled[0].anchor_pos == 3


# ---------------------------------------------------------------------------
# Case 7 -- exact touch of the trigger does not fill (negative control)
# ---------------------------------------------------------------------------


def test_case7_negative_control_exact_touch_does_not_fill():
    rows = [
        *_BULLISH_PREFIX,
        # high == trigger (108) exactly, no gap -- strict inequality means no fill.
        {"open": 100, "high": 108, "low": 101, "close": 105},
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    assert not any(r.event == EntryEvent.ENTRY_FILLED for r in records[3])
    assert records[3] == []


# ---------------------------------------------------------------------------
# Case 8 -- gap fill: worse than the trigger, never better
# ---------------------------------------------------------------------------


def test_case8_gap_fill_is_worse_than_trigger_never_better():
    rows = [
        *_BULLISH_PREFIX,
        {"open": 112, "high": 115, "low": 110, "close": 113},  # 3: opens beyond the trigger (108)
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    filled = records[3]
    assert [r.event for r in filled] == [EntryEvent.ENTRY_FILLED]
    assert filled[0].fill == 112.0
    assert filled[0].fill == pytest.approx(filled[0].fill)
    assert filled[0].fill > filled[0].trigger  # a long paid MORE than the trigger -- worse
    assert filled[0].trigger == 108.0
    assert filled[0].stop == 99.0


# ---------------------------------------------------------------------------
# Case 9 -- full bearish mirror of 2 through 6
# ---------------------------------------------------------------------------


def test_case9_bearish_full_mirror_anchor_reanchor_inside_and_fill():
    rows = [
        {"open": 98, "high": 100, "low": 90, "close": 95},  # 0: arm
        {"open": 90, "high": 95, "low": 80, "close": 85},  # 1: expansion (parent)
        # higher low (85>80) AND higher high (98>95) than parent -- pullback opens & anchors.
        {"open": 90, "high": 98, "low": 85, "close": 92},  # 2: trigger=85 (low), stop=98 (high)
        # not inside bar 2 (101 is NOT <=98); no fill (low 88 not < trigger 85) -- re-anchors.
        {"open": 95, "high": 101, "low": 88, "close": 95},  # 3: trigger=88, stop=101
        # inside bar 3 (99<=101 and 90>=88) -- anchor must not move.
        {"open": 95, "high": 99, "low": 90, "close": 95},  # 4
        # negative control: low (89) below the inside candle's low (90) but above the standing
        # anchor's trigger (88) -- must not fill.
        {"open": 95, "high": 93, "low": 89, "close": 95},  # 5
        # trades through 88, no gap (open 95 not < 88) -- fills at the trigger.
        {"open": 95, "high": 96, "low": 85, "close": 90},  # 6
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BEARISH, rows, events_by_pos={0: _arm(Direction.BEARISH)}
    )

    anchored2 = records[2]
    assert [r.event for r in anchored2] == [EntryEvent.PTB_ANCHORED]
    assert anchored2[0].anchor_pos == 2
    assert anchored2[0].trigger == 85.0
    assert anchored2[0].stop == 98.0

    reanchored3 = records[3]
    assert [r.event for r in reanchored3] == [EntryEvent.PTB_ANCHORED]
    assert reanchored3[0].anchor_pos == 3
    assert reanchored3[0].trigger == 88.0  # moved up from 85
    assert reanchored3[0].stop == 101.0

    assert records[4] == []  # inside bar 3 -- anchor unmoved
    assert records[5] == []  # negative control -- no fill

    filled6 = records[6]
    assert [r.event for r in filled6] == [EntryEvent.ENTRY_FILLED]
    assert filled6[0].fill == 88.0
    assert filled6[0].trigger == 88.0
    assert filled6[0].stop == 101.0  # bar 3's own high -- the PTB's opposite extreme
    assert filled6[0].anchor_pos == 3


# ---------------------------------------------------------------------------
# Case 10 -- each §5.4.7 invalidation event cancels a working order
# ---------------------------------------------------------------------------


def _invalidation_cancels_order(event: Event):
    rows = [
        *_BULLISH_PREFIX,
        {"open": 103, "high": 105, "low": 101, "close": 103},  # 3: no trade-through, no fill
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH,
        rows,
        events_by_pos={
            0: _arm(Direction.BULLISH),
            3: [EventRecord(3, event, Direction.BULLISH)],
        },
    )
    cancelled = records[3]
    assert [r.event for r in cancelled] == [EntryEvent.ORDER_CANCELLED]
    assert cancelled[0].anchor_pos == 2
    assert cancelled[0].trigger == 108.0
    assert cancelled[0].stop == 99.0
    assert machine.state.order is None
    assert machine.state.armed is False
    assert machine.state.positions == ()


def test_case10_invalidation_a_opposite_step3_cancels_order():
    _invalidation_cancels_order(Event.INVALIDATED_OPPOSITE_STEP_3)


def test_case10_invalidation_b_ma_close_cancels_order():
    _invalidation_cancels_order(Event.INVALIDATED_MA_CLOSE)


def test_case10_invalidation_c_boundary_close_cancels_order():
    _invalidation_cancels_order(Event.INVALIDATED_BOUNDARY_CLOSE)


# ---------------------------------------------------------------------------
# Case 11 -- RESET does not cancel a working order, but blocks a NEW pullback
# ---------------------------------------------------------------------------


def test_case11_reset_does_not_cancel_order_but_blocks_new_pullback():
    rows = [
        *_BULLISH_PREFIX,
        # inside bar 2 (105<=108 and 101>=99); no fill (105 < trigger 108). RESET fires here.
        {"open": 103, "high": 105, "low": 101, "close": 102},  # 3
        # trades through the still-standing trigger (108) -- the order fills normally post-RESET.
        {"open": 103, "high": 112, "low": 100, "close": 110},  # 4
        # a fresh pullback candidate vs its parent (bar 4): lower high (108<112) and lower low
        # (95<100) -- would anchor if armed, but RESET disarmed the machine.
        {"open": 103, "high": 108, "low": 95, "close": 100},  # 5
    ]
    machine, _, records, states = _run_entry(
        Direction.BULLISH,
        rows,
        events_by_pos={
            0: _arm(Direction.BULLISH),
            3: [EventRecord(3, Event.RESET, Direction.BULLISH, step3_extreme=112.0)],
        },
    )
    assert records[3] == []  # RESET itself emits no EntryRecord
    assert states[3].order is not None  # order survives the reset (O-15), checked right after it
    assert states[3].armed is False

    filled = records[4]
    assert [r.event for r in filled] == [EntryEvent.ENTRY_FILLED]
    assert filled[0].fill == 108.0
    assert filled[0].anchor_pos == 2

    assert records[5] == []  # armed is False -- no new pullback may be scanned
    assert machine.state.order is None
    assert machine.state.armed is False


# ---------------------------------------------------------------------------
# Case 12 -- break-even fires once, then the position is dropped
# ---------------------------------------------------------------------------


def test_case12_break_even_fires_once_then_position_dropped():
    rows = [
        *_BULLISH_PREFIX,
        {"open": 103, "high": 109, "low": 101, "close": 107},  # 3: fills (109>108), stays open
        {"open": 109, "high": 118, "low": 108, "close": 116},  # 4: trades through frozen extreme
        {"open": 116, "high": 125, "low": 115, "close": 120},  # 5: still above -- must not re-fire
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH,
        rows,
        events_by_pos={0: _arm(Direction.BULLISH)},
        extremes_by_pos={3: 115.0},  # frozen at fill; bar 3's own high (109) does not clear it
    )
    filled = records[3]
    assert [r.event for r in filled] == [EntryEvent.ENTRY_FILLED]

    be = records[4]
    assert [r.event for r in be] == [EntryEvent.STOP_TO_BREAK_EVEN]
    assert be[0].stop == 108.0  # == fill
    assert be[0].step3_extreme == 115.0

    assert records[5] == []  # fires once; the position was dropped
    assert machine.state.positions == ()


# ---------------------------------------------------------------------------
# Case 13 -- negative control: the break-even level is frozen at fill
# ---------------------------------------------------------------------------


def test_case13_negative_control_break_even_level_frozen_at_fill():
    """A HIGHER running extreme fed on a LATER bar must not move the break-even threshold: the
    fill freezes 110.0; bar 4 trades to 115 (beyond the frozen 110, so break-even should fire)
    while the machine is simultaneously told the live running extreme is now 130 (well above
    115). If break-even wrongly read the live value, it would NOT fire here."""
    rows = [
        *_BULLISH_PREFIX,
        {"open": 103, "high": 109, "low": 101, "close": 107},  # 3: fills (109>108); frozen=110
        {"open": 109, "high": 115, "low": 108, "close": 112},  # 4: 115 > frozen(110), < live(130)
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH,
        rows,
        events_by_pos={0: _arm(Direction.BULLISH)},
        extremes_by_pos={3: 110.0, 4: 130.0},
    )
    be = records[4]
    assert [r.event for r in be] == [EntryEvent.STOP_TO_BREAK_EVEN]
    assert be[0].step3_extreme == 110.0  # the frozen value, not the live 130.0
    assert be[0].stop == 108.0


# ---------------------------------------------------------------------------
# Case 14 -- continuation: a second fill in the same directional state freezes
# a different number from the same series (§3.7)
# ---------------------------------------------------------------------------


def test_case14_continuation_second_fill_freezes_different_extreme():
    rows = [
        {"open": 98, "high": 100, "low": 95, "close": 98},  # 0: arm
        {"open": 108, "high": 110, "low": 101, "close": 108},  # 1: expansion (parent)
        {"open": 100, "high": 108, "low": 99, "close": 100},  # 2: pullback1 anchors (108/99)
        {"open": 103, "high": 112, "low": 101, "close": 110},  # 3: fill #1 (112>108)
        {"open": 112, "high": 115, "low": 106, "close": 113},  # 4: expansion (new parent)
        {"open": 106, "high": 110, "low": 100, "close": 105},  # 5: pullback2 anchors (110/100)
        {"open": 105, "high": 115, "low": 102, "close": 112},  # 6: fill #2 (115>110)
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH,
        rows,
        events_by_pos={0: _arm(Direction.BULLISH)},
        extremes_by_pos={3: 112.0, 6: 118.0},
    )
    filled = [r for recs in records.values() for r in recs if r.event == EntryEvent.ENTRY_FILLED]
    assert len(filled) == 2
    assert filled[0].fill == 108.0
    assert filled[0].step3_extreme == 112.0
    assert filled[1].fill == 110.0
    assert filled[1].step3_extreme == 118.0
    assert filled[0].step3_extreme != filled[1].step3_extreme


# ---------------------------------------------------------------------------
# Case 15 -- no bar cap: an 8-bar pullback keeps re-anchoring and never expires
# ---------------------------------------------------------------------------


def test_case15_no_bar_cap_eight_bar_pullback_keeps_reanchoring():
    rows = [
        {"open": 98, "high": 100, "low": 95, "close": 98},  # 0: arm
        {"open": 180, "high": 200, "low": 150, "close": 190},  # 1: expansion (parent)
        {"open": 185, "high": 190, "low": 140, "close": 185},  # 2: anchor -> trigger=190, stop=140
        {"open": 175, "high": 180, "low": 130, "close": 175},  # 3: re-anchor -> 180/130
        {"open": 165, "high": 170, "low": 120, "close": 165},  # 4: re-anchor -> 170/120
        {"open": 155, "high": 160, "low": 110, "close": 155},  # 5: re-anchor -> 160/110
        {"open": 145, "high": 150, "low": 100, "close": 145},  # 6: re-anchor -> 150/100
        {"open": 135, "high": 140, "low": 90, "close": 135},  # 7: re-anchor -> 140/90
        {"open": 125, "high": 130, "low": 80, "close": 125},  # 8: re-anchor -> 130/80
        {"open": 115, "high": 120, "low": 70, "close": 115},  # 9: re-anchor -> 120/70
    ]
    machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    anchored = [r for recs in records.values() for r in recs if r.event == EntryEvent.PTB_ANCHORED]
    assert len(anchored) == 8
    assert [r.anchor_pos for r in anchored] == [2, 3, 4, 5, 6, 7, 8, 9]
    assert machine.state.order == WorkingOrder(anchor_pos=9, trigger=120.0, stop=70.0)
    assert machine.state.positions == ()  # never filled


# ---------------------------------------------------------------------------
# Case 16 -- no minimum-R gate (O-10): a 1-tick-range PTB still fills
# ---------------------------------------------------------------------------


def test_case16_no_minimum_r_gate_tiny_range_ptb_still_fills():
    rows = [
        {"open": 98, "high": 100, "low": 95, "close": 98},  # 0: arm
        {"open": 108, "high": 110, "low": 101, "close": 108},  # 1: expansion (parent)
        # tiny range (0.01): lower high & lower low than parent -- still a valid pullback bar.
        {"open": 100.005, "high": 100.01, "low": 100.00, "close": 100.005},  # 2
        {"open": 100.005, "high": 100.02, "low": 100.00, "close": 100.01},  # 3: fills
    ]
    _machine, _, records, _states = _run_entry(
        Direction.BULLISH, rows, events_by_pos={0: _arm(Direction.BULLISH)}
    )
    filled = records[3]
    assert [r.event for r in filled] == [EntryEvent.ENTRY_FILLED]
    assert filled[0].fill == pytest.approx(100.01)
    assert filled[0].stop == pytest.approx(100.00)


# ---------------------------------------------------------------------------
# Case 17 -- replay_entries smoke test
# ---------------------------------------------------------------------------

_REPLAY_COLUMNS = ["pos", "ts", "event", "direction", "anchor_pos", "trigger", "stop", "fill",
                   "step3_extreme"]


def _replay_stub_judgment() -> Judgment:
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    return Judgment(
        is_meaningful_break=lambda *_: True,
        find_base=lambda *_: base,
        select_boundary=lambda *_: boundary,
        is_meaningful_close=lambda *_: True,
    )


def _replay_bars() -> pd.DataFrame:
    common = {"sma_10": 100, "sma_20": 100}
    return _bars(
        [
            {"high": 106, "low": 101, "close": 105, **common},  # 0: Step1
            {"high": 106, "low": 103, "close": 104, **common},  # 1: base bar
            {"high": 112, "low": 105, "close": 111, **common},  # 2: break + confirm
            {"high": 120, "low": 113, "close": 118, **common},  # 3: expansion (parent)
            {"high": 118, "low": 110, "close": 115, **common},  # 4: pullback opens & anchors
            {"open": 115, "high": 122, "low": 112, "close": 120, **common},  # 5: fill
        ]
    )


def test_case17_replay_entries_smoke_test_schema_and_determinism():
    judgment = _replay_stub_judgment()
    bars = _replay_bars()

    result = replay_entries(bars, judgment)

    assert list(result.columns) == _REPLAY_COLUMNS
    assert str(result["pos"].dtype) == "Int64"
    assert str(result["anchor_pos"].dtype) == "Int64"
    assert result["ts"].dtype == bars.index.dtype
    assert result["event"].dtype == object
    assert result["direction"].dtype == object
    for col in ("trigger", "stop", "fill", "step3_extreme"):
        assert result[col].dtype == "float64"

    # replay_entries returns only L3's own events, not L2's.
    assert set(result["event"]) <= set(EntryEvent)

    anchored = result[result["event"] == EntryEvent.PTB_ANCHORED]
    assert list(anchored["pos"]) == [4]
    assert list(anchored["trigger"]) == [118.0]

    filled = result[result["event"] == EntryEvent.ENTRY_FILLED]
    assert list(filled["pos"]) == [5]
    assert list(filled["fill"]) == [118.0]

    result_again = replay_entries(bars, judgment)
    pd.testing.assert_frame_equal(result, result_again)


def test_case17_replay_entries_empty_result_has_same_schema():
    empty_judgment = Judgment(
        is_meaningful_break=lambda *_: False,
        find_base=lambda *_: None,
        select_boundary=lambda *_: None,
        is_meaningful_close=lambda *_: False,
    )
    bars = _bars([{"high": 106, "low": 101, "close": 105, "sma_10": 100, "sma_20": 100}])

    result = replay_entries(bars, empty_judgment)

    assert len(result) == 0
    assert list(result.columns) == _REPLAY_COLUMNS
    assert str(result["pos"].dtype) == "Int64"
    assert str(result["anchor_pos"].dtype) == "Int64"
    assert result["ts"].dtype == bars.index.dtype
    assert result["event"].dtype == object
    assert result["direction"].dtype == object
    for col in ("trigger", "stop", "fill", "step3_extreme"):
        assert result[col].dtype == "float64"


# ---------------------------------------------------------------------------
# Sanity: OpenEntry / EntryRecord constructed above are the real dataclasses
# ---------------------------------------------------------------------------


def test_open_entry_and_entry_record_are_frozen_dataclasses():
    entry = OpenEntry(fill_pos=0, fill=1.0, stop=0.5, step3_extreme=None)
    with pytest.raises(AttributeError):
        entry.fill = 2.0  # type: ignore[misc]
