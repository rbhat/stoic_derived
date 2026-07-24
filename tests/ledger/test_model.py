from __future__ import annotations

from dataclasses import replace

import pytest

from stoic_derived.ledger.model import (
    EventKind,
    LedgerError,
    LedgerEvent,
    LedgerLimits,
    signal_sha256,
    source_partition,
)
from stoic_derived.signal_engine.model import SignalType


def test_signal_event_is_content_addressed_and_observational(make_signal) -> None:
    signal = make_signal()

    first = LedgerEvent.for_signal(signal, source="writer-a")
    replay = LedgerEvent.for_signal(signal, source="writer-a")

    assert first == replay
    assert first.event_id == replay.event_id
    assert first.canonical_dict()["execution"] is False
    assert first.canonical_dict()["orders_placed"] == 0
    assert first.canonical_dict()["broker_fill_claimed"] is False


def test_different_sources_preserve_evidence_but_share_semantics(make_signal) -> None:
    signal = make_signal()

    first = LedgerEvent.for_signal(signal, source="writer-a")
    second = LedgerEvent.for_signal(signal, source="writer-b")

    assert first.event_id != second.event_id
    assert first.semantic_id == second.semantic_id
    assert first.source_partition == source_partition("writer-a")


def test_event_rejects_changed_signal_lineage(make_signal, lineage) -> None:
    signal = make_signal()

    with pytest.raises(LedgerError, match="lineage"):
        LedgerEvent(
            kind=EventKind.SIGNAL_OBSERVED,
            signal_type=SignalType.SCALP,
            signal_id=signal.signal_id,
            signal_sha256=signal_sha256(signal),
            lineage=replace(lineage, instrument_id=202),
            observed_ts_ns=signal.signal_ts_ns,
            source="writer",
            signal=signal,
        )


def test_non_cutoff_market_event_rejects_fence(make_signal, make_bar) -> None:
    signal = make_signal()
    root = LedgerEvent.for_signal(signal, source="writer")
    bar = make_bar()

    with pytest.raises(LedgerError, match="watchdog"):
        LedgerEvent.for_market(
            EventKind.ENTRY_OBSERVED,
            signal,
            predecessor_semantic_id=root.semantic_id,
            market_bar=bar,
            price_ticks=signal.entry_ticks,
            source="writer",
            fence_token=1,
        )


def test_limits_reject_download_bound_smaller_than_event_bound() -> None:
    with pytest.raises(LedgerError, match="max_download_bytes"):
        LedgerLimits(max_event_bytes=20, max_download_bytes=10)
