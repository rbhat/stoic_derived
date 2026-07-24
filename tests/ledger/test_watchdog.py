from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from stoic_derived.ledger.lifecycle import LifecycleTracker
from stoic_derived.ledger.model import EventKind, LedgerError, LedgerEvent
from stoic_derived.ledger.outbox import LedgerOutbox
from stoic_derived.ledger.watchdog import (
    coalesce_cutoff_batches,
    cutoff_events,
    cutoff_utc_ns,
    enqueue_cutoff,
)
from stoic_derived.market_data.model import QualityState, Timeframe
from stoic_derived.signal_engine.model import CoverageGap, SignalType


def _active_events(make_signal, make_bar, make_batch, session_date: date):
    cutoff_ns = cutoff_utc_ns(session_date)
    signal = make_signal(signal_ts_ns=cutoff_ns - 600_000_000_000)
    tracker = LifecycleTracker(source="lifecycle")
    tracker.observe_signal(signal)
    entry_bar = make_bar(
        end_ns=cutoff_ns - 300_000_000_000,
        timeframe=Timeframe.FIVE_MINUTES,
    )
    tracker.ingest(make_batch(bars=(entry_bar,)))
    return signal, tracker.events


def test_cutoff_uses_pacific_dst_not_fixed_offset() -> None:
    winter = datetime.fromtimestamp(cutoff_utc_ns(date(2026, 1, 15)) / 1_000_000_000, tz=UTC)
    summer = datetime.fromtimestamp(cutoff_utc_ns(date(2026, 7, 15)) / 1_000_000_000, tz=UTC)

    assert (winter.hour, winter.minute) == (21, 58)
    assert (summer.hour, summer.minute) == (20, 58)


def test_active_non_position_closes_at_exact_observed_cutoff_price(
    make_signal, make_bar, make_batch
) -> None:
    session_date = date(2026, 7, 15)
    signal, events = _active_events(make_signal, make_bar, make_batch, session_date)
    cutoff_ns = cutoff_utc_ns(session_date)
    cutoff_bar = make_bar(
        timeframe=Timeframe.ONE_MINUTE,
        end_ns=cutoff_ns,
        open_ticks=103,
        high_ticks=105,
        low_ticks=95,
        close_ticks=104,
    )

    generated = cutoff_events(
        events,
        make_batch(bars=(cutoff_bar,)),
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )

    assert len(generated) == 1
    assert generated[0].kind is EventKind.SESSION_FLATTEN_OBSERVED
    assert generated[0].price_ticks == cutoff_bar.close_ticks
    assert generated[0].signal_id == signal.signal_id
    assert generated[0].canonical_dict()["execution"] is False


def test_pending_becomes_unresolved_without_fabricated_entry(
    make_signal, make_bar, make_batch
) -> None:
    session_date = date(2026, 7, 15)
    cutoff_ns = cutoff_utc_ns(session_date)
    signal = make_signal(signal_ts_ns=cutoff_ns - 60_000_000_000)
    root = LedgerEvent.for_signal(signal, source="lifecycle")
    cutoff_bar = make_bar(timeframe=Timeframe.ONE_MINUTE, end_ns=cutoff_ns)

    generated = cutoff_events(
        (root,),
        make_batch(bars=(cutoff_bar,)),
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )

    assert generated[0].kind is EventKind.UNRESOLVED_OBSERVED
    assert generated[0].reason == "pending_at_session_cutoff"
    assert generated[0].price_ticks is None


def test_position_is_cutoff_exempt(make_signal, make_bar, make_batch) -> None:
    session_date = date(2026, 7, 15)
    cutoff_ns = cutoff_utc_ns(session_date)
    signal = make_signal(
        signal_type=SignalType.POSITION,
        signal_ts_ns=cutoff_ns - 172_800_000_000_000,
    )
    root = LedgerEvent.for_signal(signal, source="lifecycle")
    daily = make_bar(
        timeframe=Timeframe.DAILY,
        end_ns=cutoff_ns - 86_400_000_000_000,
    )
    entry = LedgerEvent.for_market(
        EventKind.ENTRY_OBSERVED,
        signal,
        predecessor_semantic_id=root.semantic_id,
        market_bar=daily,
        price_ticks=signal.entry_ticks,
        source="lifecycle",
    )
    cutoff_bar = make_bar(timeframe=Timeframe.ONE_MINUTE, end_ns=cutoff_ns)

    generated = cutoff_events(
        (root, entry),
        make_batch(bars=(cutoff_bar,)),
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )

    assert not generated


