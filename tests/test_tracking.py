"""Unit tests for stoic.tracking (Phase 7) -- hand-built fixtures only, no disk or network.

Design: `docs/PHASE7.md`. Fixtures mirror the real engine schemas exactly (`stoic/emission.py`'s
`_PAYLOAD_COLUMNS`, `stoic/sequence.py`'s), per `docs/CONSTRAINTS.md`'s named defect class -- a
hand-built fixture that guesses the schema instead of matching it has hit this repo three times.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from stoic.emission import EmissionEvent, SignalType
from stoic.sequence import Event
from stoic.sessions import flatten_cutoff_utc
from stoic.structure import Direction
from stoic.tracking import (
    Outcome,
    TrackFlag,
    track_outcomes,
)

SESSION_DATE = dt.date(2026, 7, 31)
CUTOFF = flatten_cutoff_utc([SESSION_DATE])[0]
FLATTEN_BAR_START = CUTOFF.floor("5min")

FAR_START = pd.Timestamp("2026-07-31 14:00", tz="UTC")  # well clear of CUTOFF for non-flatten tests


# ---------------------------------------------------------------------------
# Fixture builders -- real schemas, not guesses at them
# ---------------------------------------------------------------------------


def _bars(start: pd.Timestamp, n: int, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price}, index=index, dtype="float64"
    )


def _minute_bars(start: pd.Timestamp, n: int, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price}, index=index, dtype="float64"
    )


_EMISSIONS_COLUMNS = [
    "pos", "ts", "event", "direction", "blocked_by", "signal_id", "source", "instrument",
    "type_", "setup_tf", "signal_ts", "anchor_ts", "anchor_pos", "fill_pos", "trigger",
    "fill", "stop", "r", "tp1", "tp2", "setup_type", "continuation", "confluence_present",
    "confluence_score", "confluence_of",
]


def _emissions(bars_index: pd.DatetimeIndex, rows: list[dict]) -> pd.DataFrame:
    """Mirrors `stoic/emission.py`'s `_PAYLOAD_COLUMNS` frame construction exactly."""
    data = {c: [row.get(c) for row in rows] for c in _EMISSIONS_COLUMNS}
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=bars_index.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "blocked_by": pd.Series(data["blocked_by"], dtype="object"),
            "signal_id": pd.Series(data["signal_id"], dtype="object"),
            "source": pd.Series(data["source"], dtype="object"),
            "instrument": pd.Series(data["instrument"], dtype="object"),
            "type_": pd.Series(data["type_"], dtype="object"),
            "setup_tf": pd.Series(data["setup_tf"], dtype="object"),
            "signal_ts": pd.Series(data["signal_ts"], dtype=bars_index.dtype),
            "anchor_ts": pd.Series(data["anchor_ts"], dtype=bars_index.dtype),
            "anchor_pos": pd.Series(data["anchor_pos"], dtype="Int64"),
            "fill_pos": pd.Series(data["fill_pos"], dtype="Int64"),
            "trigger": pd.Series(data["trigger"], dtype="float64"),
            "fill": pd.Series(data["fill"], dtype="float64"),
            "stop": pd.Series(data["stop"], dtype="float64"),
            "r": pd.Series(data["r"], dtype="float64"),
            "tp1": pd.Series(data["tp1"], dtype="float64"),
            "tp2": pd.Series(data["tp2"], dtype="float64"),
            "setup_type": pd.Series(data["setup_type"], dtype="object"),
            "continuation": pd.Series(data["continuation"], dtype="boolean"),
            "confluence_present": pd.Series(data["confluence_present"], dtype="object"),
            "confluence_score": pd.Series(data["confluence_score"], dtype="Int64"),
            "confluence_of": pd.Series(data["confluence_of"], dtype="Int64"),
        }
    )


