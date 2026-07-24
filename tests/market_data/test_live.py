"""No-network contracts for the Databento live-trades boundary."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from stoic_derived.market_data.aggregate import AggregationSpec, MultiTimeframeAggregator
from stoic_derived.market_data.calendar import CmeEquityIndexCalendar
from stoic_derived.market_data.databento import (
    DbnMetadata,
    InstrumentMapping,
    normalize_trade_record,
)
from stoic_derived.market_data.live import (
    CONTINUOUS_SYMBOLS,
    DATASET,
    LIVE_SOURCE,
    SCHEMA,
    STYPE_IN,
    DatabentoLiveAdapter,
    LiveAdapterError,
    LiveStatusKind,
)
from stoic_derived.market_data.model import FinalBar, ResumeCursor, Timeframe


@dataclass(frozen=True, slots=True)
class FakeMapping:
    instrument_id: int
    stype_in_symbol: str
    stype_out_symbol: str


@dataclass(frozen=True, slots=True)
class FakeTrade:
    publisher_id: int
    instrument_id: int
    ts_event: int
    ts_recv: int
    price: int
    size: int
    action: str = "T"
    side: str = "A"
    flags: int = 0
    depth: int = 0
    sequence: int = 1


@dataclass(frozen=True, slots=True)
class FakeSystem:
    msg: str
    code: int = 0
    ts_event: int = 100

    def is_heartbeat(self) -> bool:
        return self.code == 0


@dataclass(frozen=True, slots=True)
class FakeError:
    err: str
    code: int = 6
    is_last: bool = True


class FakeLiveClient:
    def __init__(self) -> None:
        self.subscriptions: list[dict[str, object]] = []
        self.stopped = False
        self.records: list[object] = []

    def subscribe(self, **kwargs: object) -> int:
        self.subscriptions.append(kwargs)
        return len(self.subscriptions)

    def stop(self) -> None:
        self.stopped = True

    def __iter__(self) -> Iterator[object]:
        return iter(self.records)


class FakeLiveFactory:
    def __init__(self) -> None:
        self.keys: list[str | None] = []
        self.clients: list[FakeLiveClient] = []

    def __call__(self, key: str | None) -> FakeLiveClient:
        self.keys.append(key)
        client = FakeLiveClient()
        self.clients.append(client)
        return client


def test_live_adapter_subscribes_only_to_the_fixed_continuous_trade_stream() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory, key="db-secret")

    adapter.open_session(start_ns=123)

    assert factory.clients[0].subscriptions == [
        {
            "dataset": DATASET,
            "schema": SCHEMA,
            "symbols": CONTINUOUS_SYMBOLS,
            "stype_in": STYPE_IN,
            "start": 123,
        }
    ]
    assert "db-secret" not in repr(adapter)


def test_live_session_requires_mapping_before_normalizing_a_trade() -> None:
    adapter = DatabentoLiveAdapter(client_factory=FakeLiveFactory())
    session = adapter.open_session()

    with pytest.raises(LiveAdapterError, match="SymbolMappingMsg"):
        session.process(
            FakeTrade(
                publisher_id=1,
                instrument_id=100,
                ts_event=10,
                ts_recv=11,
                price=20_000_000_000_000,
                size=1,
            )
        )


def test_live_session_normalizes_only_after_a_supported_continuous_mapping() -> None:
    adapter = DatabentoLiveAdapter(client_factory=FakeLiveFactory())
    session = adapter.open_session()

    mapping = session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    trade = session.process(
        FakeTrade(
            publisher_id=1,
            instrument_id=100,
            ts_event=10,
            ts_recv=11,
            price=20_000_250_000_000,
            size=2,
            sequence=3,
        )
    )

    assert mapping.status is not None
    assert mapping.status.kind is LiveStatusKind.SYMBOL_MAPPING
    assert trade.trade is not None
    assert trade.trade.instrument.root == "NQ"
    assert trade.trade.price_ticks == 80_001


def test_live_and_historical_adapters_produce_the_same_canonical_trade() -> None:
    record = FakeTrade(
        publisher_id=1,
        instrument_id=100,
        ts_event=10,
        ts_recv=11,
        price=20_000_250_000_000,
        size=2,
        sequence=3,
    )
    metadata = DbnMetadata(
        path=Path("fixture.dbn.zst"),
        dataset=DATASET,
        start_ns=0,
        end_ns=100,
        mappings=(
            InstrumentMapping(
                root="NQ",
                instrument_id=100,
                start_date=date(1970, 1, 1),
                end_date=date(1970, 1, 2),
            ),
        ),
    )
    historical = normalize_trade_record(record, metadata=metadata)
    session = DatabentoLiveAdapter(client_factory=FakeLiveFactory()).open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    live = session.process(record)

    assert live.trade is not None
    assert live.trade.canonical_bytes() == historical.canonical_bytes()


def test_resume_filter_discards_only_previously_seen_timestamp_counts_not_identical_records() -> (
    None
):
    adapter = DatabentoLiveAdapter(client_factory=FakeLiveFactory())
    session = adapter.open_session(
        cursors=(
            ResumeCursor(
                source=LIVE_SOURCE,
                instrument_id=100,
                ts_event_ns=20,
                records_at_timestamp=2,
            ),
        )
    )
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    records = [
        FakeTrade(1, 100, 19, 19, 20_000_000_000_000, 1),
        FakeTrade(1, 100, 20, 20, 20_000_000_000_000, 1),
        FakeTrade(1, 100, 20, 20, 20_000_000_000_000, 1),
        FakeTrade(1, 100, 20, 20, 20_000_000_000_000, 1),
        FakeTrade(1, 100, 21, 21, 20_000_000_000_000, 1),
    ]

    results = [session.process(record) for record in records]
    for result in results:
        if result.trade is not None:
            session.ack(result.trade)

    assert [result.dropped_replay for result in results] == [True, True, True, False, False]
    assert [result.trade.ts_event_ns for result in results if result.trade] == [20, 21]
    assert session.cursors == (
        ResumeCursor(
            source=LIVE_SOURCE,
            instrument_id=100,
            ts_event_ns=21,
            records_at_timestamp=1,
        ),
    )


def test_system_and_error_records_become_secret_safe_statuses() -> None:
    secret = "db-super-secret"
    adapter = DatabentoLiveAdapter(client_factory=FakeLiveFactory(), key=secret)
    session = adapter.open_session()

    heartbeat = session.process(FakeSystem("quiet", code=0))
    error = session.process(FakeError(f"gateway unavailable: {secret}"))

    assert heartbeat.status is not None
    assert heartbeat.status.kind is LiveStatusKind.HEARTBEAT
    assert heartbeat.status.source_progress_ns == 100
    assert error.status is not None
    assert error.status.kind is LiveStatusKind.ERROR
    assert secret not in repr(heartbeat.status)
    assert secret not in repr(error.status)


def test_skipped_records_halt_the_session_until_cursor_recovery() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    accepted = session.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))
    assert accepted.trade is not None
    session.ack(accepted.trade)

    gap = session.process(FakeError("slow reader dropped records", code=7))

    assert gap.status is not None
    assert gap.status.kind is LiveStatusKind.HARD_GAP
    assert session.is_halted is True
    with pytest.raises(LiveAdapterError, match="halted"):
        session.process(FakeTrade(1, 100, 31, 32, 20_000_000_000_000, 1))

    recovered = adapter.reconnect(session)
    assert factory.clients[1].subscriptions[0]["start"] == 30
    assert recovered.is_halted is False


def test_halted_session_without_replay_point_requires_explicit_backfill() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session()
    session.process(FakeError("slow reader dropped records", code=7))

    with pytest.raises(LiveAdapterError, match="backfill"):
        adapter.reconnect(session)
    assert factory.clients[0].stopped is False


def test_continuous_roll_requires_a_new_session_and_fresh_mapping() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))

    with pytest.raises(LiveAdapterError, match="new session"):
        session.process(FakeMapping(101, "NQ.c.0", "NQU6"))

    rolled = adapter.resubscribe_for_continuous_roll(session)

    assert factory.clients[0].stopped is True
    assert len(factory.clients) == 2
    with pytest.raises(LiveAdapterError, match="SymbolMappingMsg"):
        rolled.process(FakeTrade(1, 101, 30, 30, 20_000_000_000_000, 1))


def test_roll_refuses_to_discard_an_unacknowledged_old_contract_trade() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    pending = session.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))
    assert pending.trade is not None

    with pytest.raises(LiveAdapterError, match="acknowledgement"):
        adapter.resubscribe_for_continuous_roll(session)

    assert session.pending_ack_count == 1
    assert factory.clients[0].stopped is False


def test_heartbeat_progress_can_finalize_a_quiet_bar_without_vendor_types() -> None:
    start = 1_780_876_200_000_000_000  # 2026-06-07 22:30 UTC
    session = DatabentoLiveAdapter(client_factory=FakeLiveFactory()).open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    normalized = session.process(FakeTrade(1, 100, start + 1, start + 2, 20_000_000_000_000, 1))
    assert normalized.trade is not None
    calendar = CmeEquityIndexCalendar(
        version="test",
        coverage_start=date(2026, 6, 1),
        coverage_end=date(2026, 6, 15),
        provenance=("test-fixture",),
    )
    aggregator = MultiTimeframeAggregator(
        calendar,
        AggregationSpec(timeframes=(Timeframe.ONE_MINUTE,)),
    )
    assert aggregator.push(normalized.trade).bars == ()
    minute_end = start + 60_000_000_000

    heartbeat = session.process(FakeSystem("quiet", code=0, ts_event=minute_end))
    assert heartbeat.status is not None
    bars: list[FinalBar] = []
    for progress in session.watermarks(heartbeat.status):
        bars.extend(
            aggregator.advance_watermark(
                progress.root,
                progress.instrument_id,
                progress.watermark_ns,
            ).bars
        )

    assert len(bars) == 1
    assert bars[0].end_ns == minute_end


def test_reconnect_uses_the_lowest_inclusive_cursor_timestamp_across_instruments() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session(
        cursors=(
            ResumeCursor(LIVE_SOURCE, 200, 50, 1),
            ResumeCursor(LIVE_SOURCE, 100, 40, 2),
        )
    )

    adapter.reconnect(session)

    assert factory.clients[0].stopped is True
    assert factory.clients[1].subscriptions[0]["start"] == 40


def test_reconnect_replays_an_unacknowledged_trade_when_no_cursor_exists() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    result = session.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))
    assert result.trade is not None
    assert not session.cursors

    adapter.reconnect(session)

    assert factory.clients[1].subscriptions[0]["start"] == 30


def test_reconnect_starts_before_an_older_unacked_other_instrument_trade() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    session = adapter.open_session(cursors=(ResumeCursor(LIVE_SOURCE, 200, 100, 1),))
    session.process(FakeMapping(200, "ES.c.0", "ESM6"))
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    pending = session.process(FakeTrade(1, 100, 90, 91, 20_000_000_000_000, 1))
    assert pending.trade is not None

    recovered = adapter.reconnect(session)

    assert factory.clients[1].subscriptions[0]["start"] == 90
    assert recovered.cursors == (ResumeCursor(LIVE_SOURCE, 200, 100, 1),)


def test_new_roll_mapping_retires_the_old_contract_cursor() -> None:
    factory = FakeLiveFactory()
    adapter = DatabentoLiveAdapter(client_factory=factory)
    original = adapter.open_session()
    original.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    first = original.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))
    assert first.trade is not None
    original.ack(first.trade)

    rolled = adapter.resubscribe_for_continuous_roll(original)
    rolled.process(FakeMapping(101, "NQ.c.0", "NQU6"))
    next_trade = rolled.process(FakeTrade(1, 101, 40, 41, 20_000_250_000_000, 1))
    assert next_trade.trade is not None
    rolled.ack(next_trade.trade)

    adapter.reconnect(rolled)

    assert rolled.cursors == (ResumeCursor(LIVE_SOURCE, 101, 40, 1),)
    assert factory.clients[2].subscriptions[0]["start"] == 40


def test_live_session_advances_the_cursor_only_after_downstream_acknowledges_trade() -> None:
    adapter = DatabentoLiveAdapter(client_factory=FakeLiveFactory())
    session = adapter.open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    result = session.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))

    assert session.cursors == ()
    assert result.trade is not None
    cursor = session.ack(result.trade)

    assert cursor == ResumeCursor(LIVE_SOURCE, 100, 30, 1)
    assert list(session.cursors) == [cursor]
    with pytest.raises(LiveAdapterError, match="uncommitted"):
        session.ack(result.trade)


def test_live_session_rejects_ack_for_a_trade_it_did_not_emit() -> None:
    session = DatabentoLiveAdapter(client_factory=FakeLiveFactory()).open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))
    result = session.process(FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1))
    assert result.trade is not None
    forged = type(result.trade)(
        source=result.trade.source,
        instrument=result.trade.instrument,
        publisher_id=result.trade.publisher_id,
        instrument_id=result.trade.instrument_id,
        ts_event_ns=result.trade.ts_event_ns + 1,
        ts_recv_ns=result.trade.ts_recv_ns + 1,
        price_ticks=result.trade.price_ticks,
        size=result.trade.size,
        action=result.trade.action,
        aggressor_side=result.trade.aggressor_side,
        flags=result.trade.flags,
        depth=result.trade.depth,
        sequence=result.trade.sequence,
    )

    with pytest.raises(LiveAdapterError, match="uncommitted"):
        session.ack(forged)


def test_live_session_iterates_fake_client_records_without_sdk_types() -> None:
    factory = FakeLiveFactory()
    session = DatabentoLiveAdapter(client_factory=factory).open_session()
    factory.clients[0].records = [
        FakeMapping(100, "NQ.c.0", "NQM6"),
        FakeTrade(1, 100, 30, 31, 20_000_000_000_000, 1),
    ]

    results = tuple(session.results())

    assert results[0].status is not None
    assert results[1].trade is not None


def test_live_session_rejects_receive_time_before_event_time() -> None:
    session = DatabentoLiveAdapter(client_factory=FakeLiveFactory()).open_session()
    session.process(FakeMapping(100, "NQ.c.0", "NQM6"))

    with pytest.raises(LiveAdapterError, match="ts_recv"):
        session.process(FakeTrade(1, 100, 31, 30, 20_000_000_000_000, 1))