@pytest.mark.parametrize(
    ("quality", "with_gap", "expected_reason"),
    [
        (None, False, "missing_cutoff_bar"),
        (QualityState.DEGRADED, False, "degraded_cutoff_bar"),
        (QualityState.COMPLETE, True, "cutoff_coverage_gap"),
    ],
)
def test_unavailable_cutoff_price_is_explicitly_unresolved(
    quality,
    with_gap,
    expected_reason,
    make_signal,
    make_bar,
    make_batch,
    lineage,
) -> None:
    session_date = date(2026, 7, 15)
    _, events = _active_events(make_signal, make_bar, make_batch, session_date)
    cutoff_ns = cutoff_utc_ns(session_date)
    bars = ()
    gaps = ()
    if quality is not None:
        bar = make_bar(
            timeframe=Timeframe.ONE_MINUTE,
            end_ns=cutoff_ns,
            quality=quality,
        )
        bars = (bar,)
        if with_gap:
            gaps = (
                CoverageGap(
                    lineage=lineage,
                    timeframe=Timeframe.ONE_MINUTE,
                    start_ns=bar.start_ns,
                    end_ns=bar.end_ns,
                    reason="missing",
                ),
            )
    batch = make_batch(
        bars=bars,
        gaps=gaps,
        finalized_through_ns=cutoff_ns,
    )

    generated = cutoff_events(
        events,
        batch,
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )

    assert generated[0].kind is EventKind.UNRESOLVED_OBSERVED
    assert generated[0].reason == expected_reason
    assert generated[0].price_ticks is None


def test_watchdog_refuses_incomplete_watermark(make_signal, make_batch) -> None:
    session_date = date(2026, 7, 15)
    cutoff_ns = cutoff_utc_ns(session_date)
    root = LedgerEvent.for_signal(
        make_signal(signal_ts_ns=cutoff_ns - 60_000_000_000),
        source="lifecycle",
    )

    with pytest.raises(LedgerError, match="watermark"):
        cutoff_events(
            (root,),
            make_batch(finalized_through_ns=cutoff_ns - 1),
            session_date=session_date,
            source="watchdog",
            fence_token=1,
        )


def test_fenced_enqueue_survives_prior_process_death(
    tmp_path, make_signal, make_bar, make_batch
) -> None:
    session_date = date(2026, 7, 15)
    _, events = _active_events(make_signal, make_bar, make_batch, session_date)
    cutoff_ns = cutoff_utc_ns(session_date)
    batch = make_batch(bars=(make_bar(timeframe=Timeframe.ONE_MINUTE, end_ns=cutoff_ns),))
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")

    generated = enqueue_cutoff(
        events,
        batch,
        outbox,
        session_date=session_date,
        source="watchdog",
        owner="scheduler-instance",
        now_utc_ns=cutoff_ns,
        lease_ttl_ns=60_000_000_000,
    )

    assert len(generated) == 1
    assert len(outbox.pending()) == 1


def test_fence_changes_event_evidence_not_semantic_truth(make_signal, make_bar, make_batch) -> None:
    session_date = date(2026, 7, 15)
    _, events = _active_events(make_signal, make_bar, make_batch, session_date)
    cutoff_ns = cutoff_utc_ns(session_date)
    batch = make_batch(bars=(make_bar(timeframe=Timeframe.ONE_MINUTE, end_ns=cutoff_ns),))

    first = cutoff_events(
        events,
        batch,
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )[0]
    second = cutoff_events(
        events,
        batch,
        session_date=session_date,
        source="watchdog",
        fence_token=2,
    )[0]

    assert first.event_id != second.event_id
    assert first.semantic_id == second.semantic_id


def test_restart_reconstruction_retains_cutoff_bar_from_earlier_batch(
    make_signal, make_bar, make_batch
) -> None:
    session_date = date(2026, 7, 15)
    _, events = _active_events(make_signal, make_bar, make_batch, session_date)
    cutoff_ns = cutoff_utc_ns(session_date)
    cutoff_bar = make_bar(
        timeframe=Timeframe.ONE_MINUTE,
        end_ns=cutoff_ns,
        close_ticks=104,
    )
    with_bar = make_batch(bars=(cutoff_bar,), finalized_through_ns=cutoff_ns)
    watermark_only = make_batch(finalized_through_ns=cutoff_ns + 60_000_000_000)

    coalesced = coalesce_cutoff_batches((with_bar, watermark_only), session_date=session_date)
    generated = cutoff_events(
        events,
        coalesced[0],
        session_date=session_date,
        source="watchdog",
        fence_token=1,
    )

    assert generated[0].kind is EventKind.SESSION_FLATTEN_OBSERVED
    assert generated[0].price_ticks == cutoff_bar.close_ticks