def _signal_row(
    bars_index: pd.DatetimeIndex,
    *,
    pos: int,
    direction: Direction,
    fill: float,
    stop: float,
    trigger: float,
    tp1: float | None = None,
    r: float | None = None,
    signal_id: str = "sig",
) -> dict:
    ts = bars_index[pos]
    return {
        "pos": pos, "ts": ts, "event": EmissionEvent.SIGNAL, "direction": direction,
        "blocked_by": (), "signal_id": signal_id, "source": "stoic_123", "instrument": "NQ",
        "type_": SignalType.SCALP, "setup_tf": "5m", "signal_ts": ts, "anchor_ts": ts,
        "anchor_pos": pos, "fill_pos": pos, "trigger": trigger, "fill": fill, "stop": stop,
        "r": r if r is not None else abs(fill - stop), "tp1": tp1, "tp2": None,
        "setup_type": "123_ptb", "continuation": False,
        "confluence_present": (), "confluence_score": 0, "confluence_of": 3,
    }


def _break_even_row(
    bars_index: pd.DatetimeIndex, *, pos: int, direction: Direction, signal_id: str
) -> dict:
    return {
        "pos": pos, "ts": bars_index[pos], "event": EmissionEvent.BREAK_EVEN,
        "direction": direction, "signal_id": signal_id,
    }


_SEQ_COLUMNS = [
    "pos", "ts", "event", "direction", "boundary_level", "base_start", "base_end",
    "step2_swing_pos", "step2_swing_price", "step3_extreme",
]


def _sequence_events(bars_index: pd.DatetimeIndex, rows: list[dict]) -> pd.DataFrame:
    """Mirrors `stoic/sequence.py`'s `_PAYLOAD_COLUMNS` frame construction exactly."""
    data = {c: [row.get(c) for row in rows] for c in _SEQ_COLUMNS}
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=bars_index.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "boundary_level": pd.Series(data["boundary_level"], dtype="float64"),
            "base_start": pd.Series(data["base_start"], dtype="Int64"),
            "base_end": pd.Series(data["base_end"], dtype="Int64"),
            "step2_swing_pos": pd.Series(data["step2_swing_pos"], dtype="Int64"),
            "step2_swing_price": pd.Series(data["step2_swing_price"], dtype="float64"),
            "step3_extreme": pd.Series(data["step3_extreme"], dtype="float64"),
        }
    )


def _invalidation_row(
    bars_index: pd.DatetimeIndex,
    *,
    pos: int,
    direction: Direction,
    event: Event = Event.INVALIDATED_BOUNDARY_CLOSE,
) -> dict:
    return {"pos": pos, "ts": bars_index[pos], "event": event, "direction": direction}


def _run(bars, emission_rows, seq_rows=(), minute_bars=None, type_=SignalType.SCALP):
    return track_outcomes(
        bars,
        emissions=_emissions(bars.index, emission_rows),
        sequence_events=_sequence_events(bars.index, list(seq_rows)),
        minute_bars=minute_bars,
        type_=type_,
    )


# ---------------------------------------------------------------------------
# Plain (non-drilled) stop / tp1
# ---------------------------------------------------------------------------


def test_stop_reached_plain_bar_long():
    bars = _bars(FAR_START, 5)
    bars.loc[bars.index[2], "low"] = 90.0
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)])
    row = out.iloc[0]
    assert row["outcome"] == Outcome.STOP
    assert row["exit_pos"] == 2
    assert row["exit_ts"] == bars.index[2]
    assert row["exit_price"] == 95.0
    assert row["bars_held"] == 2
    assert row["r_realized"] == pytest.approx(-1.0)
    assert row["flags"] == ()


def test_tp1_reached_plain_bar_long():
    bars = _bars(FAR_START, 5)
    bars.loc[bars.index[3], "high"] = 130.0
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)])
    row = out.iloc[0]
    assert row["outcome"] == Outcome.TP1
    assert row["exit_pos"] == 3
    assert row["exit_price"] == 120.0
    assert row["r_realized"] == pytest.approx((120.0 - 100.0) / 5.0)
    assert row["flags"] == ()


