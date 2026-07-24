"""Order-independent reconciliation of immutable lifecycle evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from stoic_derived.market_data.model import FinalBar, Timeframe
from stoic_derived.signal_engine.model import SignalRecord, SignalType

from .model import (
    ConflictCode,
    EventKind,
    LedgerConflict,
    LedgerError,
    LedgerEvent,
    LedgerLimits,
    LedgerRecord,
    LedgerState,
    LedgerView,
    ReconciliationResult,
    canonical_json_bytes,
)

PACIFIC = ZoneInfo("America/Los_Angeles")


def reconcile_events(
    events: Iterable[LedgerEvent],
    *,
    limits: LedgerLimits | None = None,
) -> ReconciliationResult:
    """Materialize all four ledgers without trusting transport order or clocks."""
    selected_limits = limits or LedgerLimits()
    by_id: dict[str, LedgerEvent] = {}
    for event in events:
        if not isinstance(event, LedgerEvent):
            raise LedgerError("events must contain LedgerEvent values")
        existing = by_id.setdefault(event.event_id, event)
        if existing.canonical_bytes() != event.canonical_bytes():
            raise LedgerError("event_id collision with different canonical bytes")
    if len(by_id) > selected_limits.max_events_per_reconcile:
        raise LedgerError("event count exceeds max_events_per_reconcile")
    if len({event.source_partition for event in by_id.values()}) > (
        selected_limits.max_source_partitions
    ):
        raise LedgerError("source partitions exceed max_source_partitions")

    grouped: dict[tuple[SignalType, str], list[LedgerEvent]] = defaultdict(list)
    for event in by_id.values():
        grouped[(event.signal_type, event.signal_id)].append(event)

    records_by_type: dict[SignalType, list[LedgerRecord]] = {
        signal_type: [] for signal_type in SignalType
    }
    all_conflicts: list[LedgerConflict] = []
    for (signal_type, signal_id), signal_events in sorted(
        grouped.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        record, conflicts = _reconcile_signal(signal_type, signal_id, signal_events)
        all_conflicts.extend(conflicts)
        if record is not None:
            records_by_type[signal_type].append(record)
            if len(records_by_type[signal_type]) > selected_limits.max_signals_per_type:
                raise LedgerError(f"{signal_type.value} signals exceed max_signals_per_type")

    active_count = sum(
        record.state in {LedgerState.PENDING, LedgerState.ACTIVE}
        for records in records_by_type.values()
        for record in records
    )
    if active_count > selected_limits.max_active_signals:
        raise LedgerError("active records exceed max_active_signals")

    views = tuple(
        LedgerView(
            signal_type,
            tuple(sorted(records_by_type[signal_type], key=lambda item: item.signal.signal_id)),
        )
        for signal_type in sorted(SignalType, key=lambda item: item.value)
    )
    conflicts = tuple(
        sorted(
            all_conflicts,
            key=lambda item: (
                item.signal_type.value,
                item.signal_id,
                item.code.value,
                item.semantic_ids,
            ),
        )
    )
    return ReconciliationResult(views, conflicts)


def _reconcile_signal(
    signal_type: SignalType,
    signal_id: str,
    events: list[LedgerEvent],
) -> tuple[LedgerRecord | None, tuple[LedgerConflict, ...]]:
    semantic_groups: dict[str, list[LedgerEvent]] = defaultdict(list)
    for event in events:
        semantic_groups[event.semantic_id].append(event)
    for group in semantic_groups.values():
        group.sort(key=lambda item: item.event_id)

    root_ids = tuple(
        sorted(
            semantic_id
            for semantic_id, group in semantic_groups.items()
            if group[0].kind is EventKind.SIGNAL_OBSERVED
        )
    )
    if not root_ids:
        conflict = _conflict(
            ConflictCode.MISSING_SIGNAL,
            signal_type,
            signal_id,
            tuple(sorted(semantic_groups)),
            "lifecycle evidence has no signal_observed root",
        )
        return None, (conflict,)
    if len(root_ids) != 1:
        conflict = _conflict(
            ConflictCode.SIGNAL_CONFLICT,
            signal_type,
            signal_id,
            root_ids,
            "multiple different signal_observed roots claim one signal_id",
        )
        return None, (conflict,)

    root_id = root_ids[0]
    root = semantic_groups[root_id][0]
    assert root.signal is not None
    signal = root.signal
    inconsistent = tuple(
        sorted(
            event.semantic_id
            for event in events
            if (
                event.signal_sha256 != root.signal_sha256
                or event.lineage != signal.lineage
                or event.signal_type is not signal.signal_type
            )
        )
    )
    if inconsistent:
        conflict = _conflict(
            ConflictCode.CROSS_LINEAGE,
            signal_type,
            signal_id,
            inconsistent,
            "event signal digest, Type, or physical lineage differs from signal root",
        )
        return _unresolved_record(
            signal,
            root_id,
            events,
            (conflict,),
            entry_ts=None,
            entry_price=None,
        ), (conflict,)

    children: dict[str, set[str]] = defaultdict(set)
    for semantic_id, group in semantic_groups.items():
        predecessor = group[0].predecessor_semantic_id
        if predecessor is not None:
            children[predecessor].add(semantic_id)

    current_id = root_id
    visited = {root_id}
    state = LedgerState.PENDING
    entry_ts: int | None = None
    entry_price: int | None = None
    close_ts: int | None = None
    close_price: int | None = None
    terminal_reason: str | None = None
    current_observed_ns = signal.signal_ts_ns
    entry_bar_id: str | None = None
    entry_bar_touched_stop = False
    conflicts: list[LedgerConflict] = []

    while True:
        next_ids = tuple(sorted(children.get(current_id, set())))
        if not next_ids:
            if state is LedgerState.ACTIVE and entry_bar_touched_stop:
                conflicts.append(
                    _conflict(
                        ConflictCode.INVALID_TRANSITION,
                        signal_type,
                        signal_id,
                        (current_id,),
                        "entry bar touched stop but has no same-bar stop observation",
                    )
                )
            break
        if state in {LedgerState.CLOSED, LedgerState.UNRESOLVED}:
            conflicts.append(
                _conflict(
                    ConflictCode.TERMINAL_SUCCESSOR,
                    signal_type,
                    signal_id,
                    next_ids,
                    "terminal lifecycle evidence has a successor",
                )
            )
            break
        if len(next_ids) != 1:
            conflicts.append(
                _conflict(
                    ConflictCode.EVENT_FORK,
                    signal_type,
                    signal_id,
                    next_ids,
                    "multiple incompatible successor observations share one predecessor",
                )
            )
            break

        next_id = next_ids[0]
        event = semantic_groups[next_id][0]
        transition_error = _transition_error(
            signal,
            state,
            event,
            current_observed_ns=current_observed_ns,
            entry_bar_id=entry_bar_id,
            entry_bar_touched_stop=entry_bar_touched_stop,
        )
        if transition_error is not None:
            visited.add(next_id)
            conflicts.append(
                _conflict(
                    transition_error[0],
                    signal_type,
                    signal_id,
                    (next_id,),
                    transition_error[1],
                )
            )
            break
        visited.add(next_id)
        current_id = next_id
        current_observed_ns = event.observed_ts_ns
        if event.kind is EventKind.ENTRY_OBSERVED:
            state = LedgerState.ACTIVE
            entry_ts = event.observed_ts_ns
            entry_price = event.price_ticks
            assert event.market_bar is not None
            entry_bar_id = event.market_bar.identity
            entry_bar_touched_stop = _touches(event.market_bar, signal.stop_ticks)
        elif event.kind in {
            EventKind.STOP_OBSERVED,
            EventKind.TARGET_OBSERVED,
            EventKind.SESSION_FLATTEN_OBSERVED,
        }:
            state = LedgerState.CLOSED
            close_ts = event.observed_ts_ns
            close_price = event.price_ticks
            terminal_reason = event.kind.value
        else:
            state = LedgerState.UNRESOLVED
            terminal_reason = event.reason

    orphan_ids = tuple(sorted(set(semantic_groups) - visited))
    if orphan_ids and not any(
        conflict.code in {ConflictCode.EVENT_FORK, ConflictCode.TERMINAL_SUCCESSOR}
        for conflict in conflicts
    ):
        conflicts.append(
            _conflict(
                ConflictCode.ORPHAN_EVENT,
                signal_type,
                signal_id,
                orphan_ids,
                "event is not reachable from the unique signal root",
            )
        )
    if conflicts:
        ordered_conflicts = tuple(
            sorted(conflicts, key=lambda item: (item.code.value, item.semantic_ids))
        )
        return (
            _unresolved_record(
                signal,
                current_id,
                events,
                ordered_conflicts,
                entry_ts=entry_ts,
                entry_price=entry_price,
            ),
            ordered_conflicts,
        )

    contributing = tuple(
        sorted(event.event_id for semantic_id in visited for event in semantic_groups[semantic_id])
    )
    record = LedgerRecord(
        signal=signal,
        state=state,
        current_semantic_id=current_id,
        contributing_event_ids=contributing,
        entry_observed_ts_ns=entry_ts,
        entry_price_ticks=entry_price,
        close_observed_ts_ns=close_ts,
        close_price_ticks=close_price,
        terminal_reason=terminal_reason,
    )
    return record, ()


def _transition_error(
    signal: SignalRecord,
    state: LedgerState,
    event: LedgerEvent,
    *,
    current_observed_ns: int,
    entry_bar_id: str | None,
    entry_bar_touched_stop: bool,
) -> tuple[ConflictCode, str] | None:
    if event.observed_ts_ns < current_observed_ns:
        return (
            ConflictCode.INVALID_TRANSITION,
            "lifecycle observation precedes its predecessor observation",
        )
    if event.kind is EventKind.ENTRY_OBSERVED:
        if state is not LedgerState.PENDING:
            return ConflictCode.INVALID_TRANSITION, "entry observation requires pending state"
        if (
            event.market_bar is None
            or event.market_bar.timeframe is not signal.timeframe_plan.manage
        ):
            return (
                ConflictCode.INVALID_TRANSITION,
                "entry observation must use the pinned manage timeframe",
            )
        if event.observed_ts_ns <= signal.signal_ts_ns:
            return ConflictCode.INVALID_TRANSITION, "entry observation must be after signal"
        if event.price_ticks != signal.entry_ticks:
            return (
                ConflictCode.INVALID_TRANSITION,
                "entry observation price must equal planned entry",
            )
        if not _touches(event.market_bar, signal.entry_ticks):
            return (
                ConflictCode.INVALID_TRANSITION,
                "entry price is outside the cited market bar",
            )
        return None

    if event.kind is EventKind.UNRESOLVED_OBSERVED:
        if state not in {LedgerState.PENDING, LedgerState.ACTIVE}:
            return (
                ConflictCode.INVALID_TRANSITION,
                "unresolved observation requires pending or active state",
            )
        return None

    if state is not LedgerState.ACTIVE:
        return ConflictCode.INVALID_TRANSITION, "terminal market observation requires active state"
    if event.market_bar is None:
        return ConflictCode.INVALID_TRANSITION, "terminal observation has no market bar"
    if entry_bar_touched_stop and (
        event.kind is not EventKind.STOP_OBSERVED or event.market_bar.identity != entry_bar_id
    ):
        return (
            ConflictCode.INVALID_TRANSITION,
            "entry-bar stop touch requires a same-bar stop observation",
        )
    if event.kind is EventKind.STOP_OBSERVED:
        if event.market_bar.timeframe is not signal.timeframe_plan.manage:
            return (
                ConflictCode.INVALID_TRANSITION,
                "stop observation must use the pinned manage timeframe",
            )
        if event.price_ticks != signal.stop_ticks:
            return ConflictCode.INVALID_TRANSITION, "stop price must equal planned stop"
        if not _touches(event.market_bar, signal.stop_ticks):
            return ConflictCode.INVALID_TRANSITION, "stop price is outside the cited market bar"
        return None
    if event.kind is EventKind.TARGET_OBSERVED:
        if event.market_bar.timeframe is not signal.timeframe_plan.manage:
            return (
                ConflictCode.INVALID_TRANSITION,
                "target observation must use the pinned manage timeframe",
            )
        if event.price_ticks != signal.target_ticks:
            return ConflictCode.INVALID_TRANSITION, "target price must equal planned target"
        if event.market_bar.identity == entry_bar_id:
            return ConflictCode.INVALID_TRANSITION, "entry-bar target cannot prove causal ordering"
        if not _touches(event.market_bar, signal.target_ticks):
            return (
                ConflictCode.INVALID_TRANSITION,
                "target price is outside the cited market bar",
            )
        if _touches(event.market_bar, signal.stop_ticks):
            return (
                ConflictCode.INVALID_TRANSITION,
                "target observation cannot override a same-bar stop touch",
            )
        return None
    if event.kind is EventKind.SESSION_FLATTEN_OBSERVED:
        if signal.signal_type is SignalType.POSITION:
            return ConflictCode.POSITION_CUTOFF, "Position cannot receive session cutoff evidence"
        if event.market_bar.timeframe is not Timeframe.ONE_MINUTE:
            return ConflictCode.INVALID_TRANSITION, "cutoff evidence must use a one-minute bar"
        pacific_end = datetime.fromtimestamp(
            event.market_bar.end_ns / 1_000_000_000, tz=UTC
        ).astimezone(PACIFIC)
        if (pacific_end.hour, pacific_end.minute, pacific_end.second, pacific_end.microsecond) != (
            13,
            58,
            0,
            0,
        ):
            return ConflictCode.INVALID_TRANSITION, "cutoff bar must end at 13:58 Pacific"
        if event.price_ticks != event.market_bar.close_ticks:
            return ConflictCode.INVALID_TRANSITION, "cutoff price must equal observed bar close"
        return None
    return ConflictCode.INVALID_TRANSITION, "unsupported successor event"


def _touches(bar: FinalBar, price_ticks: int) -> bool:
    return bar.low_ticks <= price_ticks <= bar.high_ticks


def _unresolved_record(
    signal: SignalRecord,
    current_semantic_id: str,
    events: list[LedgerEvent],
    conflicts: tuple[LedgerConflict, ...],
    *,
    entry_ts: int | None,
    entry_price: int | None,
) -> LedgerRecord:
    conflict_projection = [conflict.canonical_dict() for conflict in conflicts]
    conflict_identity = sha256(
        canonical_json_bytes(
            {
                "current_semantic_id": current_semantic_id,
                "evidence_conflicts": conflict_projection,
                "signal_id": signal.signal_id,
            }
        )
    ).hexdigest()
    return LedgerRecord(
        signal=signal,
        state=LedgerState.UNRESOLVED,
        current_semantic_id=conflict_identity,
        contributing_event_ids=tuple(sorted(event.event_id for event in events)),
        entry_observed_ts_ns=entry_ts,
        entry_price_ticks=entry_price,
        terminal_reason="evidence_conflict",
        conflicts=conflicts,
    )


def _conflict(
    code: ConflictCode,
    signal_type: SignalType,
    signal_id: str,
    semantic_ids: tuple[str, ...],
    detail: str,
) -> LedgerConflict:
    return LedgerConflict(
        code=code,
        signal_type=signal_type,
        signal_id=signal_id,
        semantic_ids=tuple(sorted(set(semantic_ids))),
        detail=detail,
    )


__all__ = ["PACIFIC", "reconcile_events"]
