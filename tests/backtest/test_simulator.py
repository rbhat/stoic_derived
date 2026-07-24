"""Mechanics-only tests for the private conservative SP3 outcome tracker."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from stoic_derived.backtest.model import (
    BacktestValidationError,
    FillKind,
    ObservationReason,
    ObservationState,
    SimulationPolicy,
    WarningCode,
)
from stoic_derived.backtest.simulator import _OutcomeTracker
from stoic_derived.market_data.model import FinalBar, InstrumentSpec, QualityState, Timeframe
from stoic_derived.signal_engine.model import (
    CoverageGap,
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
)


def _ns(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp() * 1_000_000_000)


def _policy(**changes: int) -> SimulationPolicy:
    values: dict[str, object] = {
        "entry_slippage_ticks": 1,
        "exit_slippage_ticks": 2,
        "fees_ticks_round_turn": 3,
        "zero_costs_declared": False,
        "max_active_observations": 4,
        "max_active_lineages": 2,
        "max_retained_gaps": 4,
        "max_accepted_batches": 8,
        "max_output_records": 32,
        "max_artifact_bytes": 4096,
    }
    values.update(changes)
    return SimulationPolicy(**values)  # type: ignore[arg-type]


def _lineage(instrument_id: int = 101) -> MarketLineage:
    return MarketLineage(
        source="databento:GLBX.MDP3:trades",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=instrument_id,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        market_data_schema="market-data/v1",
    )


_BASE_NS = _ns("2026-07-24T20:00:00")


def _at(value: int) -> int:
    return value if value > _BASE_NS // 2 else _BASE_NS + value


def _signal(
    *,
    direction: Direction = Direction.LONG,
    signal_type: SignalType = SignalType.SCALP,
    signal_ts_ns: int = 100,
    lineage: MarketLineage | None = None,
) -> SignalRecord:
    entry, stop, target = (100, 96, 106) if direction is Direction.LONG else (100, 104, 94)
    return SignalRecord(
        signal_type=signal_type,
        direction=direction,
        entry_ticks=entry,
        stop_ticks=stop,
        target_ticks=target,
        risk_reward=RationalR(3, 2),
        setup_type=SetupType.BREAK_AND_RETEST,
        entry_model="private-neutral-mechanics-fixture",
        confidence=73,
        signal_ts_ns=_at(signal_ts_ns),
        source="test",
        release_file_sha256="c" * 64,
        rulebook_version="test",
        rule_id=f"fixture-{direction.value}-{signal_type.value}",
        engine_version="test",
        lineage=lineage or _lineage(),
        causal_bar_ids=("d" * 64,),
    )


def _bar(
    *,
    end_ns: int,
    open_ticks: int = 100,
    high_ticks: int = 104,
    low_ticks: int = 98,
    close_ticks: int | None = None,
    lineage: MarketLineage | None = None,
    quality: QualityState = QualityState.COMPLETE,
    timeframe: Timeframe = Timeframe.ONE_MINUTE,
) -> FinalBar:
    current = lineage or _lineage()
    end_ns = _at(end_ns)
    if close_ticks is None:
        close_ticks = min(max(open_ticks, low_ticks), high_ticks)
    return FinalBar(
        source=current.source,
        instrument=InstrumentSpec(current.root, current.continuous_symbol),
        instrument_id=current.instrument_id,
        timeframe=timeframe,
        calendar_fingerprint=current.calendar_fingerprint,
        aggregation_fingerprint=current.aggregation_fingerprint,
        start_ns=end_ns - 60_000_000_000,
        end_ns=end_ns,
        trading_date=None,
        open_ticks=open_ticks,
        high_ticks=high_ticks,
        low_ticks=low_ticks,
        close_ticks=close_ticks,
        volume=1,
        trade_count=1,
        first_event_ns=end_ns - 50_000_000_000,
        last_event_ns=end_ns - 1,
        quality=quality,
    )


def test_long_short_and_costs_are_exact_and_symmetric() -> None:
    tracker = _OutcomeTracker(_policy())
    long = _signal(direction=Direction.LONG)
    short = _signal(direction=Direction.SHORT)
    tracker.register(long)
    tracker.register(short)
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    update = tracker.observe_bar(_bar(end_ns=180, open_ticks=106, high_ticks=108, low_ticks=105))

    long_trade = next(trade for trade in update.trades if trade.signal == long)
    assert long_trade.state is ObservationState.CLOSED
    assert tuple(fill.kind for fill in long_trade.fills) == (FillKind.ENTRY, FillKind.TARGET)
    assert (long_trade.gross_ticks, long_trade.net_ticks) == (3, 0)
    assert long_trade.gross_r and long_trade.gross_r.numerator == 3
    assert long_trade.net_r and long_trade.net_r.numerator == 0

    tracker = _OutcomeTracker(_policy())
    tracker.register(short)
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    update = tracker.observe_bar(_bar(end_ns=180, open_ticks=94, high_ticks=95, low_ticks=92))
    short_trade = update.trades[0]
    assert (short_trade.gross_ticks, short_trade.net_ticks) == (3, 0)


def test_decision_bar_and_entry_bar_target_are_not_fillable_but_entry_bar_stop_wins() -> None:
    signal = _signal(signal_ts_ns=120)
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    assert tracker.observe_bar(_bar(end_ns=120, high_ticks=110, low_ticks=90)).trades == ()
    opened = tracker.observe_bar(_bar(end_ns=180, high_ticks=110, low_ticks=99))
    assert opened.trades[0].state is ObservationState.OPEN

    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    closed = tracker.observe_bar(_bar(end_ns=180, high_ticks=110, low_ticks=95)).trades[0]
    assert closed.terminal_reason is ObservationReason.STOP
    assert closed.fills[0].event_ts_ns >= signal.signal_ts_ns
    assert closed.fills[0].event_ts_ns == closed.fills[-1].event_ts_ns
    assert closed.fills[0].source_bar_id == closed.fills[-1].source_bar_id


def test_later_tie_and_stop_gap_are_conservative_and_target_gap_has_no_improvement() -> None:
    signal = _signal()
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    tied = tracker.observe_bar(_bar(end_ns=180, high_ticks=107, low_ticks=95)).trades[0]
    assert tied.terminal_reason is ObservationReason.STOP
    assert tied.fills[-1].price_ticks == 94

    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    gapped_stop = tracker.observe_bar(
        _bar(end_ns=180, open_ticks=90, high_ticks=92, low_ticks=89)
    ).trades[0]
    assert gapped_stop.fills[-1].price_ticks == 88

    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    gapped_target = tracker.observe_bar(
        _bar(end_ns=180, open_ticks=110, high_ticks=112, low_ticks=109)
    ).trades[0]
    assert gapped_target.fills[-1].price_ticks == 104


def test_degraded_or_gapped_one_minute_evidence_unresolves_with_typed_warning() -> None:
    signal = _signal()
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    update = tracker.observe_bar(_bar(end_ns=120, quality=QualityState.DEGRADED))
    assert update.trades[0].terminal_reason is ObservationReason.DEGRADED_DATA
    assert update.warnings[0].code is WarningCode.DEGRADED_DATA

    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    bar = _bar(end_ns=120)
    gap = CoverageGap(signal.lineage, Timeframe.ONE_MINUTE, bar.start_ns, bar.end_ns, "source gap")
    update = tracker.observe_bar(bar, gaps=(gap,))
    assert update.trades[0].terminal_reason is ObservationReason.COVERAGE_GAP
    assert update.warnings[0].code is WarningCode.COVERAGE_GAP


@pytest.mark.parametrize(
    ("stamp", "cutoff"),
    [
        ("2026-03-08T20:58:00", "2026-03-08T13:58:00-07:00"),
        ("2026-11-01T21:58:00", "2026-11-01T13:58:00-08:00"),
    ],
)
def test_cutoff_uses_pacific_wall_clock_through_dst(stamp: str, cutoff: str) -> None:
    cutoff_ns = _ns(stamp)
    assert (
        datetime.fromtimestamp(cutoff_ns / 1_000_000_000, UTC)
        .astimezone(ZoneInfo("America/Los_Angeles"))
        .isoformat()
        == cutoff
    )
    signal = _signal(signal_ts_ns=cutoff_ns - 120_000_000_000)
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=cutoff_ns - 60_000_000_000, high_ticks=101, low_ticks=99))
    cutoff_bar = _bar(end_ns=cutoff_ns, close_ticks=102, high_ticks=103, low_ticks=99)
    update = tracker.observe_bar(cutoff_bar)
    assert update.trades[0].terminal_reason is ObservationReason.SESSION_FLATTEN
    assert update.trades[0].fills[-1].source_bar_id == cutoff_bar.identity


def test_cutoff_bar_preserves_stop_first_conservative_outcome_ordering() -> None:
    cutoff_ns = _ns("2026-07-24T20:58:00")
    signal = _signal(signal_ts_ns=cutoff_ns - 120_000_000_000)
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=cutoff_ns - 60_000_000_000, high_ticks=101, low_ticks=99))

    update = tracker.observe_bar(
        _bar(end_ns=cutoff_ns, open_ticks=100, high_ticks=107, low_ticks=95)
    )

    assert update.trades[0].terminal_reason is ObservationReason.STOP
    assert update.trades[0].fills[-1].kind is FillKind.STOP


def test_watermark_past_an_absent_cutoff_bar_unresolves_with_typed_warning() -> None:
    cutoff_ns = _ns("2026-07-24T20:58:00")
    signal = _signal(signal_ts_ns=cutoff_ns - 120_000_000_000)
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)

    update = tracker.observe_watermark(signal.lineage, cutoff_ns + 1)

    assert update.trades[0].terminal_reason is ObservationReason.MISSING_CUTOFF_BAR
    assert update.warnings[0].code is WarningCode.MISSING_CUTOFF_BAR


def test_pending_and_after_cutoff_are_unresolved_position_is_exempt_and_roll_is_unresolved() -> (
    None
):
    cutoff_ns = _ns("2026-07-24T20:58:00")
    pending = _signal(signal_ts_ns=cutoff_ns - 60_000_000_000)
    tracker = _OutcomeTracker(_policy())
    tracker.register(pending)
    update = tracker.observe_bar(
        _bar(end_ns=cutoff_ns, open_ticks=99, high_ticks=99, low_ticks=98, close_ticks=99)
    )
    assert update.trades[0].terminal_reason is ObservationReason.SESSION_CUTOFF

    after = _signal(signal_ts_ns=cutoff_ns)
    update = tracker.register(after)
    assert update.trades[0].terminal_reason is ObservationReason.SESSION_CUTOFF

    position = _signal(signal_type=SignalType.POSITION, signal_ts_ns=cutoff_ns - 120_000_000_000)
    tracker = _OutcomeTracker(_policy())
    tracker.register(position)
    tracker.observe_bar(_bar(end_ns=cutoff_ns - 60_000_000_000, high_ticks=101, low_ticks=99))
    assert tracker.observe_bar(_bar(end_ns=cutoff_ns)).trades == ()
    assert tracker.trade_records[0].state is ObservationState.OPEN
    assert (
        tracker.retire_lineage(position.lineage).trades[0].terminal_reason
        is ObservationReason.CONTRACT_ROLL
    )


def test_duplicates_are_idempotent_and_active_lineage_and_output_bounds_fail_closed() -> None:
    policy = _policy(max_active_observations=1, max_active_lineages=1, max_output_records=2)
    tracker = _OutcomeTracker(policy)
    signal = _signal()
    assert tracker.register(signal).trades[0].state is ObservationState.PENDING
    assert tracker.register(signal).trades == ()
    with pytest.raises(BacktestValidationError, match="max_active_observations"):
        tracker.register(replace(signal, rule_id="distinct"))
    tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    assert tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99)).trades == ()
    with pytest.raises(BacktestValidationError, match="max_output_records"):
        tracker.observe_bar(_bar(end_ns=180, high_ticks=107, low_ticks=99))

    lineage_bound = _OutcomeTracker(_policy(max_active_observations=2, max_active_lineages=1))
    lineage_bound.register(signal)
    with pytest.raises(BacktestValidationError, match="max_active_lineages"):
        lineage_bound.register(replace(signal, lineage=_lineage(102), rule_id="other-lineage"))

    gap_bound = _OutcomeTracker(_policy(max_retained_gaps=1))
    first_gap = CoverageGap(signal.lineage, Timeframe.ONE_MINUTE, _BASE_NS, _BASE_NS + 10, "one")
    second_gap = CoverageGap(
        signal.lineage, Timeframe.ONE_MINUTE, _BASE_NS + 20, _BASE_NS + 30, "two"
    )
    gap_bound.observe_gap(first_gap)
    with pytest.raises(BacktestValidationError, match="max_retained_gaps"):
        gap_bound.observe_gap(second_gap)


def test_exact_lineage_isolated_and_end_or_fold_boundaries_unresolve() -> None:
    signal = _signal()
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    tracker.observe_bar(_bar(end_ns=120, lineage=_lineage(102), high_ticks=110, low_ticks=90))
    assert tracker.trade_records[0].state is ObservationState.PENDING
    assert tracker.finish().trades[0].terminal_reason is ObservationReason.END_OF_DATA

    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    assert (
        tracker.finish(ObservationReason.FOLD_END).trades[0].terminal_reason
        is ObservationReason.FOLD_END
    )


def test_non_one_minute_bars_cannot_change_outcome_state_or_replay_watermark() -> None:
    signal = _signal()
    tracker = _OutcomeTracker(_policy())
    tracker.register(signal)
    assert (
        tracker.observe_bar(
            _bar(
                end_ns=180,
                high_ticks=110,
                low_ticks=90,
                timeframe=Timeframe.FIVE_MINUTES,
            )
        ).trades
        == ()
    )
    opened = tracker.observe_bar(_bar(end_ns=120, high_ticks=101, low_ticks=99))
    assert opened.trades[0].state is ObservationState.OPEN