def test_open_when_bar_spine_ends_first():
    bars = _bars(FAR_START, 4)  # stays flat -- nothing ever reached
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)])
    row = out.iloc[0]
    assert row["outcome"] == Outcome.OPEN
    for field in ("exit_pos", "exit_ts", "exit_price", "bars_held", "r_realized"):
        assert row[field] is None or pd.isna(row[field])
    assert row["flags"] == ()


@pytest.mark.parametrize(
    "direction, bar_field, level_kind",
    [
        (Direction.BULLISH, "low", "stop"),
        (Direction.BULLISH, "high", "tp1"),
        (Direction.BEARISH, "high", "stop"),
        (Direction.BEARISH, "low", "tp1"),
    ],
)
def test_exact_touch_does_not_trigger(direction, bar_field, level_kind):
    fill = 100.0
    stop = 95.0 if direction == Direction.BULLISH else 105.0
    tp1 = 120.0 if direction == Direction.BULLISH else 80.0
    level_value = stop if level_kind == "stop" else tp1

    bars = _bars(FAR_START, 2)
    bars.loc[bars.index[1], bar_field] = level_value
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=direction,
                                   fill=fill, stop=stop, trigger=fill, tp1=tp1)])
    assert out.iloc[0]["outcome"] == Outcome.OPEN


# ---------------------------------------------------------------------------
# Window 1 -- two levels on one bar (whole-bar span); also the required negative control
# ---------------------------------------------------------------------------


def test_two_levels_one_bar_negative_control_order_flips_the_outcome():
    """Same 5m bar, same fixture, only the 1m order differs -- the required negative control for
    intrabar resolution (`coding_rules.md`). Short direction, so this also covers a genuine
    (non-exact-touch) short stop/tp1 hit."""
    bars = _bars(FAR_START, 3)
    bars.loc[bars.index[2], "high"] = 110.0  # breaches the short's stop (105)
    bars.loc[bars.index[2], "low"] = 85.0  # breaches the short's tp1 (90)
    signal = [_signal_row(bars.index, pos=0, direction=Direction.BEARISH,
                           fill=100.0, stop=105.0, trigger=100.0, tp1=90.0)]

    stop_first = _minute_bars(bars.index[2], 5)
    stop_first.loc[stop_first.index[0], "high"] = 110.0  # stop hit in minute 0
    stop_first.loc[stop_first.index[1], "low"] = 85.0  # tp1 hit in minute 1, after
    out_stop = _run(bars, signal, minute_bars=stop_first)
    row_stop = out_stop.iloc[0]
    assert row_stop["outcome"] == Outcome.STOP
    assert row_stop["exit_price"] == 105.0
    assert row_stop["exit_ts"] == stop_first.index[0]
    assert TrackFlag.RESOLVED_ON_1M in row_stop["flags"]

    tp1_first = _minute_bars(bars.index[2], 5)
    tp1_first.loc[tp1_first.index[0], "low"] = 85.0  # tp1 hit in minute 0
    tp1_first.loc[tp1_first.index[1], "high"] = 110.0  # stop hit in minute 1, after
    out_tp1 = _run(bars, signal, minute_bars=tp1_first)
    row_tp1 = out_tp1.iloc[0]
    assert row_tp1["outcome"] == Outcome.TP1
    assert row_tp1["exit_price"] == 90.0
    assert row_tp1["exit_ts"] == tp1_first.index[0]
    assert TrackFlag.RESOLVED_ON_1M in row_tp1["flags"]


def test_two_levels_one_bar_ambiguous_minute_bars_none():
    bars = _bars(FAR_START, 3)
    bars.loc[bars.index[2], "low"] = 90.0
    bars.loc[bars.index[2], "high"] = 130.0
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)],
               minute_bars=None)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.AMBIGUOUS
    assert row["flags"] == (TrackFlag.UNRESOLVED_NO_1M,)
    for field in ("exit_pos", "exit_ts", "exit_price", "r_realized"):
        assert row[field] is None or pd.isna(row[field])


