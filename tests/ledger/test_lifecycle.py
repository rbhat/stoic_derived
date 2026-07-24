from __future__ import annotations

import pytest

from stoic_derived.ledger.lifecycle import LifecycleTracker
from stoic_derived.ledger.model import EventKind, LedgerError, LedgerLimits, LedgerState
from stoic_derived.signal_engine.model import CoverageGap, Direction, SignalType


def test_signal_then_entry_then_target_tracks_full_lifecycle(
    make_signal, make_bar, make_batch
) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    root = tracker.observe_signal(signal)
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)

    entry_events = tracker.ingest(make_batch(bars=(entry_bar,)))
    target_bar = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=95,
        close_ticks=120,
    )
    target_events = tracker.ingest(make_batch(bars=(target_bar,)))
    record = tracker.result.for_type(SignalType.SCALP).records[0]

    assert len(root) == 1
    assert [event.kind for event in entry_events] == [EventKind.ENTRY_OBSERVED]
    assert [event.kind for event in target_events] == [EventKind.TARGET_OBSERVED]
    assert record.state is LedgerState.CLOSED
    assert record.close_price_ticks == signal.target_ticks


def test_entry_bar_stop_wins_and_target_is_not_claimed(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    ambiguous_entry = make_bar(
        end_ns=signal.signal_ts_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=85,
        close_ticks=100,
    )

    created = tracker.ingest(make_batch(bars=(ambiguous_entry,)))

    assert [event.kind for event in created] == [
        EventKind.ENTRY_OBSERVED,
        EventKind.STOP_OBSERVED,
    ]


def test_later_stop_target_tie_is_stop_first(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    tracker.ingest(make_batch(bars=(entry_bar,)))
    tie = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=125,
        low_ticks=85,
        close_ticks=100,
    )

    created = tracker.ingest(make_batch(bars=(tie,)))

    assert [event.kind for event in created] == [EventKind.STOP_OBSERVED]


def test_short_signal_is_observed_symmetrically(make_signal, make_bar, make_batch) -> None:
    signal = make_signal(direction=Direction.SHORT)
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    entry_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    tracker.ingest(make_batch(bars=(entry_bar,)))
    target = make_bar(
        end_ns=entry_bar.end_ns + 300_000_000_000,
        high_ticks=105,
        low_ticks=75,
        close_ticks=80,
    )

    created = tracker.ingest(make_batch(bars=(target,)))

    assert [event.kind for event in created] == [EventKind.TARGET_OBSERVED]


def test_manage_bar_covered_by_gap_is_unavailable(
    make_signal, make_bar, make_batch, lineage
) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    gap = CoverageGap(
        lineage=lineage,
        timeframe=bar.timeframe,
        start_ns=bar.start_ns,
        end_ns=bar.end_ns,
        reason="known_missing_coverage",
    )

    created = tracker.ingest(make_batch(bars=(bar,), gaps=(gap,)))

    assert not created
    assert tracker.result.for_type(SignalType.SCALP).records[0].state is LedgerState.PENDING


def test_duplicate_batch_and_signal_are_idempotent(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    tracker.observe_signal(signal)
    batch = make_batch(bars=(make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000),))

    first = tracker.ingest(batch)
    second = tracker.ingest(batch)

    assert len(first) == 1
    assert not second
    assert len(tracker.events) == 2


def test_conflicting_same_interval_content_fails_closed(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    first_bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    second_bar = make_bar(
        end_ns=first_bar.end_ns,
        high_ticks=106,
        low_ticks=95,
        close_ticks=102,
    )
    tracker.ingest(make_batch(bars=(first_bar,)))

    with pytest.raises(LedgerError, match="conflicting bars"):
        tracker.ingest(make_batch(bars=(second_bar,)))


def test_watermark_regression_is_rejected(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(source="lifecycle")
    bar = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    tracker.ingest(make_batch(bars=(bar,), finalized_through_ns=bar.end_ns + 10))

    with pytest.raises(LedgerError, match="watermark regressed"):
        tracker.ingest(make_batch(finalized_through_ns=bar.end_ns))


def test_contract_roll_makes_pending_and_active_unresolved(
    make_signal, make_bar, make_batch, lineage
) -> None:
    active = make_signal(signal_type=SignalType.SCALP)
    pending = make_signal(
        signal_type=SignalType.DAY,
        signal_ts_ns=active.signal_ts_ns + 600_000_000_000,
    )
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signals(tuple(sorted((pending, active), key=lambda item: item.signal_id)))
    entry_bar = make_bar(end_ns=active.signal_ts_ns + 300_000_000_000)
    tracker.ingest(make_batch(bars=(entry_bar,)))

    created = tracker.retire_lineage(lineage.identity, boundary_ts_ns=pending.signal_ts_ns + 1)

    assert len(created) == 2
    assert {event.reason for event in created} == {"contract_roll"}
    assert {record.state for view in tracker.result.views for record in view.records} == {
        LedgerState.UNRESOLVED
    }


def test_market_observation_bound_fails_atomically(make_signal, make_bar, make_batch) -> None:
    signal = make_signal()
    tracker = LifecycleTracker(
        source="lifecycle",
        limits=LedgerLimits(max_market_observations=1),
    )
    tracker.observe_signal(signal)
    first = make_bar(end_ns=signal.signal_ts_ns + 300_000_000_000)
    second = make_bar(
        end_ns=first.end_ns + 300_000_000_000,
        high_ticks=105,
        low_ticks=95,
        close_ticks=101,
    )

    with pytest.raises(LedgerError, match="max_market_observations"):
        tracker.ingest(make_batch(bars=(first, second)))
    created = tracker.ingest(make_batch(bars=(first,)))

    assert [event.kind for event in created] == [EventKind.ENTRY_OBSERVED]
