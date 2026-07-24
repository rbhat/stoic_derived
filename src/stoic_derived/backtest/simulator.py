"""Private, conservative mechanics for observational one-minute outcomes.

This module deliberately accepts already-constructed signals only inside SP3.
Release validation and all production composition belong to the runner; no
function here can alter live signal generation or claim to execute an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from stoic_derived.market_data.model import FinalBar, QualityState, Timeframe
from stoic_derived.signal_engine.model import (
    CoverageGap,
    Direction,
    MarketLineage,
    SignalRecord,
    SignalType,
)

from .model import (
    BacktestValidationError,
    ExactR,
    FillKind,
    ObservationReason,
    ObservationState,
    RunWarning,
    SimulatedFillRecord,
    SimulationPolicy,
    TradeRecord,
    WarningCode,
)

_PACIFIC = ZoneInfo("America/Los_Angeles")
_NANOSECONDS_PER_SECOND = 1_000_000_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class TrackerUpdate:
    """The immutable records changed by one private tracker operation."""

    trades: tuple[TradeRecord, ...] = ()
    warnings: tuple[RunWarning, ...] = ()


class _OutcomeTracker:
    """Bounded, idempotent research-only lifecycle tracker.

    It never models an order, broker, portfolio, or position size.  One signal
    corresponds to one independently observed simulated contract.
    """

    def __init__(self, policy: SimulationPolicy) -> None:
        if not isinstance(policy, SimulationPolicy):
            raise BacktestValidationError("policy must be a SimulationPolicy")
        self._policy = policy
        self._trades: dict[str, TradeRecord] = {}
        self._warnings: dict[str, RunWarning] = {}
        self._retained_gap_ids: set[str] = set()
        self._last_bar_end_by_lineage: dict[str, int] = {}
        self._last_bar_ids_by_lineage: dict[str, frozenset[str]] = {}

    @property
    def trade_records(self) -> tuple[TradeRecord, ...]:
        """Return all current lifecycle records in stable signal order."""
        return tuple(self._trades[signal_id] for signal_id in sorted(self._trades))

    @property
    def warnings(self) -> tuple[RunWarning, ...]:
        """Return deduplicated deterministic evidence warnings."""
        return tuple(self._warnings[warning_id] for warning_id in sorted(self._warnings))

    def register(self, signal: SignalRecord) -> TrackerUpdate:
        """Register one constructed internal signal, exactly once by identity."""
        if not isinstance(signal, SignalRecord):
            raise BacktestValidationError("signal must be a SignalRecord")
        existing = self._trades.get(signal.signal_id)
        if existing is not None:
            if existing.signal != signal:
                raise BacktestValidationError("conflicting signal identity")
            return TrackerUpdate()

        self._ensure_output_capacity(1)
        cutoff = _cutoff_at_or_after_signal(signal.signal_ts_ns)
        if signal.signal_type is not SignalType.POSITION and signal.signal_ts_ns >= cutoff:
            warning = self._warning(
                WarningCode.SESSION_CUTOFF,
                "signal was emitted at or after the Pacific session cutoff",
                (signal.signal_id,),
            )
            self._ensure_output_capacity(2)
            trade = self._unresolved(signal, (), ObservationReason.SESSION_CUTOFF)
            self._trades[signal.signal_id] = trade
            return TrackerUpdate((trade,), self._add_warnings((warning,), prechecked=True))

        active = self._active_trades()
        if len(active) >= self._policy.max_active_observations:
            raise BacktestValidationError("max_active_observations bound exceeded")
        active_lineages = {trade.lineage.identity for trade in active}
        if signal.lineage.identity not in active_lineages and (
            len(active_lineages) >= self._policy.max_active_lineages
        ):
            raise BacktestValidationError("max_active_lineages bound exceeded")

        trade = TradeRecord(
            signal=signal,
            policy_id=self._policy.policy_id,
            fees_ticks_round_turn=self._policy.fees_ticks_round_turn,
            state=ObservationState.PENDING,
        )
        self._trades[signal.signal_id] = trade
        return TrackerUpdate((trade,))

    register_signal = register

    def observe_bar(self, bar: FinalBar, *, gaps: tuple[CoverageGap, ...] = ()) -> TrackerUpdate:
        """Observe one complete one-minute bar and its known missing coverage."""
        if not isinstance(bar, FinalBar):
            raise BacktestValidationError("bar must be a FinalBar")
        if not isinstance(gaps, tuple) or any(not isinstance(gap, CoverageGap) for gap in gaps):
            raise BacktestValidationError("gaps must be a tuple of CoverageGap values")
        if bar.timeframe is not Timeframe.ONE_MINUTE:
            return TrackerUpdate()
        lineage = MarketLineage.from_final_bar(bar)
        if self._is_replayed_bar(lineage, bar):
            return TrackerUpdate()
        self._check_gap_capacity(gaps, lineage)

        changed: list[TradeRecord] = []
        warnings: list[RunWarning] = []
        relevant = [
            trade
            for trade in self._active_trades()
            if trade.lineage == lineage and bar.end_ns > trade.signal.signal_ts_ns
        ]
        if not relevant:
            return self._complete_bar(lineage, bar, gaps, TrackerUpdate())

        overlap = self._overlapping_one_minute_gap(lineage, bar, gaps)
        if overlap is not None:
            update = self._unresolve_for_data_quality(
                relevant,
                ObservationReason.COVERAGE_GAP,
                WarningCode.COVERAGE_GAP,
                "one-minute source coverage gap overlaps an eligible observation bar",
                overlap.identity,
            )
            return self._complete_bar(lineage, bar, gaps, update)
        if bar.quality is not QualityState.COMPLETE:
            update = self._unresolve_for_data_quality(
                relevant,
                ObservationReason.DEGRADED_DATA,
                WarningCode.DEGRADED_DATA,
                "degraded one-minute bar is unavailable for outcome observation",
                bar.identity,
            )
            return self._complete_bar(lineage, bar, gaps, update)

        cutoff_trades = [
            trade
            for trade in relevant
            if trade.signal.signal_type is not SignalType.POSITION
            and _cutoff_for_local_date(trade.signal.signal_ts_ns) == bar.end_ns
        ]
        if cutoff_trades:
            for trade in cutoff_trades:
                if trade.state is ObservationState.OPEN:
                    if _stop_triggered(trade.signal, bar):
                        changed.append(
                            self._closed(
                                trade.signal,
                                (
                                    trade.fills[0],
                                    self._exit_fill(trade.signal, FillKind.STOP, bar),
                                ),
                            )
                        )
                    elif _target_triggered(trade.signal, bar):
                        changed.append(
                            self._closed(
                                trade.signal,
                                (
                                    trade.fills[0],
                                    self._exit_fill(trade.signal, FillKind.TARGET, bar),
                                ),
                            )
                        )
                    else:
                        changed.append(self._close_at_cutoff(trade, bar))
                else:
                    changed.append(
                        self._unresolved(
                            trade.signal,
                            trade.fills,
                            ObservationReason.SESSION_CUTOFF,
                        )
                    )
            self._replace(changed)
            return self._complete_bar(lineage, bar, gaps, TrackerUpdate(tuple(changed)))

        missed_cutoff = [
            trade
            for trade in relevant
            if trade.signal.signal_type is not SignalType.POSITION
            and bar.end_ns > _cutoff_for_local_date(trade.signal.signal_ts_ns)
        ]
        if missed_cutoff:
            for trade in missed_cutoff:
                changed.append(
                    self._unresolved(
                        trade.signal,
                        trade.fills,
                        ObservationReason.MISSING_CUTOFF_BAR,
                    )
                )
                warnings.append(
                    self._warning(
                        WarningCode.MISSING_CUTOFF_BAR,
                        "the exact 13:58 America/Los_Angeles cutoff bar is unavailable",
                        tuple(sorted((trade.signal.signal_id, bar.identity))),
                    )
                )
            self._preflight_replace(changed, tuple(warnings))
            self._replace(changed, prechecked=True)
            return self._complete_bar(
                lineage,
                bar,
                gaps,
                TrackerUpdate(tuple(changed), self._add_warnings(tuple(warnings), prechecked=True)),
            )

        for trade in relevant:
            if bar.end_ns <= trade.signal.signal_ts_ns:
                continue
            next_trade = self._observe_eligible_bar(trade, bar)
            if next_trade != trade:
                changed.append(next_trade)
        self._replace(changed)
        return self._complete_bar(lineage, bar, gaps, TrackerUpdate(tuple(changed)))

    def observe_gap(self, gap: CoverageGap) -> TrackerUpdate:
        """Record a known one-minute gap and fail active affected observations closed."""
        if not isinstance(gap, CoverageGap):
            raise BacktestValidationError("gap must be a CoverageGap")
        if gap.identity in self._retained_gap_ids:
            return TrackerUpdate()
        if len(self._retained_gap_ids) >= self._policy.max_retained_gaps:
            raise BacktestValidationError("max_retained_gaps bound exceeded")
        if gap.timeframe is not Timeframe.ONE_MINUTE:
            self._retained_gap_ids.add(gap.identity)
            return TrackerUpdate()
        affected = [
            trade
            for trade in self._active_trades()
            if trade.lineage == gap.lineage and trade.signal.signal_ts_ns < gap.end_ns
        ]
        update = self._unresolve_for_data_quality(
            affected,
            ObservationReason.COVERAGE_GAP,
            WarningCode.COVERAGE_GAP,
            "known one-minute source coverage gap prevents a causal outcome observation",
            gap.identity,
        )
        self._retained_gap_ids.add(gap.identity)
        return update

    def observe_watermark(self, lineage: MarketLineage, finalized_through_ns: int) -> TrackerUpdate:
        """Resolve a provably absent cutoff bar once committed time has passed it."""
        if not isinstance(lineage, MarketLineage):
            raise BacktestValidationError("lineage must be a MarketLineage")
        if (
            not isinstance(finalized_through_ns, int)
            or isinstance(finalized_through_ns, bool)
            or finalized_through_ns < 0
        ):
            raise BacktestValidationError("finalized_through_ns must be non-negative")
        affected = [
            trade
            for trade in self._active_trades()
            if trade.lineage == lineage
            and trade.signal.signal_type is not SignalType.POSITION
            and finalized_through_ns > _cutoff_for_local_date(trade.signal.signal_ts_ns)
        ]
        changed = [
            self._unresolved(
                trade.signal,
                trade.fills,
                ObservationReason.MISSING_CUTOFF_BAR,
            )
            for trade in affected
        ]
        warnings = tuple(
            self._warning(
                WarningCode.MISSING_CUTOFF_BAR,
                "the exact 13:58 Pacific cutoff bar is absent before the committed watermark",
                tuple(sorted((trade.signal.signal_id, lineage.identity))),
            )
            for trade in affected
        )
        self._preflight_replace(changed, warnings)
        self._replace(changed, prechecked=True)
        return TrackerUpdate(tuple(changed), self._add_warnings(warnings, prechecked=True))

    def retire_lineage(self, lineage: MarketLineage) -> TrackerUpdate:
        """End every still-active observation at a physical contract roll."""
        if not isinstance(lineage, MarketLineage):
            raise BacktestValidationError("lineage must be a MarketLineage")
        affected = [trade for trade in self._active_trades() if trade.lineage == lineage]
        changed = [
            self._unresolved(trade.signal, trade.fills, ObservationReason.CONTRACT_ROLL)
            for trade in affected
        ]
        warnings = tuple(
            self._warning(
                WarningCode.CONTRACT_ROLL,
                "physical contract lineage retired before the observation resolved",
                (trade.signal.signal_id,),
            )
            for trade in affected
        )
        self._preflight_replace(changed, warnings)
        self._replace(changed, prechecked=True)
        self._last_bar_end_by_lineage.pop(lineage.identity, None)
        self._last_bar_ids_by_lineage.pop(lineage.identity, None)
        return TrackerUpdate(tuple(changed), self._add_warnings(warnings, prechecked=True))

    def finish(
        self,
        reason: ObservationReason = ObservationReason.END_OF_DATA,
        *,
        lineage: MarketLineage | None = None,
    ) -> TrackerUpdate:
        """Declare a bounded end-of-data or fold boundary without fabricating fills."""
        if reason not in {ObservationReason.END_OF_DATA, ObservationReason.FOLD_END}:
            raise BacktestValidationError("finish reason must be end_of_data or fold_end")
        if lineage is not None and not isinstance(lineage, MarketLineage):
            raise BacktestValidationError("lineage must be a MarketLineage or None")
        affected = [
            trade for trade in self._active_trades() if lineage is None or trade.lineage == lineage
        ]
        changed = [self._unresolved(trade.signal, trade.fills, reason) for trade in affected]
        code = (
            WarningCode.END_OF_DATA
            if reason is ObservationReason.END_OF_DATA
            else WarningCode.FOLD_END
        )
        detail = "available historical evidence ended before the observation resolved"
        if reason is ObservationReason.FOLD_END:
            detail = "chronological replay fold ended before the observation resolved"
        warnings = tuple(
            self._warning(code, detail, (trade.signal.signal_id,)) for trade in affected
        )
        self._preflight_replace(changed, warnings)
        self._replace(changed, prechecked=True)
        return TrackerUpdate(tuple(changed), self._add_warnings(warnings, prechecked=True))

    def _observe_eligible_bar(self, trade: TradeRecord, bar: FinalBar) -> TradeRecord:
        signal = trade.signal
        if trade.state is ObservationState.PENDING:
            if not _touches(bar, signal.entry_ticks):
                return trade
            entry = SimulatedFillRecord(
                signal_id=signal.signal_id,
                kind=FillKind.ENTRY,
                price_ticks=_entry_price(signal, self._policy),
                event_ts_ns=bar.end_ns,
                policy_id=self._policy.policy_id,
                source_bar_id=bar.identity,
            )
            if _stop_triggered(signal, bar):
                return self._closed(
                    trade.signal, (entry, self._exit_fill(signal, FillKind.STOP, bar))
                )
            return TradeRecord(
                signal=signal,
                policy_id=self._policy.policy_id,
                fees_ticks_round_turn=self._policy.fees_ticks_round_turn,
                state=ObservationState.OPEN,
                fills=(entry,),
            )
        if trade.state is not ObservationState.OPEN:
            return trade
        stop_touched = _stop_triggered(signal, bar)
        target_touched = _target_triggered(signal, bar)
        if stop_touched:  # Stop wins every later OHLC ambiguity by policy.
            return self._closed(
                signal, (trade.fills[0], self._exit_fill(signal, FillKind.STOP, bar))
            )
        if target_touched:
            return self._closed(
                signal, (trade.fills[0], self._exit_fill(signal, FillKind.TARGET, bar))
            )
        return trade

    def _close_at_cutoff(self, trade: TradeRecord, bar: FinalBar) -> TradeRecord:
        signal = trade.signal
        exit_fill = SimulatedFillRecord(
            signal_id=signal.signal_id,
            kind=FillKind.SESSION_FLATTEN,
            price_ticks=_adverse_exit_price(signal.direction, bar.close_ticks, self._policy),
            event_ts_ns=bar.end_ns,
            policy_id=self._policy.policy_id,
            source_bar_id=bar.identity,
        )
        return self._closed(signal, (trade.fills[0], exit_fill))

    def _exit_fill(
        self, signal: SignalRecord, kind: FillKind, bar: FinalBar
    ) -> SimulatedFillRecord:
        if kind is FillKind.STOP:
            planned = signal.stop_ticks
            if signal.direction is Direction.LONG:
                raw_price = min(bar.open_ticks, planned)
            else:
                raw_price = max(bar.open_ticks, planned)
        elif kind is FillKind.TARGET:
            # A target gap never grants a better-than-planned price.
            raw_price = signal.target_ticks
        else:
            raise BacktestValidationError("exit fill kind must be stop or target")
        return SimulatedFillRecord(
            signal_id=signal.signal_id,
            kind=kind,
            price_ticks=_adverse_exit_price(signal.direction, raw_price, self._policy),
            event_ts_ns=bar.end_ns,
            policy_id=self._policy.policy_id,
            source_bar_id=bar.identity,
        )

    def _closed(
        self, signal: SignalRecord, fills: tuple[SimulatedFillRecord, SimulatedFillRecord]
    ) -> TradeRecord:
        entry, exit_fill = fills
        gross_ticks = (
            exit_fill.price_ticks - entry.price_ticks
            if signal.direction is Direction.LONG
            else entry.price_ticks - exit_fill.price_ticks
        )
        net_ticks = gross_ticks - self._policy.fees_ticks_round_turn
        risk_ticks = abs(signal.entry_ticks - signal.stop_ticks)
        reason = {
            FillKind.STOP: ObservationReason.STOP,
            FillKind.TARGET: ObservationReason.TARGET,
            FillKind.SESSION_FLATTEN: ObservationReason.SESSION_FLATTEN,
        }[exit_fill.kind]
        return TradeRecord(
            signal=signal,
            policy_id=self._policy.policy_id,
            fees_ticks_round_turn=self._policy.fees_ticks_round_turn,
            state=ObservationState.CLOSED,
            fills=fills,
            gross_ticks=gross_ticks,
            net_ticks=net_ticks,
            gross_r=ExactR.from_ticks(gross_ticks, risk_ticks),
            net_r=ExactR.from_ticks(net_ticks, risk_ticks),
            terminal_reason=reason,
        )

    def _unresolved(
        self,
        signal: SignalRecord,
        fills: tuple[SimulatedFillRecord, ...],
        reason: ObservationReason,
    ) -> TradeRecord:
        return TradeRecord(
            signal=signal,
            policy_id=self._policy.policy_id,
            fees_ticks_round_turn=self._policy.fees_ticks_round_turn,
            state=ObservationState.UNRESOLVED,
            fills=fills,
            terminal_reason=reason,
        )

    def _unresolve_for_data_quality(
        self,
        affected: list[TradeRecord],
        reason: ObservationReason,
        code: WarningCode,
        detail: str,
        source_id: str,
    ) -> TrackerUpdate:
        changed = [self._unresolved(trade.signal, trade.fills, reason) for trade in affected]
        warnings = tuple(
            self._warning(code, detail, tuple(sorted((trade.signal.signal_id, source_id))))
            for trade in affected
        )
        self._preflight_replace(changed, warnings)
        self._replace(changed, prechecked=True)
        return TrackerUpdate(tuple(changed), self._add_warnings(warnings, prechecked=True))

    def _active_trades(self) -> list[TradeRecord]:
        return [
            trade
            for trade in self._trades.values()
            if trade.state in {ObservationState.PENDING, ObservationState.OPEN}
        ]

    def _replace(self, trades: list[TradeRecord], *, prechecked: bool = False) -> None:
        added_fills = sum(
            len(trade.fills) - len(self._trades[trade.signal.signal_id].fills) for trade in trades
        )
        if not prechecked:
            self._ensure_output_capacity(added_fills)
        for trade in trades:
            self._trades[trade.signal.signal_id] = trade

    def _warning(self, code: WarningCode, detail: str, references: tuple[str, ...]) -> RunWarning:
        return RunWarning(code=code, detail=detail, references=references)

    def _add_warnings(
        self, warnings: tuple[RunWarning, ...], *, prechecked: bool = False
    ) -> tuple[RunWarning, ...]:
        novel = tuple(warning for warning in warnings if warning.warning_id not in self._warnings)
        if not prechecked:
            self._ensure_output_capacity(len(novel))
        for warning in novel:
            self._warnings[warning.warning_id] = warning
        return novel

    def _preflight_replace(
        self, trades: list[TradeRecord], warnings: tuple[RunWarning, ...]
    ) -> None:
        added_fills = sum(
            len(trade.fills) - len(self._trades[trade.signal.signal_id].fills) for trade in trades
        )
        novel_warnings = sum(warning.warning_id not in self._warnings for warning in warnings)
        self._ensure_output_capacity(added_fills + novel_warnings)

    def _ensure_output_capacity(self, additional: int) -> None:
        current = (
            len(self._trades)
            + sum(len(trade.fills) for trade in self._trades.values())
            + len(self._warnings)
        )
        if current + additional > self._policy.max_output_records:
            raise BacktestValidationError("max_output_records bound exceeded")

    def _is_replayed_bar(self, lineage: MarketLineage, bar: FinalBar) -> bool:
        last_end = self._last_bar_end_by_lineage.get(lineage.identity)
        if last_end is None:
            return False
        if bar.end_ns < last_end:
            raise BacktestValidationError("one-minute bar end regressed")
        if bar.end_ns > last_end:
            return False
        known_ids = self._last_bar_ids_by_lineage[lineage.identity]
        if bar.identity in known_ids:
            return True
        raise BacktestValidationError("conflicting one-minute bars share an end timestamp")

    def _remember_bar(self, lineage: MarketLineage, bar: FinalBar) -> None:
        last_end = self._last_bar_end_by_lineage.get(lineage.identity)
        if last_end is None or bar.end_ns > last_end:
            self._last_bar_end_by_lineage[lineage.identity] = bar.end_ns
            self._last_bar_ids_by_lineage[lineage.identity] = frozenset((bar.identity,))

    def _remember_gaps(self, gaps: tuple[CoverageGap, ...], lineage: MarketLineage) -> None:
        self._check_gap_capacity(gaps, lineage)
        self._retained_gap_ids.update(gap.identity for gap in gaps if gap.lineage == lineage)

    def _check_gap_capacity(self, gaps: tuple[CoverageGap, ...], lineage: MarketLineage) -> None:
        new_ids = {
            gap.identity
            for gap in gaps
            if gap.lineage == lineage and gap.identity not in self._retained_gap_ids
        }
        if len(self._retained_gap_ids) + len(new_ids) > self._policy.max_retained_gaps:
            raise BacktestValidationError("max_retained_gaps bound exceeded")

    def _complete_bar(
        self,
        lineage: MarketLineage,
        bar: FinalBar,
        gaps: tuple[CoverageGap, ...],
        update: TrackerUpdate,
    ) -> TrackerUpdate:
        self._remember_gaps(gaps, lineage)
        if any(trade.lineage == lineage for trade in self._active_trades()):
            self._remember_bar(lineage, bar)
        else:
            self._last_bar_end_by_lineage.pop(lineage.identity, None)
            self._last_bar_ids_by_lineage.pop(lineage.identity, None)
        return update

    @staticmethod
    def _overlapping_one_minute_gap(
        lineage: MarketLineage, bar: FinalBar, gaps: tuple[CoverageGap, ...]
    ) -> CoverageGap | None:
        for gap in gaps:
            if (
                gap.lineage == lineage
                and gap.timeframe is Timeframe.ONE_MINUTE
                and gap.start_ns < bar.end_ns
                and bar.start_ns < gap.end_ns
            ):
                return gap
        return None


def _touches(bar: FinalBar, price_ticks: int) -> bool:
    return bar.low_ticks <= price_ticks <= bar.high_ticks


def _stop_triggered(signal: SignalRecord, bar: FinalBar) -> bool:
    if signal.direction is Direction.LONG:
        return bar.low_ticks <= signal.stop_ticks
    return bar.high_ticks >= signal.stop_ticks


def _target_triggered(signal: SignalRecord, bar: FinalBar) -> bool:
    if signal.direction is Direction.LONG:
        return bar.high_ticks >= signal.target_ticks
    return bar.low_ticks <= signal.target_ticks


def _entry_price(signal: SignalRecord, policy: SimulationPolicy) -> int:
    if signal.direction is Direction.LONG:
        return signal.entry_ticks + policy.entry_slippage_ticks
    return signal.entry_ticks - policy.entry_slippage_ticks


def _adverse_exit_price(direction: Direction, price_ticks: int, policy: SimulationPolicy) -> int:
    if direction is Direction.LONG:
        return price_ticks - policy.exit_slippage_ticks
    return price_ticks + policy.exit_slippage_ticks


def _to_pacific(ns: int) -> datetime:
    seconds, nanoseconds = divmod(ns, _NANOSECONDS_PER_SECOND)
    instant = _EPOCH + timedelta(seconds=seconds, microseconds=nanoseconds // 1_000)
    return instant.astimezone(_PACIFIC)


def _cutoff_for_local_date(signal_ts_ns: int) -> int:
    local = _to_pacific(signal_ts_ns)
    cutoff = local.replace(hour=13, minute=58, second=0, microsecond=0)
    utc_cutoff = cutoff.astimezone(UTC)
    delta = utc_cutoff - _EPOCH
    return (
        delta.days * 86_400 + delta.seconds
    ) * _NANOSECONDS_PER_SECOND + delta.microseconds * 1_000


def _cutoff_at_or_after_signal(signal_ts_ns: int) -> int:
    return _cutoff_for_local_date(signal_ts_ns)
