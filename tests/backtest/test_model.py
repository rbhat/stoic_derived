"""SP3 immutable, research-only contract tests."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from stoic_derived.backtest.model import (
    BacktestResult,
    BacktestStatus,
    BacktestValidationError,
    ChronologicalReplayFold,
    ChronologicalReplayPlan,
    EvidenceClass,
    ExactR,
    FillKind,
    HalfOpenInterval,
    ObservationReason,
    ObservationState,
    SimulatedFillRecord,
    SimulationPolicy,
    TradeRecord,
)
from stoic_derived.signal_engine.model import (
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
)


def _lineage() -> MarketLineage:
    return MarketLineage(
        source="databento:GLBX.MDP3:trades",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=101,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        market_data_schema="market-data/v1",
    )


def _signal() -> SignalRecord:
    return SignalRecord(
        signal_type=SignalType.SCALP,
        direction=Direction.LONG,
        entry_ticks=80_000,
        stop_ticks=79_996,
        target_ticks=80_006,
        risk_reward=RationalR(3, 2),
        setup_type=SetupType.BREAK_AND_RETEST,
        entry_model="sbs_model_1",
        confidence=73,
        signal_ts_ns=100,
        source="signal-engine",
        release_file_sha256="c" * 64,
        rulebook_version="1.2.3",
        rule_id="retest-long-v1",
        engine_version="1.0.0",
        lineage=_lineage(),
        causal_bar_ids=("a" * 64,),
    )


def _policy() -> SimulationPolicy:
    return SimulationPolicy(
        entry_slippage_ticks=1,
        exit_slippage_ticks=2,
        fees_ticks_round_turn=3,
        zero_costs_declared=False,
        max_active_observations=4,
        max_active_lineages=2,
        max_retained_gaps=8,
        max_accepted_batches=16,
        max_output_records=32,
        max_artifact_bytes=4_096,
    )


def test_policy_is_immutable_canonical_content_addressed_and_never_implicitly_free() -> None:
    policy = _policy()

    assert policy.policy_id == SimulationPolicy(**policy.init_dict()).policy_id
    assert policy.canonical_bytes() == SimulationPolicy(**policy.init_dict()).canonical_bytes()
    assert policy.canonical_bytes() == (
        b'{"entry_slippage_ticks":1,"exit_slippage_ticks":2,"fees_ticks_round_turn":3,'
        b'"max_accepted_batches":16,"max_active_lineages":2,"max_active_observations":4,'
        b'"max_artifact_bytes":4096,"max_output_records":32,"max_retained_gaps":8,'
        b'"policy_id":"2bead73dd25fcf8480a003b7189d44fc23fad845653230d76ee3345004b54999",'
        b'"schema_version":"backtest/v1",'
        b'"simulator_algorithm_version":"conservative-causal-one-minute/v1",'
        b'"zero_costs_declared":false}'
    )
    with pytest.raises(AttributeError):
        policy.entry_slippage_ticks = 0  # type: ignore[misc]
    with pytest.raises(BacktestValidationError, match="zero-costs declaration"):
        replace(policy, entry_slippage_ticks=0, exit_slippage_ticks=0, fees_ticks_round_turn=0)
    zero = replace(
        policy,
        entry_slippage_ticks=0,
        exit_slippage_ticks=0,
        fees_ticks_round_turn=0,
        zero_costs_declared=True,
    )
    assert zero.zero_costs_declared is True
    with pytest.raises(BacktestValidationError, match="zero-costs declaration"):
        replace(policy, zero_costs_declared=True)


@pytest.mark.parametrize("bad", [True, 1.0, -1])
def test_policy_rejects_boolean_float_and_negative_cost_or_bound_values(bad: object) -> None:
    with pytest.raises(BacktestValidationError):
        replace(_policy(), entry_slippage_ticks=bad)  # type: ignore[arg-type]
    with pytest.raises(BacktestValidationError):
        replace(_policy(), max_output_records=bad)  # type: ignore[arg-type]


def test_signed_r_is_exact_reduced_and_accepts_losses_and_zero_without_floats() -> None:
    assert ExactR.from_fraction(Fraction(-6, 8)) == ExactR(-3, 4)
    assert ExactR(0, 7).canonical_dict() == {"decimal": "0", "denominator": 1, "numerator": 0}
    assert ExactR(-1, 8).decimal_string == "-0.125"
    with pytest.raises(BacktestValidationError, match="reduced"):
        ExactR(2, 4)
    with pytest.raises(BacktestValidationError, match="integer"):
        ExactR(1.0, 1)  # type: ignore[arg-type]


def test_fill_and_trade_require_a_legal_lifecycle_and_exact_accounting() -> None:
    signal = _signal()
    policy = _policy()
    entry = SimulatedFillRecord(
        signal_id=signal.signal_id,
        kind=FillKind.ENTRY,
        price_ticks=80_001,
        event_ts_ns=101,
        policy_id=policy.policy_id,
        source_bar_id="d" * 64,
    )
    stop = SimulatedFillRecord(
        signal_id=signal.signal_id,
        kind=FillKind.STOP,
        price_ticks=79_994,
        event_ts_ns=102,
        policy_id=policy.policy_id,
        source_bar_id="e" * 64,
    )
    closed = TradeRecord(
        signal=signal,
        policy_id=policy.policy_id,
        fees_ticks_round_turn=policy.fees_ticks_round_turn,
        state=ObservationState.CLOSED,
        fills=(entry, stop),
        gross_ticks=-7,
        net_ticks=-10,
        gross_r=ExactR(-7, 4),
        net_r=ExactR(-5, 2),
        terminal_reason=ObservationReason.STOP,
    )

    assert closed.trade_id == TradeRecord(**closed.init_dict()).trade_id
    assert closed.canonical_dict()["signal"]["signal_id"] == signal.signal_id
    with pytest.raises(BacktestValidationError, match="pending"):
        TradeRecord(
            signal=signal,
            policy_id=policy.policy_id,
            fees_ticks_round_turn=policy.fees_ticks_round_turn,
            state=ObservationState.PENDING,
            fills=(entry,),
        )
    with pytest.raises(BacktestValidationError, match="closed trade"):
        replace(closed, net_ticks=-9)
    with pytest.raises(BacktestValidationError, match="fees exactly once"):
        replace(closed, fees_ticks_round_turn=2)
    with pytest.raises(BacktestValidationError, match="research-only"):
        replace(entry, research_only=False)


def test_chronological_folds_are_half_open_and_evaluations_cannot_leak() -> None:
    fold_one = ChronologicalReplayFold(
        fold_id="first",
        warmup=HalfOpenInterval(0, 10),
        context=HalfOpenInterval(10, 20),
        embargo=HalfOpenInterval(20, 25),
        evaluation=HalfOpenInterval(25, 30),
    )
    fold_two = ChronologicalReplayFold(
        fold_id="second",
        warmup=HalfOpenInterval(20, 30),
        context=HalfOpenInterval(30, 40),
        embargo=HalfOpenInterval(40, 45),
        evaluation=HalfOpenInterval(45, 50),
    )
    plan = ChronologicalReplayPlan((fold_one, fold_two))

    assert plan.evidence_class is EvidenceClass.RETROSPECTIVE_REPLAY
    assert plan.plan_id == ChronologicalReplayPlan((fold_one, fold_two)).plan_id
    with pytest.raises(BacktestValidationError, match="chronological"):
        replace(fold_one, context=HalfOpenInterval(9, 20))
    with pytest.raises(BacktestValidationError, match="overlap"):
        ChronologicalReplayPlan((fold_one, replace(fold_two, evaluation=HalfOpenInterval(29, 50))))


def test_blocked_result_is_nonexecuting_and_has_zero_trade_population() -> None:
    result = BacktestResult.blocked(
        evidence_class=EvidenceClass.RETROSPECTIVE_REPLAY,
        plan_id="f" * 64,
        readiness_blockers=("signed_release_unavailable",),
    )

    assert result.status is BacktestStatus.BLOCKED
    assert result.execution is False
    assert result.orders_placed == 0
    assert result.trades == ()
    with pytest.raises(BacktestValidationError, match="trades"):
        replace(result, trades=(object(),))  # type: ignore[arg-type]
    with pytest.raises(BacktestValidationError, match="orders_placed"):
        replace(result, orders_placed=1)
