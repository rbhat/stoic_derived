from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest

from stoic_derived.market_data.model import (
    FinalBar,
    InstrumentSpec,
    QualityState,
    Timeframe,
)
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import (
    CoverageGap,
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
)

FINGERPRINT = "a" * 64
BASE_NS = 1_768_500_000_000_000_000

type SignalFactory = Callable[..., SignalRecord]
type BarFactory = Callable[..., FinalBar]
type BatchFactory = Callable[..., FinalizedSeriesBatch]


@pytest.fixture
def lineage() -> MarketLineage:
    return MarketLineage(
        source="market-test",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=101,
        calendar_fingerprint=FINGERPRINT,
        aggregation_fingerprint=FINGERPRINT,
        market_data_schema="market-data/v1",
    )


@pytest.fixture
def make_signal(lineage: MarketLineage) -> SignalFactory:
    def factory(
        *,
        signal_type: SignalType = SignalType.SCALP,
        direction: Direction = Direction.LONG,
        signal_ts_ns: int = BASE_NS,
        selected_lineage: MarketLineage = lineage,
    ) -> SignalRecord:
        if direction is Direction.LONG:
            entry_ticks, stop_ticks, target_ticks = 100, 90, 120
        else:
            entry_ticks, stop_ticks, target_ticks = 100, 110, 80
        return SignalRecord(
            signal_type=signal_type,
            direction=direction,
            entry_ticks=entry_ticks,
            stop_ticks=stop_ticks,
            target_ticks=target_ticks,
            risk_reward=RationalR.from_prices(direction, entry_ticks, stop_ticks, target_ticks),
            setup_type=SetupType.BREAK_AND_RETEST,
            entry_model="planned_touch",
            confidence=80,
            signal_ts_ns=signal_ts_ns,
            source="stoic-signal-engine/v1",
            release_file_sha256="b" * 64,
            rulebook_version="test/v1",
            rule_id=f"{signal_type.value.lower()}-{direction.value}",
            engine_version="signal-engine/v1",
            lineage=selected_lineage,
            causal_bar_ids=("c" * 64,),
        )

    return factory


@pytest.fixture
def make_bar(lineage: MarketLineage) -> BarFactory:
    def factory(
        *,
        timeframe: Timeframe = Timeframe.FIVE_MINUTES,
        end_ns: int = BASE_NS + 300_000_000_000,
        open_ticks: int = 100,
        high_ticks: int = 105,
        low_ticks: int = 95,
        close_ticks: int = 101,
        quality: QualityState = QualityState.COMPLETE,
        selected_lineage: MarketLineage = lineage,
    ) -> FinalBar:
        duration = timeframe.duration_ns or 86_400_000_000_000
        start_ns = end_ns - duration
        return FinalBar(
            source=selected_lineage.source,
            instrument=InstrumentSpec(selected_lineage.root, selected_lineage.continuous_symbol),
            instrument_id=selected_lineage.instrument_id,
            timeframe=timeframe,
            calendar_fingerprint=selected_lineage.calendar_fingerprint,
            aggregation_fingerprint=selected_lineage.aggregation_fingerprint,
            start_ns=start_ns,
            end_ns=end_ns,
            trading_date=date(2026, 1, 15) if timeframe.is_session_based else None,
            open_ticks=open_ticks,
            high_ticks=high_ticks,
            low_ticks=low_ticks,
            close_ticks=close_ticks,
            volume=10,
            trade_count=2,
            first_event_ns=start_ns,
            last_event_ns=end_ns - 1,
            quality=quality,
        )

    return factory


@pytest.fixture
def make_batch(lineage: MarketLineage) -> BatchFactory:
    def factory(
        *,
        bars: tuple[FinalBar, ...] = (),
        gaps: tuple[CoverageGap, ...] = (),
        finalized_through_ns: int | None = None,
        selected_lineage: MarketLineage = lineage,
    ) -> FinalizedSeriesBatch:
        latest = max([bar.end_ns for bar in bars] + [gap.end_ns for gap in gaps] + [BASE_NS])
        return FinalizedSeriesBatch(
            selected_lineage,
            latest if finalized_through_ns is None else finalized_through_ns,
            bars,
            gaps,
        )

    return factory
