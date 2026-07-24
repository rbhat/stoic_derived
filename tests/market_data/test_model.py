"""SP1 immutable market-data contract tests."""

from __future__ import annotations

from datetime import date

import pytest

from stoic_derived.market_data.model import (
    NANOS_PER_TICK,
    FinalBar,
    InstrumentSpec,
    IssueCode,
    MarketDataIssue,
    MarketDataValidationError,
    QualityState,
    ResumeCursor,
    Timeframe,
    TradeEvent,
)


def test_trade_event_serializes_exact_tick_values_with_a_stable_identity() -> None:
    instrument = InstrumentSpec(root="NQ", continuous_symbol="NQ.c.0")
    event = TradeEvent(
        source="historical",
        instrument=instrument,
        publisher_id=1,
        instrument_id=101,
        ts_event_ns=1_700_000_000_000_000_001,
        ts_recv_ns=1_700_000_000_000_000_123,
        price_ticks=80_001,
        size=3,
        action="trade",
        aggressor_side="bid",
        flags=0,
        depth=0,
        sequence=7,
    )

    assert NANOS_PER_TICK == 250_000_000
    assert event.price_nanos == 20_000_250_000_000
    assert event.canonical_bytes() == (
        b'{"action":"trade","aggressor_side":"bid","continuous_symbol":"NQ.c.0",'
        b'"depth":0,"flags":0,"instrument_id":101,"price_ticks":80001,'
        b'"publisher_id":1,"root":"NQ","schema_version":"market-data/v1",'
        b'"sequence":7,"size":3,"source":"historical",'
        b'"ts_event_ns":1700000000000000001,"ts_recv_ns":1700000000000000123}'
    )
    assert event.identity == "03aa78a1cfd272e6ea451acb57bec815d1ab94d98c545d35ba23a8fee66ba5da"
    assert Timeframe.ONE_MINUTE.value == "1m"


@pytest.mark.parametrize(
    ("root", "symbol", "message"),
    [
        ("CL", "CL.c.0", "root"),
        ("NQ", "ES.c.0", "continuous_symbol"),
    ],
)
def test_instrument_spec_rejects_non_v1_roots_and_symbols(
    root: str, symbol: str, message: str
) -> None:
    with pytest.raises(MarketDataValidationError, match=message):
        InstrumentSpec(root=root, continuous_symbol=symbol)


def test_trade_event_rejects_nonpositive_size() -> None:
    instrument = InstrumentSpec(root="ES", continuous_symbol="ES.c.0")

    with pytest.raises(MarketDataValidationError, match="size"):
        TradeEvent(
            source="live",
            instrument=instrument,
            publisher_id=1,
            instrument_id=102,
            ts_event_ns=1,
            ts_recv_ns=1,
            price_ticks=20_000,
            size=0,
            action="trade",
            aggressor_side="none",
            flags=0,
            depth=0,
            sequence=1,
        )


def test_final_bar_issue_and_cursor_are_immutable_canonical_value_objects() -> None:
    instrument = InstrumentSpec(root="ES", continuous_symbol="ES.c.0")
    bar = FinalBar(
        source="historical",
        instrument=instrument,
        instrument_id=102,
        timeframe=Timeframe.DAILY,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        start_ns=1_000,
        end_ns=2_000,
        trading_date=date(2026, 3, 9),
        open_ticks=20_000,
        high_ticks=20_004,
        low_ticks=19_999,
        close_ticks=20_001,
        volume=5,
        trade_count=2,
        first_event_ns=1_100,
        last_event_ns=1_900,
        quality=QualityState.COMPLETE,
    )
    issue = MarketDataIssue(
        code=IssueCode.LATE_EVENT_AFTER_FINALIZATION,
        source="live",
        detail="event was behind the watermark",
        instrument_id=102,
        ts_event_ns=2_000,
    )
    cursor = ResumeCursor(
        source="live",
        instrument_id=102,
        ts_event_ns=2_000,
        records_at_timestamp=3,
    )

    assert b'"timeframe":"D"' in bar.canonical_bytes()
    assert len(bar.identity) == 64
    assert len(bar.series_id) == 64
    assert issue.canonical_dict()["code"] == "late_event_after_finalization"
    assert cursor.canonical_dict()["records_at_timestamp"] == 3
    with pytest.raises(AttributeError):
        cursor.instrument_id = 103  # type: ignore[misc]


def test_final_bar_rejects_non_string_fingerprint_without_a_type_error() -> None:
    instrument = InstrumentSpec(root="ES", continuous_symbol="ES.c.0")
    with pytest.raises(MarketDataValidationError, match="aggregation_fingerprint"):
        FinalBar(
            source="databento:GLBX.MDP3:trades",
            instrument=instrument,
            instrument_id=102,
            timeframe=Timeframe.ONE_MINUTE,
            calendar_fingerprint="a" * 64,
            aggregation_fingerprint=1,  # type: ignore[arg-type]
            start_ns=1_000,
            end_ns=2_000,
            trading_date=None,
            open_ticks=20_000,
            high_ticks=20_000,
            low_ticks=20_000,
            close_ticks=20_000,
            volume=1,
            trade_count=1,
            first_event_ns=1_100,
            last_event_ns=1_100,
        )