def test_two_levels_one_bar_ambiguous_single_1m_bar_spans_both():
    bars = _bars(FAR_START, 3)
    bars.loc[bars.index[2], "low"] = 90.0
    bars.loc[bars.index[2], "high"] = 130.0
    minute_bars = _minute_bars(bars.index[2], 5)
    minute_bars.loc[minute_bars.index[0], "low"] = 90.0
    minute_bars.loc[minute_bars.index[0], "high"] = 130.0  # one 1m bar spans both levels
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.AMBIGUOUS
    assert row["flags"] == (TrackFlag.UNRESOLVED_1M_AMBIGUOUS,)


def test_two_levels_one_bar_ambiguous_span_has_no_1m_coverage():
    """The second of the three AMBIGUOUS triggers: `minute_bars` is real, but has no bars in the
    relevant span (a real gap, e.g. 2025-11-28 / 2026-06-11->06-19) -- distinct from `None`."""
    bars = _bars(FAR_START, 3)
    bars.loc[bars.index[2], "low"] = 90.0
    bars.loc[bars.index[2], "high"] = 130.0
    elsewhere = _minute_bars(pd.Timestamp("2020-01-01", tz="UTC"), 5)
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)],
               minute_bars=elsewhere)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.AMBIGUOUS
    assert row["flags"] == (TrackFlag.UNRESOLVED_NO_1M,)


# ---------------------------------------------------------------------------
# Window 2 -- the fill bar
# ---------------------------------------------------------------------------


def test_fill_bar_gap_beyond_tp1():
    bars = _bars(FAR_START, 2, price=125.0)
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=125.0, stop=95.0, trigger=100.0, tp1=120.0)])
    row = out.iloc[0]
    assert row["outcome"] == Outcome.TP1
    assert row["exit_pos"] == 0
    assert row["exit_ts"] == bars.index[0]
    assert row["exit_price"] == 125.0
    assert row["bars_held"] == 0
    assert row["r_realized"] == pytest.approx(0.0)
    assert row["flags"] == (TrackFlag.GAP_BEYOND_TP1,)


def test_fill_and_invalidate_on_one_bar():
    bars = _bars(FAR_START, 2)
    out = _run(
        bars,
        [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                     fill=100.0, stop=95.0, trigger=100.0, tp1=120.0)],
        seq_rows=[_invalidation_row(bars.index, pos=0, direction=Direction.BULLISH)],
    )
    row = out.iloc[0]
    assert row["outcome"] == Outcome.INVALIDATED
    assert row["exit_pos"] == 0
    assert row["bars_held"] == 0
    assert row["exit_price"] == 100.0  # the fill bar's own close (flat fixture)


def test_fill_bar_dip_to_stop_before_trigger_triggers_does_not_stop_out():
    """A touch fill: the 5m bar's own low (90) is below the stop (95), but that dip happened
    BEFORE the 1m bar that actually crosses the trigger -- must not be booked as a stop-out."""
    bars = _bars(FAR_START, 2)  # 2 bars: a span is inferable from 2 (A5)
    bars.loc[bars.index[0], "open"] = 98.0
    bars.loc[bars.index[0], "low"] = 90.0
    bars.loc[bars.index[0], "high"] = 105.0
    bars.loc[bars.index[0], "close"] = 100.0

    minute_bars = _minute_bars(bars.index[0], 5, price=98.0)
    minute_bars.loc[minute_bars.index[0], "low"] = 90.0  # the dip -- before the cross
    minute_bars.loc[minute_bars.index[0], "high"] = 99.0
    minute_bars.loc[minute_bars.index[1], "high"] = 101.0  # crosses trigger (100) here
    minute_bars.loc[minute_bars.index[1], "low"] = 96.0  # no dip to stop after the cross
    for i in (2, 3, 4):
        minute_bars.loc[minute_bars.index[i], "low"] = 96.0
        minute_bars.loc[minute_bars.index[i], "high"] = 101.0

    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.OPEN  # the 5m bar's low alone would have said STOP


