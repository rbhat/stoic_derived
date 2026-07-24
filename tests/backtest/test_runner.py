"""Release-bound runner tests live with the shared SP3 suite."""

from __future__ import annotations

from dataclasses import replace

import pytest

from stoic_derived.backtest.model import (
    BacktestStatus,
    BacktestValidationError,
    EvidenceClass,
    ObservationReason,
    SimulationPolicy,
)
from stoic_derived.backtest.runner import _run_with_engine, run_replay
from stoic_derived.market_data.model import FinalBar, InstrumentSpec, Timeframe
from stoic_derived.signal_engine import FinalizedSeriesBatch, MarketLineage, SignalEngine
from stoic_derived.signal_engine.compiler import _strategy_neutral_test_program
from stoic_derived.signal_engine.model import TIMEFRAME_PLANS, Role, SetupType, SignalType


def _policy() -> SimulationPolicy:
    return SimulationPolicy(
        entry_slippage_ticks=0,
        exit_slippage_ticks=0,
        fees_ticks_round_turn=0,
        zero_costs_declared=True,
        max_active_observations=16,
        max_active_lineages=4,
        max_retained_gaps=4,
        max_accepted_batches=16,
        max_output_records=512,
        max_artifact_bytes=4096,
    )


_BASE_NS = 1_784_923_200_000_000_000


def _batch(
    *,
    end_ns: int = _BASE_NS,
    instrument_id: int = 101,
    only_one_minute: bool = False,
) -> FinalizedSeriesBatch:
    lineage = MarketLineage(
        source="market-test",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=instrument_id,
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
            instrument_id=instrument_id,
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


def _engine() -> SignalEngine:
    program = _strategy_neutral_test_program()
    return SignalEngine._from_program_for_test(
        replace(
            program,
            profiles=tuple(
                replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
                for profile in program.profiles
            ),
        )
    )


def test_blocked_release_is_a_successful_zero_population_result() -> None:
    result = run_replay(None, None, None, (), _policy())

    assert result.status is BacktestStatus.BLOCKED
    assert result.evidence_class is EvidenceClass.RETROSPECTIVE_REPLAY
    assert result.readiness_blockers
    assert not result.signals
    assert not result.trades
    assert not result.metrics


def test_runner_retains_byte_identical_public_engine_decisions_and_future_causality() -> None:
    first = _batch()
    second = _batch(end_ns=_BASE_NS + 60_000_000_000, only_one_minute=True)
    third = _batch(end_ns=_BASE_NS + 120_000_000_000, only_one_minute=True)

    direct = _engine().ingest(first)
    assert direct.signals
    observed = _run_with_engine(
        engine=_engine(),
        batches=(first, second),
        policy=_policy(),
        plan_id="d" * 64,
        terminal_reason=None,
    )
    extended = _run_with_engine(
        engine=_engine(),
        batches=(first, second, third),
        policy=_policy(),
        plan_id="d" * 64,
        terminal_reason=None,
    )

    observed_by_id = {signal.signal_id: signal for signal in observed.signals}
    assert {signal.signal_id for signal in direct.signals} <= set(observed_by_id)
    assert all(
        observed_by_id[signal.signal_id].canonical_bytes() == signal.canonical_bytes()
        for signal in direct.signals
    )
    assert tuple(fill.canonical_bytes() for fill in observed.fills) == tuple(
        fill.canonical_bytes()
        for fill in extended.fills
        if fill.fill_id in {prior.fill_id for prior in observed.fills}
    )


def test_roll_retires_old_root_lineage_before_engine_state_and_rejects_reappearance() -> None:
    first = _batch()
    rolled = _batch(end_ns=_BASE_NS + 120_000_000_000, instrument_id=102)

    result = _run_with_engine(
        engine=_engine(),
        batches=(first, rolled),
        policy=_policy(),
        plan_id="e" * 64,
    )

    assert any(
        trade.lineage.instrument_id == 101
        and trade.terminal_reason is ObservationReason.CONTRACT_ROLL
        for trade in result.trades
    )
    with pytest.raises(BacktestValidationError, match="retired physical lineage reappeared"):
        _run_with_engine(
            engine=_engine(),
            batches=(
                first,
                rolled,
                replace(first, finalized_through_ns=rolled.finalized_through_ns + 1),
            ),
            policy=_policy(),
            plan_id="e" * 64,
        )


def test_runner_uses_committed_watermark_to_detect_an_absent_cutoff_bar() -> None:
    first = _batch()
    cutoff_ns = 1_784_926_680_000_000_000  # 2026-07-24 13:58 America/Los_Angeles
    crossed_cutoff = FinalizedSeriesBatch(first.lineage, cutoff_ns + 1)

    result = _run_with_engine(
        engine=_engine(),
        batches=(first, crossed_cutoff),
        policy=_policy(),
        plan_id="f" * 64,
    )

    assert any(
        trade.terminal_reason is ObservationReason.MISSING_CUTOFF_BAR for trade in result.trades
    )
    assert any(warning.code.value == "missing_cutoff_bar" for warning in result.warnings)


def test_runner_enforces_input_bound_and_does_not_mutate_a_separate_live_engine() -> None:
    first = _batch()
    second = _batch(end_ns=_BASE_NS + 60_000_000_000, only_one_minute=True)
    bounded = replace(_policy(), max_accepted_batches=1)
    with pytest.raises(BacktestValidationError, match="max_accepted_batches"):
        _run_with_engine(
            engine=_engine(), batches=(first, second), policy=bounded, plan_id="f" * 64
        )

    expected = _engine().ingest(first).canonical_bytes()
    live_engine = _engine()
    _run_with_engine(engine=_engine(), batches=(first, second), policy=_policy(), plan_id="f" * 64)
    assert live_engine.ingest(first).canonical_bytes() == expected
