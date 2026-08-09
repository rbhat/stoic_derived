"""Unit tests for stoic.emission (L5) -- hand-built fixtures only, no disk or network access.

`SignalEmitter` is driven directly with synthetic `stoic.entry.EntryRecord`s and `stoic.sequence.
EventRecord`s (mirroring how `tests/test_entry.py` drives `EntryMachine` without needing
`find_base`), so the D-32/D-33 logic is testable in isolation from L1-L3. Only `replay_signals`'s
smoke test drives the full `iter_replay_steps` pipeline with a stub `Judgment`.

Every gate/condition here gets a negative control per `coding_rules.md`: inject the fault it
exists to catch and confirm it actually fails.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stoic.emission import (
    Confluence,
    EmissionEvent,
    HtfAlignment,
    SignalEmitter,
    SignalType,
    replay_signals,
)
from stoic.entry import EntryEvent, EntryRecord
from stoic.gating import GateReason
from stoic.sequence import BaseSpan, Event, EventRecord, HorizontalBoundary, Judgment
from stoic.structure import Direction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bars(
    closes: list[float],
    sma_50: list[float] | None = None,
    sma_200: list[float] | None = None,
) -> pd.DataFrame:
    """Bars carrying only what `gate()` and the confluence read need: close, sma_50, sma_200."""
    n = len(closes)
    index = pd.date_range("2026-01-05", periods=n, freq="5min", tz="UTC")
    index.name = "ts_event"
    return pd.DataFrame(
        {
            "close": closes,
            "sma_50": sma_50 if sma_50 is not None else [np.nan] * n,
            "sma_200": sma_200 if sma_200 is not None else [np.nan] * n,
        },
        index=index,
    )


def _filled(
    pos: int,
    anchor_pos: int | None,
    *,
    trigger: float,
    fill: float,
    stop: float,
    step3_extreme: float | None,
    direction: Direction = Direction.BULLISH,
) -> EntryRecord:
    return EntryRecord(
        pos,
        EntryEvent.ENTRY_FILLED,
        direction,
        anchor_pos=anchor_pos,
        trigger=trigger,
        stop=stop,
        fill=fill,
        step3_extreme=step3_extreme,
    )


def _break_even(pos: int, fill: float, direction: Direction = Direction.BULLISH) -> EntryRecord:
    return EntryRecord(pos, EntryEvent.STOP_TO_BREAK_EVEN, direction, fill=fill, stop=fill)


def _reset(pos: int, direction: Direction = Direction.BULLISH) -> EventRecord:
    return EventRecord(pos, Event.RESET, direction, step3_extreme=None)


class _HtfStub:
    def __init__(self, aligned: bool) -> None:
        self._aligned = aligned

    def is_aligned(self, ts: pd.Timestamp, direction: Direction) -> bool:
        return self._aligned


def _emitter(
    type_: SignalType = SignalType.SWING,
    htf: HtfAlignment | None = None,
    direction: Direction = Direction.BULLISH,
) -> SignalEmitter:
    return SignalEmitter(direction, instrument="NQ", type_=type_, htf=htf)


# ---------------------------------------------------------------------------
# R -- normal fill and gap fill (§5.4.2, D-22)
# ---------------------------------------------------------------------------


def test_r_equals_abs_fill_minus_stop_on_normal_fill():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, 0, trigger=100.0, fill=100.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    assert emitted[0].signal.r == pytest.approx(5.0)


def test_r_uses_fill_not_trigger_on_gap():
    """D-22: a gap fill sits beyond the trigger while the stop stays at the PTB extreme, so R
    widens. Using the trigger instead of the fill would give 5.0, not 10.0."""
    bars = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, 0, trigger=100.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    signal = emitted[0].signal
    assert signal.trigger == pytest.approx(100.0)
    assert signal.fill == pytest.approx(105.0)
    assert signal.r == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# tp1 / tp2 (§6.1/§6.2, D-6, D-16)
# ---------------------------------------------------------------------------


def test_tp1_is_l3s_frozen_step3_extreme_not_rederived():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, 0, trigger=100.0, fill=101.0, stop=95.0, step3_extreme=130.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    signal = emitted[0].signal
    assert signal.tp1 == pytest.approx(130.0)  # the frozen value, distinct from trigger/fill/stop


def test_tp2_is_always_none():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, 0, trigger=100.0, fill=101.0, stop=95.0, step3_extreme=130.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    assert emitted[0].signal.tp2 is None


# ---------------------------------------------------------------------------
# D-32 -- confluence and the gate read at the anchor bar, never the fill bar
# ---------------------------------------------------------------------------


def test_confluence_reads_the_anchor_bar_not_the_fill_bar():
    """The most important test in this file. Anchor bar (0): close 110 > sma_50 100 -- DIR_50
    present. Fill bar (1): close 90 < sma_50 100 -- DIR_50 would be absent if wrongly read here.
    A signal must still emit (gate reads the anchor too, which passes) and DIR_50 must be present,
    proving the anchor's reading wins."""
    bars = _bars(closes=[110.0, 90.0], sma_50=[100.0, 100.0])
    emitter = _emitter()
    rec = _filled(1, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 1, entry_records=[rec], sequence_events=[])
    assert emitted[0].event == EmissionEvent.SIGNAL
    signal = emitted[0].signal
    assert signal.anchor_pos == 0
    assert signal.fill_pos == 1
    assert Confluence.DIR_50 in signal.confluence.present


