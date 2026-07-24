"""Chronological replay contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

import stoic_derived.backtest.runner as runner_module
from stoic_derived.backtest.chronological_replay import run_chronological_replay
from stoic_derived.backtest.model import (
    BacktestStatus,
    ChronologicalReplayFold,
    ChronologicalReplayPlan,
    HalfOpenInterval,
    ObservationReason,
    SimulationPolicy,
)
from stoic_derived.market_data.model import FinalBar, InstrumentSpec, Timeframe
from stoic_derived.signal_engine import (
    EngineCreation,
    FinalizedSeriesBatch,
    MarketLineage,
    SignalEngine,
)
from stoic_derived.signal_engine.compiler import (
    CompilationReadiness,
    _strategy_neutral_test_program,
)
from stoic_derived.signal_engine.model import TIMEFRAME_PLANS, Role, SetupType, SignalType


def _policy() -> SimulationPolicy:
    return SimulationPolicy(
        entry_slippage_ticks=0,
        exit_slippage_ticks=0,
        fees_ticks_round_turn=0,
        zero_costs_declared=True,
        max_active_observations=4,
        max_active_lineages=2,
        max_retained_gaps=4,
        max_accepted_batches=4,
        max_output_records=32,
        max_artifact_bytes=4096,
    )


def test_blocked_release_remains_blocked_for_each_fresh_chronological_fold() -> None:
    fold = ChronologicalReplayFold(
        "fold-1",
        HalfOpenInterval(0, 10),
        HalfOpenInterval(10, 20),
        HalfOpenInterval(20, 30),
        HalfOpenInterval(30, 40),
    )
    results = run_chronological_replay(
        None, None, None, (), _policy(), ChronologicalReplayPlan((fold,))
    )

    assert len(results) == 1
    assert results[0].status is BacktestStatus.BLOCKED
    assert not results[0].trades


_BASE_NS = 1_784_923_200_000_000_000


def _batch(end_ns: int, *, only_one_minute: bool = False) -> FinalizedSeriesBatch:
    lineage = MarketLineage(
        source="market-test",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=101,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="a" * 64,
        market_data_schema="market-data/v1",
    )
    timeframes = (
        (Timeframe.ONE_MINUTE,)
        if only_one_minute
        else tuple(TIMEFRAME_PLANS[SignalType.SCALP].for_role(role) for role in Role)
    )
    bars = tuple(
        FinalBar(
            source=lineage.source,
            instrument=InstrumentSpec("NQ", "NQ.c.0"),
            instrument_id=lineage.instrument_id,
            timeframe=timeframe,
            calendar_fingerprint=lineage.calendar_fingerprint,
            aggregation_fingerprint=lineage.aggregation_fingerprint,
            start_ns=end_ns - (timeframe.duration_ns or 1),
            end_ns=end_ns,
            trading_date=None,
            open_ticks=2,
            high_ticks=2,
            low_ticks=2,
            close_ticks=2,
            volume=1,
            trade_count=1,
            first_event_ns=end_ns - (timeframe.duration_ns or 1),
            last_event_ns=end_ns - 1,
        )
        for timeframe in timeframes
    )
    return FinalizedSeriesBatch(lineage, end_ns + 1, bars)


def _ready_engine() -> SignalEngine:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )
    return SignalEngine._from_program_for_test(program)


def test_folds_use_fresh_public_composition_and_admit_only_evaluation_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = 0

    def create_ready(*_args: object) -> EngineCreation:
        nonlocal created
        created += 1
        engine = _ready_engine()
        return EngineCreation(engine, engine.program, CompilationReadiness(True, ()))

    monkeypatch.setattr(runner_module.SignalEngine, "from_release", create_ready)
    first = ChronologicalReplayFold(
        "first",
        HalfOpenInterval(_BASE_NS - 100, _BASE_NS - 80),
        HalfOpenInterval(_BASE_NS - 80, _BASE_NS - 60),
        HalfOpenInterval(_BASE_NS - 60, _BASE_NS),
        HalfOpenInterval(_BASE_NS, _BASE_NS + 120_000_000_000),
    )
    second = ChronologicalReplayFold(
        "second",
        HalfOpenInterval(_BASE_NS + 120_000_000_000, _BASE_NS + 120_000_000_020),
        HalfOpenInterval(_BASE_NS + 120_000_000_020, _BASE_NS + 120_000_000_040),
        HalfOpenInterval(_BASE_NS + 120_000_000_040, _BASE_NS + 180_000_000_000),
        HalfOpenInterval(_BASE_NS + 180_000_000_000, _BASE_NS + 300_000_000_000),
    )
    results = run_chronological_replay(
        None,
        None,
        None,
        (
            _batch(_BASE_NS),
            _batch(_BASE_NS + 60_000_000_000, only_one_minute=True),
            _batch(_BASE_NS + 180_000_000_000),
            _batch(_BASE_NS + 240_000_000_000, only_one_minute=True),
        ),
        _policy(),
        ChronologicalReplayPlan((first, second)),
    )

    assert created == 2
    for fold, result in zip((first, second), results, strict=True):
        assert result.status is BacktestStatus.COMPLETE
        assert all(
            fold.evaluation.start_ns <= signal.signal_ts_ns < fold.evaluation.end_ns
            for signal in result.signals
        )
        assert all(trade.terminal_reason is ObservationReason.FOLD_END for trade in result.trades)