def test_fill_bar_window_resolved_stop_after_the_fill():
    bars = _bars(FAR_START, 2)  # 2 bars: a span is inferable from 2 (A5)
    bars.loc[bars.index[0], "open"] = 98.0
    bars.loc[bars.index[0], "low"] = 90.0
    bars.loc[bars.index[0], "high"] = 105.0

    minute_bars = _minute_bars(bars.index[0], 5, price=98.0)
    minute_bars.loc[minute_bars.index[0], "low"] = 97.0  # no dip yet
    minute_bars.loc[minute_bars.index[1], "high"] = 101.0  # crosses trigger here
    minute_bars.loc[minute_bars.index[1], "low"] = 97.0
    minute_bars.loc[minute_bars.index[2], "low"] = 90.0  # genuine post-fill dip to stop

    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.STOP
    assert row["exit_ts"] == minute_bars.index[2]
    assert row["exit_price"] == 95.0
    assert TrackFlag.RESOLVED_ON_1M in row["flags"]


def test_fill_bar_window_unresolved_no_1m():
    bars = _bars(FAR_START, 2)  # 2 bars: a span is inferable from 2 (A5)
    bars.loc[bars.index[0], "open"] = 98.0
    bars.loc[bars.index[0], "low"] = 90.0
    bars.loc[bars.index[0], "high"] = 105.0
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=None)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.AMBIGUOUS
    assert row["flags"] == (TrackFlag.UNRESOLVED_NO_1M,)


# ---------------------------------------------------------------------------
# Window 3 -- the flatten bar
# ---------------------------------------------------------------------------


def _flatten_bars(n_before: int = 2, n_after: int = 2) -> pd.DataFrame:
    start = FLATTEN_BAR_START - pd.Timedelta(minutes=5 * n_before)
    return _bars(start, n_before + 1 + n_after)


def test_flatten_bar_stop_before_cutoff_wins():
    bars = _flatten_bars()
    flatten_pos = 2  # n_before=2 -> index 2 is FLATTEN_BAR_START
    bars.loc[bars.index[flatten_pos], "low"] = 90.0
    minute_bars = _minute_bars(bars.index[flatten_pos], 5)
    minute_bars.loc[minute_bars.index[0], "low"] = 90.0  # before CUTOFF (minute 0 of the bar)

    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.STOP
    assert row["exit_ts"] == minute_bars.index[0]
    assert TrackFlag.RESOLVED_ON_1M in row["flags"]


def test_flatten_bar_stop_after_cutoff_flatten_wins():
    bars = _flatten_bars()
    flatten_pos = 2
    bars.loc[bars.index[flatten_pos], "low"] = 90.0
    minute_bars = _minute_bars(bars.index[flatten_pos], 5)
    # CUTOFF falls inside this bar, not necessarily on a minute boundary offset 0 -- put the dip
    # on the last minute of the bar, strictly after CUTOFF (CUTOFF sits 2 minutes before the CME
    # close per VISION.md, well inside the bar, and this bar's minute 4 starts after it).
    minute_bars.loc[minute_bars.index[4], "low"] = 90.0
    minute_bars.loc[minute_bars.index[4], "close"] = 90.5

    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.FLATTEN
    assert row["exit_ts"] == CUTOFF
    assert row["exit_pos"] == flatten_pos