# ---------------------------------------------------------------------------
# Suppression (L4's gate, unchanged)
# ---------------------------------------------------------------------------


def test_blocked_candidate_emits_suppressed_no_signal_record():
    bars = _bars(closes=[90.0], sma_50=[100.0])  # blocks TREND_50 for a bullish candidate
    emitter = _emitter()
    rec = _filled(0, 0, trigger=88.0, fill=88.0, stop=80.0, step3_extreme=95.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    assert len(emitted) == 1
    record = emitted[0]
    assert record.event == EmissionEvent.SUPPRESSED
    assert record.signal is None
    assert record.signal_id is None
    assert record.blocked_by == (GateReason.TREND_50,)


def test_both_gate_reasons_collected_on_fast_chart():
    # close 90 < sma_50 100 -> TREND_50; close 90 <= sma_200 95 -> INTO_200 (bullish, D-31)
    bars = _bars(closes=[90.0], sma_50=[100.0], sma_200=[95.0])
    emitter = _emitter(type_=SignalType.SCALP)
    rec = _filled(0, 0, trigger=88.0, fill=88.0, stop=80.0, step3_extreme=95.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    assert emitted[0].blocked_by == (GateReason.TREND_50, GateReason.INTO_200)


def test_negative_control_gate_suppression():
    """A passing baseline, then the injected fault -- raise sma_50 above the close -- must
    actually flip the outcome to SUPPRESSED."""
    passing = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(passing, 0, entry_records=[rec], sequence_events=[])
    assert emitted[0].event == EmissionEvent.SIGNAL

    faulted = _bars(closes=[110.0], sma_50=[200.0])
    emitter2 = _emitter()
    emitted2 = emitter2.step(faulted, 0, entry_records=[rec], sequence_events=[])
    assert emitted2[0].event == EmissionEvent.SUPPRESSED
    assert GateReason.TREND_50 in emitted2[0].blocked_by


# ---------------------------------------------------------------------------
# HTF alignment (§7.5.5, D-27) -- score, never a gate
# ---------------------------------------------------------------------------


def test_htf_none_caps_score_at_two_of_three():
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[100.0])
    emitter = _emitter(htf=None)
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    confluence = emitted[0].signal.confluence
    assert confluence.score == 2
    assert confluence.of == 3
    assert Confluence.HTF_STEP_3 not in confluence.present


def test_htf_true_gives_three_of_three():
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[100.0])
    emitter = _emitter(htf=_HtfStub(True))
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    confluence = emitted[0].signal.confluence
    assert confluence.score == 3
    assert confluence.present == (Confluence.DIR_50, Confluence.DIR_200, Confluence.HTF_STEP_3)


def test_htf_false_gives_two_of_three():
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[100.0])
    emitter = _emitter(htf=_HtfStub(False))
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    confluence = emitted[0].signal.confluence
    assert confluence.score == 2
    assert Confluence.HTF_STEP_3 not in confluence.present


def test_negative_control_full_confluence_score():
    """Baseline scores 3 of 3 with an aligned HTF; inverting only the HTF input must actually
    drop the score, isolating the HTF condition from the two MA reads."""
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[100.0])
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)

    full = _emitter(htf=_HtfStub(True)).step(bars, 0, entry_records=[rec], sequence_events=[])
    assert full[0].signal.confluence.score == 3

    dropped = _emitter(htf=_HtfStub(False)).step(bars, 0, entry_records=[rec], sequence_events=[])
    assert dropped[0].signal.confluence.score == 2
    assert Confluence.HTF_STEP_3 not in dropped[0].signal.confluence.present


# ---------------------------------------------------------------------------
# Conventions 1-2 -- NaN and exact ties are absent
# ---------------------------------------------------------------------------


def test_nan_sma_200_on_slow_chart_dir_200_absent_signal_still_emitted():
    """Slow chart -> gate 2 never runs (D-31), so a NaN 200 does not block the signal; the
    confluence read still marks DIR_200 absent (convention 1)."""
    bars = _bars(closes=[110.0], sma_50=[100.0], sma_200=[np.nan])
    emitter = _emitter(type_=SignalType.SWING)
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    assert emitted[0].event == EmissionEvent.SIGNAL
    confluence = emitted[0].signal.confluence
    assert Confluence.DIR_200 not in confluence.present
    assert Confluence.DIR_50 in confluence.present


