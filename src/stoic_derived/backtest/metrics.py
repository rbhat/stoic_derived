"""Exact descriptive metrics for immutable research observations.

This module only summarizes final simulated observations.  It has no release,
engine, strategy, broker, or order-routing dependency, and its output is never
a live-readiness decision.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction

from stoic_derived.backtest.model import (
    EquityPoint,
    ExactR,
    ExclusionGroup,
    ExclusionMetric,
    MetricGroup,
    MetricRecord,
    MetricScope,
    ObservationState,
    TradeRecord,
    WarningCode,
)
from stoic_derived.signal_engine.model import Suppression


class MetricsError(ValueError):
    """Raised when a claimed final observation population is internally unsafe."""


def build_equity(trades: Iterable[TradeRecord]) -> tuple[EquityPoint, ...]:
    """Return global closed-observation equity ordered by exit then trade identity."""
    observations = _normalize_trades(trades)
    closed = _closed_in_equity_order(observations)
    cumulative_ticks = 0
    cumulative_r = Fraction()
    points: list[EquityPoint] = []
    for trade in closed:
        assert trade.exit_ts_ns is not None
        assert trade.net_ticks is not None
        assert trade.net_r is not None
        cumulative_ticks += trade.net_ticks
        cumulative_r += trade.net_r.fraction
        points.append(
            EquityPoint(
                trade_id=trade.trade_id,
                exit_ts_ns=trade.exit_ts_ns,
                cumulative_net_ticks=cumulative_ticks,
                cumulative_net_r=ExactR.from_fraction(cumulative_r),
            )
        )
    return tuple(points)


def build_metrics(trades: Iterable[TradeRecord]) -> tuple[MetricRecord, ...]:
    """Summarize all lifecycle states in physical and logical-root partitions.

    A root summary combines only physical contracts of its same root, signal
    type, fixed execute timeframe, direction, and setup.  Suppressions are
    intentionally excluded from this trade population; use ``build_exclusions``
    to summarize only the provenance SP2 actually recorded for them.
    """
    observations = _normalize_trades(trades)
    groups: dict[MetricGroup, list[TradeRecord]] = defaultdict(list)
    physical_groups: set[MetricGroup] = set()
    for trade in observations:
        physical, root = _groups_for_trade(trade)
        groups[physical].append(trade)
        groups[root].append(trade)
        physical_groups.add(physical)

    has_multiple_partitions = len(physical_groups) > 1
    records = tuple(
        _build_metric(group, group_trades, has_multiple_partitions)
        for group, group_trades in groups.items()
    )
    return tuple(sorted(records, key=lambda record: record.metric_id))


def compute_metrics(trades: Iterable[TradeRecord]) -> tuple[MetricRecord, ...]:
    """Compatibility name for exact trade-observation metric construction."""
    return build_metrics(trades)


def build_exclusions(suppressions: Iterable[Suppression]) -> tuple[ExclusionMetric, ...]:
    """Count SP2 suppressions without inferring unavailable strategy attributes."""
    grouped: dict[ExclusionGroup, int] = defaultdict(int)
    for suppression in suppressions:
        if not isinstance(suppression, Suppression):
            raise MetricsError("suppressions must contain Suppression values")
        lineage = suppression.lineage
        group = ExclusionGroup(
            code=suppression.code,
            root=lineage.root if lineage else None,
            instrument_id=lineage.instrument_id if lineage else None,
            signal_type=suppression.signal_type,
        )
        grouped[group] += 1
    records = tuple(ExclusionMetric(group=group, count=count) for group, count in grouped.items())
    return tuple(sorted(records, key=lambda record: record.exclusion_id))


def _normalize_trades(trades: Iterable[TradeRecord]) -> tuple[TradeRecord, ...]:
    observations = tuple(trades)
    if any(not isinstance(trade, TradeRecord) for trade in observations):
        raise MetricsError("trades must contain TradeRecord values")
    trade_ids = tuple(trade.trade_id for trade in observations)
    if len(set(trade_ids)) != len(trade_ids):
        raise MetricsError("trades must not contain duplicate trade_id values")
    signal_ids = tuple(trade.signal.signal_id for trade in observations)
    if len(set(signal_ids)) != len(signal_ids):
        raise MetricsError("trades must not contain duplicate signal observations")
    return observations


def _groups_for_trade(trade: TradeRecord) -> tuple[MetricGroup, MetricGroup]:
    signal = trade.signal
    return (
        MetricGroup(
            scope=MetricScope.PHYSICAL_CONTRACT,
            root=trade.lineage.root,
            instrument_id=trade.lineage.instrument_id,
            signal_type=signal.signal_type,
            execute_timeframe=signal.timeframe_plan.execute,
            direction=signal.direction,
            setup_type=signal.setup_type,
        ),
        MetricGroup(
            scope=MetricScope.ROOT_SUMMARY,
            root=trade.lineage.root,
            instrument_id=None,
            signal_type=signal.signal_type,
            execute_timeframe=signal.timeframe_plan.execute,
            direction=signal.direction,
            setup_type=signal.setup_type,
        ),
    )


def _build_metric(
    group: MetricGroup, trades: list[TradeRecord], has_multiple_partitions: bool
) -> MetricRecord:
    closed = _closed_in_equity_order(trades)
    net_r_values = _closed_net_r(closed)
    win_r_values = tuple(value for value in net_r_values if value > 0)
    loss_r_values = tuple(value for value in net_r_values if value < 0)
    warning_codes = {WarningCode.INSUFFICIENT_SAMPLE} if len(closed) < 30 else set()
    if has_multiple_partitions:
        warning_codes.add(WarningCode.MULTIPLE_COMPARISONS)
    drawdown_r, drawdown_ticks = _maximum_drawdown(closed)
    return MetricRecord(
        group=group,
        contract_count=len({trade.lineage.instrument_id for trade in trades}),
        closed_count=len(closed),
        pending_count=sum(trade.state is ObservationState.PENDING for trade in trades),
        open_count=sum(trade.state is ObservationState.OPEN for trade in trades),
        unresolved_count=sum(trade.state is ObservationState.UNRESOLVED for trade in trades),
        win_count=len(win_r_values),
        win_rate=(
            ExactR.from_fraction(Fraction(len(win_r_values), len(closed))) if closed else None
        ),
        expectancy_r=_average(net_r_values),
        average_win_r=_average(win_r_values),
        average_loss_r=_average(loss_r_values),
        maximum_drawdown_r=drawdown_r,
        maximum_drawdown_ticks=drawdown_ticks,
        warning_codes=tuple(sorted(warning_codes, key=lambda code: code.value)),
    )


def _closed_in_equity_order(trades: Iterable[TradeRecord]) -> tuple[TradeRecord, ...]:
    closed = tuple(trade for trade in trades if trade.state is ObservationState.CLOSED)
    if any(trade.exit_ts_ns is None for trade in closed):
        raise MetricsError("closed trades must have an exit timestamp")
    return tuple(sorted(closed, key=lambda trade: (trade.exit_ts_ns, trade.trade_id)))


def _closed_net_r(trades: Iterable[TradeRecord]) -> tuple[Fraction, ...]:
    values: list[Fraction] = []
    for trade in trades:
        if trade.net_r is None:
            raise MetricsError("closed trades must have exact net R")
        values.append(trade.net_r.fraction)
    return tuple(values)


def _average(values: tuple[Fraction, ...]) -> ExactR | None:
    if not values:
        return None
    return ExactR.from_fraction(sum(values, Fraction()) / len(values))


def _maximum_drawdown(trades: Iterable[TradeRecord]) -> tuple[ExactR | None, int | None]:
    observations = tuple(trades)
    if not observations:
        return None, None
    cumulative_r = Fraction()
    peak_r = Fraction()
    maximum_r = Fraction()
    cumulative_ticks = 0
    peak_ticks = 0
    maximum_ticks = 0
    for trade in observations:
        if trade.net_r is None or trade.net_ticks is None:
            raise MetricsError("closed trades must have exact net R and net ticks")
        cumulative_r += trade.net_r.fraction
        cumulative_ticks += trade.net_ticks
        peak_r = max(peak_r, cumulative_r)
        peak_ticks = max(peak_ticks, cumulative_ticks)
        maximum_r = max(maximum_r, peak_r - cumulative_r)
        maximum_ticks = max(maximum_ticks, peak_ticks - cumulative_ticks)
    return ExactR.from_fraction(maximum_r), maximum_ticks