def test_flatten_bar_unresolved_no_1m_coverage():
    bars = _flatten_bars()
    flatten_pos = 2
    bars.loc[bars.index[flatten_pos], "low"] = 90.0
    elsewhere = _minute_bars(pd.Timestamp("2020-01-01", tz="UTC"), 5)
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=95.0, trigger=100.0, tp1=None)],
               minute_bars=elsewhere)
    row = out.iloc[0]
    # A4: on the flatten bar an unresolvable level order does NOT discard the certainty that the
    # trade is flat at the cutoff at a known price. AMBIGUOUS stays the answer only off it.
    assert row["outcome"] == Outcome.FLATTEN
    assert TrackFlag.FLATTEN_LEVEL_ORDER_UNRESOLVED in row["flags"]


def test_flatten_reached_with_1m_close():
    bars = _flatten_bars()
    flatten_pos = 2
    minute_bars = _minute_bars(bars.index[flatten_pos], 5)
    # A2: the 1m bar ENDING at the cutoff -- its close is the price at exactly the cutoff instant.
    # The bar STARTING at the cutoff closes a minute late and must never be the exit price.
    minute_bars.loc[CUTOFF - pd.Timedelta(minutes=1), "close"] = 101.5
    minute_bars.loc[CUTOFF, "close"] = 999.0  # a minute late -- must not be read

    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)],
               minute_bars=minute_bars)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.FLATTEN
    assert row["exit_pos"] == flatten_pos
    assert row["exit_ts"] == CUTOFF
    assert row["exit_price"] == 101.5
    assert row["flags"] == ()


def test_flatten_fallback_to_5m_close_when_1m_bar_missing():
    bars = _flatten_bars()
    flatten_pos = 2
    bars.loc[bars.index[flatten_pos], "close"] = 102.25
    out = _run(bars, [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                                   fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)],
               minute_bars=None)
    row = out.iloc[0]
    assert row["outcome"] == Outcome.FLATTEN
    assert row["exit_price"] == 102.25
    assert row["flags"] == (TrackFlag.FLATTEN_5M_FALLBACK,)


def test_invalidation_on_flatten_bar_flatten_wins():
    bars = _flatten_bars()
    flatten_pos = 2
    out = _run(
        bars,
        [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                     fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)],
        seq_rows=[_invalidation_row(bars.index, pos=flatten_pos, direction=Direction.BULLISH)],
        minute_bars=None,
    )
    row = out.iloc[0]
    assert row["outcome"] == Outcome.FLATTEN
    assert row["flags"] == (TrackFlag.FLATTEN_5M_FALLBACK,)


def test_position_type_never_flattens_while_scalp_does():
    bars = _flatten_bars(n_before=2, n_after=0)  # ends exactly on the flatten bar
    signal_kwargs = dict(pos=0, direction=Direction.BULLISH, fill=100.0, stop=50.0,
                          trigger=100.0, tp1=200.0)

    scalp = _run(bars, [_signal_row(bars.index, **signal_kwargs)],
                 minute_bars=None, type_=SignalType.SCALP)
    assert scalp.iloc[0]["outcome"] == Outcome.FLATTEN

    position = _run(bars, [_signal_row(bars.index, **signal_kwargs)],
                     minute_bars=None, type_=SignalType.POSITION)
    assert position.iloc[0]["outcome"] == Outcome.OPEN


# ---------------------------------------------------------------------------
# INVALIDATED, away from the fill/flatten bars
# ---------------------------------------------------------------------------


def test_invalidated_on_a_later_bar():
    bars = _bars(FAR_START, 5)
    out = _run(
        bars,
        [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                     fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)],
        seq_rows=[_invalidation_row(bars.index, pos=3, direction=Direction.BULLISH,
                                     event=Event.INVALIDATED_MA_CLOSE)],
    )
    row = out.iloc[0]
    assert row["outcome"] == Outcome.INVALIDATED
    assert row["exit_pos"] == 3
    assert row["exit_ts"] == bars.index[3]
    assert row["exit_price"] == 100.0