def test_exact_tie_close_vs_sma_is_absent():
    """Slow chart so gate 2 is skipped entirely; the tie at the 200 isolates convention 2's
    strict inequality in the confluence read alone."""
    bars = _bars(closes=[100.0], sma_50=[90.0], sma_200=[100.0])
    emitter = _emitter(type_=SignalType.SWING)
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted = emitter.step(bars, 0, entry_records=[rec], sequence_events=[])
    confluence = emitted[0].signal.confluence
    assert Confluence.DIR_200 not in confluence.present
    assert Confluence.DIR_50 in confluence.present  # 100 > 90, unaffected


# ---------------------------------------------------------------------------
# continuation (§2.5, D-13/D-21, convention 6)
# ---------------------------------------------------------------------------


def test_continuation_false_then_true_then_false_after_reset():
    bars = _bars(
        closes=[110.0, 110.0, 110.0, 110.0],
        sma_50=[100.0, 100.0, 100.0, 100.0],
    )
    emitter = _emitter()

    fill1 = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted1 = emitter.step(bars, 0, entry_records=[fill1], sequence_events=[])
    assert emitted1[0].signal.continuation is False

    fill2 = _filled(1, 1, trigger=108.0, fill=108.0, stop=98.0, step3_extreme=125.0)
    emitted2 = emitter.step(bars, 1, entry_records=[fill2], sequence_events=[])
    assert emitted2[0].signal.continuation is True

    emitter.step(bars, 2, entry_records=[], sequence_events=[_reset(2)])
    assert emitter.state.continuation_open is False

    fill3 = _filled(3, 3, trigger=112.0, fill=112.0, stop=102.0, step3_extreme=130.0)
    emitted3 = emitter.step(bars, 3, entry_records=[fill3], sequence_events=[])
    assert emitted3[0].signal.continuation is False


def test_continuation_counts_suppressed_candidates_too():
    """Convention 6: gating must not renumber the sequence -- a suppressed fill still counts as
    the first candidate, so the next one is a continuation."""
    bars = _bars(closes=[90.0, 110.0], sma_50=[100.0, 100.0])  # bar 0 blocks, bar 1 passes
    emitter = _emitter()

    suppressed = _filled(0, 0, trigger=88.0, fill=88.0, stop=80.0, step3_extreme=95.0)
    emitted1 = emitter.step(bars, 0, entry_records=[suppressed], sequence_events=[])
    assert emitted1[0].event == EmissionEvent.SUPPRESSED

    fill2 = _filled(1, 1, trigger=108.0, fill=108.0, stop=98.0, step3_extreme=125.0)
    emitted2 = emitter.step(bars, 1, entry_records=[fill2], sequence_events=[])
    assert emitted2[0].signal.continuation is True


# ---------------------------------------------------------------------------
# BREAK_EVEN linking (§5.4.5, D-25, convention 4)
# ---------------------------------------------------------------------------


def test_break_even_emitted_for_signal_not_for_suppressed():
    bars = _bars(
        closes=[110.0, 110.0, 90.0, 110.0],
        sma_50=[100.0, 100.0, 100.0, 100.0],
    )
    emitter = _emitter()

    fill1 = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    emitted1 = emitter.step(bars, 0, entry_records=[fill1], sequence_events=[])
    assert emitted1[0].event == EmissionEvent.SIGNAL
    signal_id = emitted1[0].signal_id

    suppressed = _filled(2, 2, trigger=88.0, fill=88.0, stop=80.0, step3_extreme=95.0)
    emitted2 = emitter.step(bars, 2, entry_records=[suppressed], sequence_events=[])
    assert emitted2[0].event == EmissionEvent.SUPPRESSED

    # Break-even for the suppressed candidate's fill price -- L3 still tracks it, L5 must not.
    be_suppressed = _break_even(3, fill=88.0)
    emitted3 = emitter.step(bars, 3, entry_records=[be_suppressed], sequence_events=[])
    assert emitted3 == []

    # Break-even for the real signal.
    be_signal = _break_even(3, fill=105.0)
    emitted4 = emitter.step(bars, 3, entry_records=[be_signal], sequence_events=[])
    assert len(emitted4) == 1
    record = emitted4[0]
    assert record.event == EmissionEvent.BREAK_EVEN
    assert record.signal_id == signal_id
    assert record.signal is None


# ---------------------------------------------------------------------------
# signal_id (convention 5)
# ---------------------------------------------------------------------------


