from __future__ import annotations

from stoic_derived.ledger.model import (
    ConflictCode,
    EventKind,
    LedgerEvent,
    LedgerState,
)
from stoic_derived.ledger.reconcile import reconcile_events
from stoic_derived.market_data.model import Timeframe
from stoic_derived.signal_engine.model import SignalType


def test_reconciliation_always_returns_four_separate_type_ledgers(make_signal) -> None:
    events = tuple(
        LedgerEvent.for_signal(make_signal(signal_type=signal_type), source="writer")
        for signal_type in SignalType
    )

    result = reconcile_events(reversed(events))

    assert {view.signal_type for view in result.views} == set(SignalType)
    assert all(len(view.records) == 1 for view in result.views)
    assert all(view.records[0].state is LedgerState.PENDING for view in result.views)


def test_entry_and_target_materialize_closed_observation(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    target_bar = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=95,
        close_ticks=120,
    )
    target = LedgerEvent.for_market(
        EventKind.TARGET_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=target_bar,
        price_ticks=signal.target_ticks,
        source="writer",
    )

    record = reconcile_events((target, root, entry)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.CLOSED
    assert record.entry_price_ticks == signal.entry_ticks
    assert record.close_price_ticks == signal.target_ticks
    assert record.terminal_reason == EventKind.TARGET_OBSERVED.value


def test_equivalent_multi_source_observations_converge(make_signal, make_bar) -> None:
    signal = make_signal()
    roots = tuple(
        LedgerEvent.for_signal(signal, source=source) for source in ("writer-a", "writer-b")
    )
    bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    entries = tuple(
        LedgerEvent.for_market(
            EventKind.ENTRY_OBSERVED,
            signal,
            predecessor_semantic_id=roots[0].semantic_id,
            market_bar=bar,
            price_ticks=signal.entry_ticks,
            source=source,
        )
        for source in ("writer-a", "writer-b")
    )

    record = reconcile_events((*entries, *roots)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.ACTIVE
    assert len(record.contributing_event_ids) == 4
    assert not record.conflicts


def test_incompatible_terminal_fork_fails_unresolved(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    ambiguous = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=85,
        close_ticks=100,
    )
    stop = LedgerEvent.for_market(
        EventKind.STOP_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=ambiguous,
        price_ticks=signal.stop_ticks,
        source="writer-a",
    )
    target = LedgerEvent.for_market(
        EventKind.TARGET_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=ambiguous,
        price_ticks=signal.target_ticks,
        source="writer-b",
    )

    record = reconcile_events((target, root, stop, entry)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.terminal_reason == "evidence_conflict"
    assert record.conflicts[0].code is ConflictCode.EVENT_FORK
    assert set(record.contributing_event_ids) == {
        root.event_id,
        entry.event_id,
        stop.event_id,
        target.event_id,
    }


def test_drive_listing_permutations_are_byte_identical(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000),
        price_ticks=signal.entry_ticks,
        source="writer",
    )

    forward = reconcile_events((root, entry)).canonical_bytes()
    reverse = reconcile_events((entry, root, root)).canonical_bytes()

    assert forward == reverse


def test_position_cutoff_evidence_is_rejected_by_fold(make_signal, make_bar) -> None:
    signal = make_signal(signal_type=SignalType.POSITION)
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(
        timeframe=Timeframe.DAILY,
        end_ns=signal.signal_ts_ns + 86_400_000_000_000,
    )
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    cutoff_bar = make_bar(
        timeframe=Timeframe.ONE_MINUTE,
        end_ns=entry_bar.end_ns + 60_000_000_000,
    )
    cutoff = LedgerEvent.for_market(
        EventKind.SESSION_FLATTEN_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=cutoff_bar,
        price_ticks=cutoff_bar.close_ticks,
        source="watchdog",
        fence_token=1,
    )

    record = reconcile_events((root, entry, cutoff)).for_type(SignalType.POSITION).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.POSITION_CUTOFF


def test_entry_price_must_be_inside_cited_bar(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    bar = make_bar(
        end_ns=signal.signal_ts_ns + 300_000_000_000,
        open_ticks=110,
        high_ticks=115,
        low_ticks=105,
        close_ticks=110,
    )
    impossible = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )

    record = reconcile_events((root, impossible)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.INVALID_TRANSITION


def test_target_on_entry_bar_is_causally_invalid(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    bar = make_bar(
        end_ns=signal.signal_ts_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=95,
        close_ticks=120,
    )
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    target = LedgerEvent.for_market(
        EventKind.TARGET_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=bar,
        price_ticks=signal.target_ticks,
        source="writer",
    )

    record = reconcile_events((root, entry, target)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.INVALID_TRANSITION


def test_target_bar_that_also_touches_stop_is_causally_invalid(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    tie_bar = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=85,
        close_ticks=120,
    )
    target = LedgerEvent.for_market(
        EventKind.TARGET_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=tie_bar,
        price_ticks=signal.target_ticks,
        source="writer",
    )

    record = reconcile_events((root, entry, target)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.INVALID_TRANSITION


def test_terminal_market_time_cannot_precede_entry(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 600_000_000_000)
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )
    earlier_stop_bar = make_bar(
        end_ns=signal.signal_ts_ns + 300_000_000_000,
        high_ticks=101,
        low_ticks=85,
        close_ticks=90,
    )
    stop = LedgerEvent.for_market(
        EventKind.STOP_OBSERVED,
        signal,
        predecessor_semantic_id=entry.semantic_id,
        market_bar=earlier_stop_bar,
        price_ticks=signal.stop_ticks,
        source="writer",
    )

    record = reconcile_events((root, entry, stop)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.INVALID_TRANSITION


def test_entry_bar_stop_touch_requires_same_bar_stop_successor(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    entry_bar = make_bar(
        end_ns=signal.signal_ts_ns + 300_000_000_000,
        high_ticks=105,
        low_ticks=85,
        close_ticks=100,
    )
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=entry_bar,
        price_ticks=signal.entry_ticks,
        source="writer",
    )

    record = reconcile_events((root, entry)).for_type(SignalType.SCALP).records[0]

    assert record.state is LedgerState.UNRESOLVED
    assert record.conflicts[0].code is ConflictCode.INVALID_TRANSITION
