"""Causal observational lifecycle tracking over immutable SP1 bars."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from stoic_derived.market_data.model import FinalBar, QualityState
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import CoverageGap, SignalRecord

from .model import (
    EventKind,
    LedgerError,
    LedgerEvent,
    LedgerLimits,
    LedgerState,
    ReconciliationResult,
    canonical_json_bytes,
)
from .reconcile import reconcile_events


class LifecycleTracker:
    """Bounded in-memory evaluator whose durable output is immutable events."""

    def __init__(
        self,
        *,
        source: str,
        limits: LedgerLimits | None = None,
        events: Iterable[LedgerEvent] = (),
    ) -> None:
        if not isinstance(source, str) or not source:
            raise LedgerError("source must be a non-empty string")
        self._source = source
        self._limits = limits or LedgerLimits()
        self._events: dict[str, LedgerEvent] = {}
        self._accepted_batches: set[str] = set()
        self._watermarks: dict[str, int] = {}
        self._bar_intervals: dict[tuple[str, str, int, int], str] = {}
        self._gap_intervals: dict[tuple[str, str, int, int], str] = {}
        self._gaps: dict[str, CoverageGap] = {}
        for event in events:
            self.add_event(event)

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events[event_id] for event_id in sorted(self._events))

    @property
    def result(self) -> ReconciliationResult:
        return reconcile_events(self.events, limits=self._limits)

    def add_event(self, event: LedgerEvent) -> bool:
        """Seed one verified immutable event, idempotently."""
        if not isinstance(event, LedgerEvent):
            raise LedgerError("event must be a LedgerEvent")
        existing = self._events.get(event.event_id)
        if existing is not None:
            if existing.canonical_bytes() != event.canonical_bytes():
                raise LedgerError("event_id collision with different bytes")
            return False
        if len(self._events) >= self._limits.max_events_per_reconcile:
            raise LedgerError("event count exceeds max_events_per_reconcile")
        self._events[event.event_id] = event
        return True

    def observe_signal(self, signal: SignalRecord) -> tuple[LedgerEvent, ...]:
        """Record one complete SP2 signal as pending."""
        if not isinstance(signal, SignalRecord):
            raise LedgerError("signal must be a SignalRecord")
        event = LedgerEvent.for_signal(signal, source=self._source)
        return (event,) if self.add_event(event) else ()

    def observe_signals(self, signals: Iterable[SignalRecord]) -> tuple[LedgerEvent, ...]:
        """Record a deterministic signal set."""
        values = tuple(signals)
        if any(not isinstance(signal, SignalRecord) for signal in values):
            raise LedgerError("signals must contain SignalRecord values")
        if tuple(sorted(values, key=lambda signal: signal.signal_id)) != values:
            raise LedgerError("signals must be ordered by signal_id")
        created: list[LedgerEvent] = []
        for signal in values:
            created.extend(self.observe_signal(signal))
        return tuple(sorted(created, key=lambda event: event.event_id))

    def ingest(self, batch: FinalizedSeriesBatch) -> tuple[LedgerEvent, ...]:
        """Observe eligible manage bars and emit causal lifecycle events."""
        self._accept_batch(batch)
        created: list[LedgerEvent] = []
        result = self.result
        records = [
            record
            for view in result.views
            for record in view.records
            if record.signal.lineage == batch.lineage
            and record.state in {LedgerState.PENDING, LedgerState.ACTIVE}
        ]
        for record in sorted(records, key=lambda item: item.signal.signal_id):
            bars = tuple(
                bar
                for bar in batch.bars
                if bar.timeframe is record.signal.timeframe_plan.manage
                and bar.quality is QualityState.COMPLETE
                and not self._bar_is_gapped(bar)
            )
            created.extend(self._observe_record(record, bars))
        return tuple(sorted(created, key=lambda event: event.event_id))

    def retire_lineage(
        self,
        lineage_identity: str,
        *,
        boundary_ts_ns: int,
    ) -> tuple[LedgerEvent, ...]:
        """Make every nonterminal observation on one physical contract unresolved."""
        if (
            not isinstance(lineage_identity, str)
            or len(lineage_identity) != 64
            or any(character not in "0123456789abcdef" for character in lineage_identity)
        ):
            raise LedgerError("lineage_identity must be a lowercase SHA-256 digest")
        if (
            not isinstance(boundary_ts_ns, int)
            or isinstance(boundary_ts_ns, bool)
            or boundary_ts_ns < 0
        ):
            raise LedgerError("boundary_ts_ns must be a non-negative integer")
        created: list[LedgerEvent] = []
        for view in self.result.views:
            for record in view.records:
                if record.signal.lineage.identity != lineage_identity or record.state not in {
                    LedgerState.PENDING,
                    LedgerState.ACTIVE,
                }:
                    continue
                if boundary_ts_ns < record.signal.signal_ts_ns:
                    raise LedgerError("roll boundary cannot precede signal")
                event = LedgerEvent.for_unresolved(
                    record.signal,
                    predecessor_semantic_id=record.current_semantic_id,
                    observed_ts_ns=boundary_ts_ns,
                    reason="contract_roll",
                    source=self._source,
                )
                if self.add_event(event):
                    created.append(event)
        return tuple(sorted(created, key=lambda event: event.event_id))

    def _observe_record(
        self,
        record: object,
        bars: tuple[FinalBar, ...],
    ) -> tuple[LedgerEvent, ...]:
        from .model import LedgerRecord

        if not isinstance(record, LedgerRecord):  # pragma: no cover - internal guard
            raise LedgerError("record must be a LedgerRecord")
        signal = record.signal
        state = record.state
        predecessor = record.current_semantic_id
        last_observed_ns = record.entry_observed_ts_ns or signal.signal_ts_ns
        created: list[LedgerEvent] = []
        for bar in sorted(bars, key=lambda item: (item.end_ns, item.identity)):
            if state is LedgerState.PENDING:
                if bar.end_ns <= signal.signal_ts_ns:
                    continue
                if not _touches(bar, signal.entry_ticks):
                    continue
                entry = LedgerEvent.for_market(
                    EventKind.ENTRY_OBSERVED,
                    signal,
                    predecessor_semantic_id=predecessor,
                    market_bar=bar,
                    price_ticks=signal.entry_ticks,
                    source=self._source,
                )
                if self.add_event(entry):
                    created.append(entry)
                predecessor = entry.semantic_id
                last_observed_ns = bar.end_ns
                state = LedgerState.ACTIVE
                if _touches(bar, signal.stop_ticks):
                    stop = LedgerEvent.for_market(
                        EventKind.STOP_OBSERVED,
                        signal,
                        predecessor_semantic_id=predecessor,
                        market_bar=bar,
                        price_ticks=signal.stop_ticks,
                        source=self._source,
                    )
                    if self.add_event(stop):
                        created.append(stop)
                    state = LedgerState.CLOSED
                if state is LedgerState.CLOSED:
                    break
                continue

            if state is not LedgerState.ACTIVE or bar.end_ns <= last_observed_ns:
                continue
            stop_touched = _touches(bar, signal.stop_ticks)
            target_touched = _touches(bar, signal.target_ticks)
            if not stop_touched and not target_touched:
                continue
            kind = EventKind.STOP_OBSERVED if stop_touched else EventKind.TARGET_OBSERVED
            price = signal.stop_ticks if stop_touched else signal.target_ticks
            terminal = LedgerEvent.for_market(
                kind,
                signal,
                predecessor_semantic_id=predecessor,
                market_bar=bar,
                price_ticks=price,
                source=self._source,
            )
            if self.add_event(terminal):
                created.append(terminal)
            break
        return tuple(created)

    def _accept_batch(self, batch: FinalizedSeriesBatch) -> None:
        if not isinstance(batch, FinalizedSeriesBatch):
            raise LedgerError("batch must be a FinalizedSeriesBatch")
        lineage_id = batch.lineage.identity
        previous = self._watermarks.get(lineage_id)
        if previous is not None and batch.finalized_through_ns < previous:
            raise LedgerError("per-lineage finalized watermark regressed")
        identity = _batch_identity(batch)
        if identity in self._accepted_batches:
            self._watermarks[lineage_id] = batch.finalized_through_ns
            return
        if len(self._accepted_batches) >= self._limits.max_market_observations:
            raise LedgerError("accepted batch identities exceed max_market_observations")
        bar_intervals = self._bar_intervals.copy()
        gap_intervals = self._gap_intervals.copy()
        gaps = self._gaps.copy()
        for bar in batch.bars:
            key = (lineage_id, bar.timeframe.value, bar.start_ns, bar.end_ns)
            existing = bar_intervals.setdefault(key, bar.identity)
            if existing != bar.identity:
                raise LedgerError("conflicting bars share a physical interval")
        for gap in batch.gaps:
            key = (lineage_id, gap.timeframe.value, gap.start_ns, gap.end_ns)
            existing = gap_intervals.setdefault(key, gap.identity)
            if existing != gap.identity:
                raise LedgerError("conflicting gaps share a physical interval")
            gaps.setdefault(gap.identity, gap)
        if len(bar_intervals) + len(gap_intervals) > self._limits.max_market_observations:
            raise LedgerError("retained intervals exceed max_market_observations")
        if len(gaps) > self._limits.max_retained_gaps:
            raise LedgerError("retained gaps exceed max_retained_gaps")
        self._bar_intervals = bar_intervals
        self._gap_intervals = gap_intervals
        self._gaps = gaps
        self._accepted_batches.add(identity)
        self._watermarks[lineage_id] = batch.finalized_through_ns

    def _bar_is_gapped(self, bar: FinalBar) -> bool:
        lineage_id = self._lineage_id_for_bar(bar)
        return any(
            gap.lineage.identity == lineage_id
            and gap.timeframe is bar.timeframe
            and gap.start_ns < bar.end_ns
            and bar.start_ns < gap.end_ns
            for gap in self._gaps.values()
        )

    @staticmethod
    def _lineage_id_for_bar(bar: FinalBar) -> str:
        from stoic_derived.signal_engine.model import MarketLineage

        return MarketLineage.from_final_bar(bar).identity


def _touches(bar: FinalBar, price_ticks: int) -> bool:
    return bar.low_ticks <= price_ticks <= bar.high_ticks


def _batch_identity(batch: FinalizedSeriesBatch) -> str:
    return sha256(
        canonical_json_bytes(
            {
                "bars": [bar.identity for bar in batch.bars],
                "finalized_through_ns": batch.finalized_through_ns,
                "gaps": [gap.identity for gap in batch.gaps],
                "lineage": batch.lineage.canonical_dict(),
            }
        )
    ).hexdigest()


__all__ = ["LifecycleTracker"]