def test_invalidation_for_the_other_direction_is_ignored():
    bars = _bars(FAR_START, 5)
    out = _run(
        bars,
        [_signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                     fill=100.0, stop=50.0, trigger=100.0, tp1=200.0)],
        seq_rows=[_invalidation_row(bars.index, pos=3, direction=Direction.BEARISH)],
    )
    assert out.iloc[0]["outcome"] == Outcome.OPEN


# ---------------------------------------------------------------------------
# BREAK_EVEN -- pinned at zero
# ---------------------------------------------------------------------------


def test_a_break_even_emission_does_not_become_an_outcome_row():
    """§2: TP1 is L3's frozen step3_extreme and D-25 fires break-even against that identical
    extreme with an identical strict trade-through test, so the bar that would trip break-even is
    always the bar that reaches TP1 first, and TP1 is a full exit. A `BREAK_EVEN` emission row for
    the same signal, on the same bar, must not change the outcome and must not produce a row of
    its own -- only `SIGNAL` rows are tracked.

    **There is deliberately no assertion here that `Outcome.BREAK_EVEN` never fires.** The member
    was removed precisely because no code path could construct it, which made such an assertion a
    pin by *absence* -- true whatever the code did. The real tripwire for the premise this rests
    on lives in `tests/test_forward_test.py`, driven through the engine, where it can fail.
    """
    bars = _bars(FAR_START, 3)
    bars.loc[bars.index[1], "high"] = 130.0
    emission_rows = [
        _signal_row(bars.index, pos=0, direction=Direction.BULLISH,
                    fill=100.0, stop=95.0, trigger=100.0, tp1=120.0, signal_id="sig-1"),
        _break_even_row(bars.index, pos=1, direction=Direction.BULLISH, signal_id="sig-1"),
    ]
    out = _run(bars, emission_rows)
    assert len(out) == 1
    assert out.iloc[0]["outcome"] == Outcome.TP1


# ---------------------------------------------------------------------------
# Schema discipline
# ---------------------------------------------------------------------------


def test_empty_input_returns_the_right_schema_and_dtypes():
    bars = _bars(FAR_START, 3)
    out = _run(bars, [])
    assert len(out) == 0
    assert list(out.columns) == [
        "signal_id", "direction", "fill_pos", "fill_ts", "fill", "stop", "tp1", "r",
        "outcome", "exit_pos", "exit_ts", "exit_price", "bars_held", "r_realized", "flags",
    ]
    assert out["signal_id"].dtype == "object"
    assert out["direction"].dtype == "object"
    assert out["fill_pos"].dtype == "Int64"
    assert out["fill_ts"].dtype == bars.index.dtype
    assert out["fill"].dtype == "float64"
    assert out["stop"].dtype == "float64"
    assert out["tp1"].dtype == "float64"
    assert out["r"].dtype == "float64"
    assert out["outcome"].dtype == "object"
    assert out["exit_pos"].dtype == "Int64"
    assert out["exit_ts"].dtype == bars.index.dtype
    assert out["exit_price"].dtype == "float64"
    assert out["bars_held"].dtype == "Int64"
    assert out["r_realized"].dtype == "float64"
    assert out["flags"].dtype == "object"


# ---------------------------------------------------------------------------
# Import direction (mirrors tests/test_fidelity.py)
# ---------------------------------------------------------------------------

STOIC = Path(__file__).resolve().parents[1] / "stoic"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_engine_module_imports_tracking():
    """Measurement must never be reachable from the signal path (docs/PHASE7.md §7)."""
    offenders = [
        path.name
        for path in sorted(STOIC.glob("*.py"))
        if path.name != "tracking.py"
        if any("tracking" in name for name in _imported_names(path))
    ]
    assert offenders == []


def test_the_import_check_can_actually_see_an_import(tmp_path):
    """Negative control: the same parser must catch a planted import."""
    planted = tmp_path / "planted.py"
    planted.write_text("from stoic.tracking import track_outcomes\n", encoding="utf-8")
    assert any("tracking" in name for name in _imported_names(planted))
