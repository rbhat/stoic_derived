"""Exact, observational SP3 metric tests."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from stoic_derived.backtest.metrics import build_equity, build_exclusions, build_metrics
from stoic_derived.backtest.model import (
    ExactR,
    ExclusionMetric,
    FillKind,
    MetricRecord,
    MetricScope,
    ObservationReason,
    ObservationState,
    SimulatedFillRecord,
    SimulationPolicy,
    TradeRecord,
    WarningCode,
)
from stoic_derived.signal_engine.model import (
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
    Suppression,
    SuppressionCode,
)


def _policy() -> SimulationPolicy:
    return SimulationPolicy(
        entry_slippage_ticks=0,
        exit_slippage_ticks=0,
        fees_ticks_round_turn=0,
        zero_costs_declared=True,
        max_active_observations=10,
        max_active_lineages=10,
        max_retained_gaps=10,
        max_accepted_batches=10,
        max_output_records=100,
        max_artifact_bytes=10_000,
    )


def _lineage(*, root: str = "NQ", instrument_id: int = 101) -> MarketLineage:
    return MarketLineage(
        source="databento:GLBX.MDP3:trades",
        root=root,
        continuous_symbol=f"{root}.c.0",
        instrument_id=instrument_id,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        market_data_schema="market-data/v1",
    )


def _trade(
    *,
    net_ticks: int,
    exit_ts_ns: int,
    root: str = "NQ",
    instrument_id: int = 101,
    direction: Direction = Direction.LONG,
    signal_type: SignalType = SignalType.SCALP,
    setup_type: SetupType = SetupType.BREAK_AND_RETEST,
) -> TradeRecord:
    signal = SignalRecord(
        signal_type=signal_type,
        direction=direction,
        entry_ticks=100,
        stop_ticks=96 if direction is Direction.LONG else 104,
        target_ticks=106 if direction is Direction.LONG else 94,
        risk_reward=RationalR(3, 2),
        setup_type=setup_type,
        entry_model="sbs_model_1",
        confidence=80,
        signal_ts_ns=exit_ts_ns - 2,
        source="signal-engine",
        release_file_sha256="c" * 64,
        rulebook_version="1.0.0",
        rule_id=f"rule-{exit_ts_ns}-{instrument_id}-{net_ticks}",
        engine_version="signal-engine/v1",
        lineage=_lineage(root=root, instrument_id=instrument_id),
        causal_bar_ids=("d" * 64,),
    )
    policy = _policy()
    entry = SimulatedFillRecord(
        signal_id=signal.signal_id,
        kind=FillKind.ENTRY,
        price_ticks=100,
        event_ts_ns=signal.signal_ts_ns + 1,
        policy_id=policy.policy_id,
        source_bar_id="e" * 64,
    )
    exit_kind = FillKind.TARGET if net_ticks >= 0 else FillKind.STOP
    exit_fill = SimulatedFillRecord(
        signal_id=signal.signal_id,
        kind=exit_kind,
        price_ticks=100 + net_ticks if direction is Direction.LONG else 100 - net_ticks,
        event_ts_ns=exit_ts_ns,
        policy_id=policy.policy_id,
        source_bar_id="f" * 64,
    )
    return TradeRecord(
        signal=signal,
        policy_id=policy.policy_id,
        fees_ticks_round_turn=0,
        state=ObservationState.CLOSED,
        fills=(entry, exit_fill),
        gross_ticks=net_ticks,
        net_ticks=net_ticks,
        gross_r=ExactR.from_fraction(Fraction(net_ticks, 4)),
        net_r=ExactR.from_fraction(Fraction(net_ticks, 4)),
        terminal_reason=(
            ObservationReason.TARGET if exit_kind is FillKind.TARGET else ObservationReason.STOP
        ),
    )


def _state(trade: TradeRecord, state: ObservationState) -> TradeRecord:
    if state is ObservationState.PENDING:
        return replace(
            trade,
            state=state,
            fills=(),
            gross_ticks=None,
            net_ticks=None,
            gross_r=None,
            net_r=None,
            terminal_reason=None,
        )
    if state is ObservationState.OPEN:
        return replace(
            trade,
            state=state,
            fills=trade.fills[:1],
            gross_ticks=None,
            net_ticks=None,
            gross_r=None,
            net_r=None,
            terminal_reason=None,
        )
    return replace(
        trade,
        state=state,
        fills=trade.fills[:1],
        gross_ticks=None,
        net_ticks=None,
        gross_r=None,
        net_r=None,
        terminal_reason=ObservationReason.END_OF_DATA,
    )


def _physical(records: tuple[MetricRecord, ...]) -> MetricRecord:
    return next(record for record in records if record.group.scope is MetricScope.PHYSICAL_CONTRACT)


def test_closed_metrics_reconcile_exact_r_and_drawdown_from_closed_observations() -> None:
    trades = (
        _trade(net_ticks=8, exit_ts_ns=10),
        _trade(net_ticks=-12, exit_ts_ns=20),
        _trade(net_ticks=0, exit_ts_ns=30),
        _state(_trade(net_ticks=4, exit_ts_ns=40), ObservationState.PENDING),
        _state(_trade(net_ticks=4, exit_ts_ns=50), ObservationState.OPEN),
        _state(_trade(net_ticks=4, exit_ts_ns=60), ObservationState.UNRESOLVED),
    )

    metric = _physical(build_metrics(trades))

    assert metric.closed_count == 3
    assert metric.pending_count == 1
    assert metric.open_count == 1
    assert metric.unresolved_count == 1
    assert metric.win_count == 1
    assert metric.win_rate == ExactR(1, 3)
    assert metric.expectancy_r == ExactR(-1, 3)
    assert metric.average_win_r == ExactR(2, 1)
    assert metric.average_loss_r == ExactR(-3, 1)
    assert metric.maximum_drawdown_r == ExactR(3, 1)
    assert metric.maximum_drawdown_ticks == 12
    assert metric.warning_codes == (WarningCode.INSUFFICIENT_SAMPLE,)


def test_equity_uses_exit_then_trade_identity_and_is_independent_of_input_order() -> None:
    winner = _trade(net_ticks=8, exit_ts_ns=20)
    loser = _trade(net_ticks=-12, exit_ts_ns=20, instrument_id=102)
    late = _trade(net_ticks=4, exit_ts_ns=30)

    first = build_equity((late, loser, winner))
    second = build_equity((winner, late, loser))

    assert first == second
    assert [(point.exit_ts_ns, point.trade_id) for point in first] == sorted(
        (point.exit_ts_ns, point.trade_id) for point in first
    )
    assert first[-1].cumulative_net_ticks == 0
    assert first[-1].cumulative_net_r == ExactR(0, 1)


def test_contract_partitions_stay_isolated_and_root_summary_retains_contract_count() -> None:
    first = _trade(net_ticks=4, exit_ts_ns=10, instrument_id=101)
    second = _trade(net_ticks=-4, exit_ts_ns=20, instrument_id=102)
    es = _trade(net_ticks=8, exit_ts_ns=30, root="ES", instrument_id=201)

    metrics = build_metrics((first, second, es))
    nq_root = next(
        metric
        for metric in metrics
        if metric.group.scope is MetricScope.ROOT_SUMMARY and metric.group.root == "NQ"
    )
    nq_contracts = [
        metric
        for metric in metrics
        if metric.group.scope is MetricScope.PHYSICAL_CONTRACT and metric.group.root == "NQ"
    ]

    assert nq_root.group.instrument_id is None
    assert nq_root.contract_count == 2
    assert nq_root.closed_count == 2
    assert nq_root.expectancy_r == ExactR(0, 1)
    assert {metric.group.instrument_id for metric in nq_contracts} == {101, 102}
    assert all(metric.contract_count == 1 for metric in nq_contracts)
    assert all(WarningCode.MULTIPLE_COMPARISONS in metric.warning_codes for metric in metrics)


def test_exactly_thirty_closed_observations_clear_only_the_small_sample_warning() -> None:
    metrics = build_metrics(
        tuple(_trade(net_ticks=4, exit_ts_ns=10 + index * 3) for index in range(30))
    )

    assert all(metric.closed_count == 30 for metric in metrics)
    assert all(WarningCode.INSUFFICIENT_SAMPLE not in metric.warning_codes for metric in metrics)
    assert all(WarningCode.MULTIPLE_COMPARISONS not in metric.warning_codes for metric in metrics)


def test_empty_input_has_no_metric_population_and_suppressions_are_separate_exclusions() -> None:
    assert build_metrics(()) == ()
    suppression = Suppression(
        code=SuppressionCode.PREDICATE_NOT_MATCHED,
        detail="no complete partition identity",
        source="signal-engine",
        release_file_sha256="c" * 64,
        rulebook_version="1.0.0",
        engine_version="signal-engine/v1",
        signal_type=SignalType.SCALP,
        lineage=_lineage(),
    )

    exclusions = build_exclusions((suppression, suppression))

    assert len(exclusions) == 1
    assert exclusions[0].group.code is SuppressionCode.PREDICATE_NOT_MATCHED
    assert exclusions[0].group.root == "NQ"
    assert exclusions[0].group.instrument_id == 101
    assert exclusions[0].group.signal_type is SignalType.SCALP
    assert exclusions[0].count == 2


def test_exclusions_distinguish_exact_available_suppression_provenance() -> None:
    lineage_free = Suppression(
        code=SuppressionCode.RELEASE_UNAVAILABLE,
        detail="release unavailable",
        source="signal-engine",
        release_file_sha256="c" * 64,
        rulebook_version="1.0.0",
        engine_version="signal-engine/v1",
    )
    lineage_bound = replace(
        lineage_free,
        code=SuppressionCode.COVERAGE_GAP,
        detail="coverage gap",
        lineage=_lineage(root="ES", instrument_id=201),
        signal_type=SignalType.DAY,
    )

    exclusions = build_exclusions((lineage_bound, lineage_free))

    assert all(isinstance(exclusion, ExclusionMetric) for exclusion in exclusions)
    assert {(item.group.root, item.group.instrument_id) for item in exclusions} == {
        (None, None),
        ("ES", 201),
    }