def test_signal_id_stable_across_two_runs():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    rec = _filled(0, 0, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)

    id1 = _emitter().step(bars, 0, entry_records=[rec], sequence_events=[])[0].signal_id
    id2 = _emitter().step(bars, 0, entry_records=[rec], sequence_events=[])[0].signal_id
    assert id1 == id2
    assert id1 is not None


# ---------------------------------------------------------------------------
# D-32's defensive assertion
# ---------------------------------------------------------------------------


def test_entry_filled_without_anchor_pos_raises():
    bars = _bars(closes=[110.0], sma_50=[100.0])
    emitter = _emitter()
    rec = _filled(0, None, trigger=105.0, fill=105.0, stop=95.0, step3_extreme=120.0)
    with pytest.raises(ValueError, match="anchor_pos"):
        emitter.step(bars, 0, entry_records=[rec], sequence_events=[])


# ---------------------------------------------------------------------------
# replay_signals -- schema and a full-pipeline smoke test
# ---------------------------------------------------------------------------

_REPLAY_COLUMNS = [
    "pos", "ts", "event", "direction", "blocked_by", "signal_id",
    "source", "instrument", "type_", "setup_tf",
    "signal_ts", "anchor_ts", "anchor_pos", "fill_pos",
    "trigger", "fill", "stop", "r", "tp1", "tp2",
    "setup_type", "continuation",
    "confluence_present", "confluence_score", "confluence_of",
]


def _full_bars(rows: list[dict[str, float]]) -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=len(rows), freq="5min", tz="UTC")
    index.name = "ts_event"
    data = {
        "open": [r.get("open", r["close"]) for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "sma_10": [r["sma_10"] for r in rows],
        "sma_20": [r["sma_20"] for r in rows],
        "sma_50": [r["sma_50"] for r in rows],
        "sma_200": [r["sma_200"] for r in rows],
    }
    return pd.DataFrame(data, index=index)


def _replay_stub_judgment(*, confirms: bool = True) -> Judgment:
    boundary = HorizontalBoundary(price=110.0)
    base = BaseSpan(start=1, end=1)
    return Judgment(
        is_meaningful_break=lambda *_: confirms,
        find_base=lambda *_: base,
        select_boundary=lambda *_: boundary,
        is_meaningful_close=lambda *_: confirms,
    )


def _replay_bars() -> pd.DataFrame:
    common = {"sma_10": 100, "sma_20": 100, "sma_50": 80.0, "sma_200": np.nan}
    return _full_bars(
        [
            {"high": 106, "low": 101, "close": 105, **common},  # 0: Step1
            {"high": 106, "low": 103, "close": 104, **common},  # 1: base bar
            {"high": 112, "low": 105, "close": 111, **common},  # 2: break + confirm
            {"high": 120, "low": 113, "close": 118, **common},  # 3: expansion (parent)
            {"high": 118, "low": 110, "close": 115, **common},  # 4: pullback opens & anchors
            {"open": 115, "high": 122, "low": 112, "close": 120, **common},  # 5: fill
        ]
    )


def test_replay_signals_smoke_test_schema_and_signal():
    bars = _replay_bars()
    judgment = _replay_stub_judgment()

    result = replay_signals(bars, judgment, instrument="NQ", type_=SignalType.SWING)

    assert list(result.columns) == _REPLAY_COLUMNS
    assert str(result["pos"].dtype) == "Int64"
    assert str(result["anchor_pos"].dtype) == "Int64"
    assert str(result["fill_pos"].dtype) == "Int64"
    assert result["ts"].dtype == bars.index.dtype
    assert result["signal_ts"].dtype == bars.index.dtype
    assert result["anchor_ts"].dtype == bars.index.dtype
    assert result["event"].dtype == object
    assert result["direction"].dtype == object
    for col in ("trigger", "fill", "stop", "r", "tp1", "tp2"):
        assert result[col].dtype == "float64"

    signals = result[result["event"] == EmissionEvent.SIGNAL]
    assert list(signals["pos"]) == [5]
    assert list(signals["anchor_pos"]) == [4]
    assert list(signals["fill"]) == [118.0]
    assert list(signals["trigger"]) == [118.0]


def test_replay_signals_empty_schema_when_no_fills():
    """Same columns and dtypes even when nothing is emitted -- an all-None column must not
    silently become float64."""
    bars = _replay_bars()
    judgment = _replay_stub_judgment(confirms=False)  # Step 1 never confirms -- no fills at all

    result = replay_signals(bars, judgment, instrument="NQ", type_=SignalType.SWING)

    assert len(result) == 0
    assert list(result.columns) == _REPLAY_COLUMNS
    assert str(result["pos"].dtype) == "Int64"
    assert str(result["anchor_pos"].dtype) == "Int64"
    assert result["ts"].dtype == bars.index.dtype
    for col in ("trigger", "fill", "stop", "r", "tp1", "tp2"):
        assert result[col].dtype == "float64"
