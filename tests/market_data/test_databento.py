"""Tests for the strict, streaming historical Databento adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from stoic_derived.market_data.databento import (
    CANONICAL_SOURCE,
    CoverageGapError,
    CoverageOverlapError,
    DbnMetadataError,
    inspect_dbn,
    iter_historical_trades,
    normalize_trade_record,
    plan_coverage,
)
from stoic_derived.market_data.model import MarketDataValidationError


@dataclass(frozen=True, slots=True)
class FakeMetadata:
    version: int
    dataset: str
    schema: str
    stype_in: str
    stype_out: str
    symbols: list[str]
    mappings: dict[str, list[dict[str, object]]]
    start: int
    end: int
    partial: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    ts_out: bool = False


@dataclass(frozen=True, slots=True)
class FakeRecord:
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


@dataclass(slots=True)
class FakeStore:
    metadata: FakeMetadata
    records: list[FakeRecord]


class FakeStoreFactory:
    def __init__(self, stores: dict[Path, FakeStore]) -> None:
        self.stores = stores
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> FakeStore:
        self.calls.append(path)
        return self.stores[path]


def metadata(
    *,
    start: int = 100,
    end: int = 200,
    roots: tuple[str, ...] = ("NQ",),
) -> FakeMetadata:
    symbols = [f"{root}.c.0" for root in roots]
    mappings = {
        symbol: [
            {
                "start_date": date(1970, 1, 1),
                "end_date": date(2100, 1, 1),
                "symbol": str(10_000 + index),
            }
        ]
        for index, symbol in enumerate(symbols)
    }
    return FakeMetadata(
        version=1,
        dataset="GLBX.MDP3",
        schema="trades",
        stype_in="continuous",
        stype_out="instrument_id",
        symbols=symbols,
        mappings=mappings,
        start=start,
        end=end,
    )


def test_inspect_dbn_parses_strict_metadata_and_root_mappings() -> None:
    path = Path("main.dbn.zst")
    store_factory = FakeStoreFactory(
        {path: FakeStore(metadata(start=10, end=20, roots=("NQ", "ES")), [])}
    )

    inspected = inspect_dbn(path, store_factory=store_factory)

    assert inspected.dataset == "GLBX.MDP3"
    assert inspected.start_ns == 10
    assert inspected.end_ns == 20
    assert inspected.instrument_for(10_000).root == "NQ"
    assert inspected.instrument_for(10_001).continuous_symbol == "ES.c.0"
    assert store_factory.calls == [path]


def test_inspect_dbn_rejects_unknown_symbols_and_incomplete_mappings() -> None:
    path = Path("bad.dbn.zst")
    base = metadata()
    unknown = FakeMetadata(
        version=base.version,
        dataset=base.dataset,
        schema=base.schema,
        stype_in=base.stype_in,
        stype_out=base.stype_out,
        symbols=["CL.c.0"],
        mappings={"CL.c.0": base.mappings["NQ.c.0"]},
        start=base.start,
        end=base.end,
    )

    with pytest.raises(DbnMetadataError, match="symbol"):
        inspect_dbn(path, store_factory=FakeStoreFactory({path: FakeStore(unknown, [])}))

    incomplete_base = metadata()
    incomplete = FakeMetadata(
        version=incomplete_base.version,
        dataset=incomplete_base.dataset,
        schema=incomplete_base.schema,
        stype_in=incomplete_base.stype_in,
        stype_out=incomplete_base.stype_out,
        symbols=incomplete_base.symbols,
        mappings={},
        start=incomplete_base.start,
        end=incomplete_base.end,
    )
    with pytest.raises(DbnMetadataError, match="mapping"):
        inspect_dbn(path, store_factory=FakeStoreFactory({path: FakeStore(incomplete, [])}))

    extra_base = metadata()
    extra_base.mappings["ES.c.0"] = extra_base.mappings["NQ.c.0"]
    with pytest.raises(DbnMetadataError, match="exactly match"):
        inspect_dbn(path, store_factory=FakeStoreFactory({path: FakeStore(extra_base, [])}))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("partial", ["NQ.c.0"], "partial"),
        ("not_found", ["ES.c.0"], "not_found"),
        ("ts_out", True, "ts_out"),
    ],
)
def test_inspect_dbn_rejects_incomplete_or_unexpected_timestamp_metadata(
    field: str, value: object, message: str
) -> None:
    path = Path("unsafe.dbn.zst")
    source = metadata()
    if isinstance(value, list):
        getattr(source, field).extend(value)
    else:
        object.__setattr__(source, field, value)

    with pytest.raises(DbnMetadataError, match=message):
        inspect_dbn(path, store_factory=FakeStoreFactory({path: FakeStore(source, [])}))


def test_coverage_plan_drops_wholly_contained_root_coverage_and_rejects_partial_overlap() -> None:
    main_path = Path("main.dbn.zst")
    redundant_path = Path("redundant.dbn.zst")
    partial_path = Path("partial.dbn.zst")
    store_factory = FakeStoreFactory(
        {
            main_path: FakeStore(metadata(start=0, end=100, roots=("NQ", "ES")), []),
            redundant_path: FakeStore(metadata(start=20, end=80), []),
            partial_path: FakeStore(metadata(start=90, end=120), []),
        }
    )
    main = inspect_dbn(main_path, store_factory=store_factory)
    redundant = inspect_dbn(redundant_path, store_factory=store_factory)
    partial = inspect_dbn(partial_path, store_factory=store_factory)

    plan = plan_coverage((main, redundant))
    reverse_plan = plan_coverage((redundant, main))

    assert [(item.path, item.root, item.start_ns, item.end_ns) for item in plan] == [
        (main_path, "ES", 0, 100),
        (main_path, "NQ", 0, 100),
    ]
    assert reverse_plan == plan
    with pytest.raises(CoverageOverlapError, match="partial overlap"):
        plan_coverage((main, partial))


def test_normalizer_requires_exact_fixed_point_ticks_and_preserves_transport_multiplicity() -> None:
    path = Path("tail.dbn.zst")
    record = FakeRecord(
        publisher_id=1,
        instrument_id=10_000,
        ts_event=101,
        ts_recv=103,
        price=20_000_250_000_000,
        size=3,
        sequence=8,
    )
    store_factory = FakeStoreFactory({path: FakeStore(metadata(), [record, record])})
    inspected = inspect_dbn(path, store_factory=store_factory)

    event = normalize_trade_record(record, metadata=inspected)
    events = tuple(iter_historical_trades(plan_coverage((inspected,)), store_factory=store_factory))

    assert event.source == CANONICAL_SOURCE
    assert event.price_ticks == 80_001
    assert event.aggressor_side == "ask"
    assert len(events) == 2
    assert events[0].canonical_bytes() == events[1].canonical_bytes()
    with pytest.raises(MarketDataValidationError, match="tick"):
        normalize_trade_record(
            FakeRecord(1, 10_000, 101, 103, 20_000_125_000_000, 3), metadata=inspected
        )


def test_historical_iteration_is_bounded_and_filters_to_selected_coverage() -> None:
    path = Path("tail.dbn.zst")
    records = [
        FakeRecord(1, 10_000, 100, 100, 20_000_000_000_000, 1, sequence=1),
        FakeRecord(1, 10_000, 101, 101, 20_000_250_000_000, 2, sequence=2),
        FakeRecord(1, 10_000, 102, 102, 20_000_500_000_000, 3, sequence=3),
    ]
    store_factory = FakeStoreFactory({path: FakeStore(metadata(start=101, end=103), records)})
    inspected = inspect_dbn(path, store_factory=store_factory)

    events = tuple(
        iter_historical_trades(plan_coverage((inspected,)), store_factory=store_factory, limit=1)
    )

    assert [event.ts_event_ns for event in events] == [101]
    with pytest.raises(MarketDataValidationError, match="limit"):
        tuple(
            iter_historical_trades(
                plan_coverage((inspected,)), store_factory=store_factory, limit=0
            )
        )


def test_normalizer_rejects_an_event_outside_its_mapped_instrument_interval() -> None:
    path = Path("expired-map.dbn.zst")
    source = metadata()
    source.mappings["NQ.c.0"][0]["end_date"] = date(1970, 1, 2)
    record = FakeRecord(1, 10_000, 172_800_000_000_000, 172_800_000_000_000, 20_000_000_000_000, 1)
    inspected = inspect_dbn(path, store_factory=FakeStoreFactory({path: FakeStore(source, [])}))

    with pytest.raises(DbnMetadataError, match="does not cover event date"):
        normalize_trade_record(record, metadata=inspected)


def test_normalizer_rejects_receive_time_before_event_time() -> None:
    path = Path("bad-time.dbn.zst")
    inspected = inspect_dbn(
        path,
        store_factory=FakeStoreFactory({path: FakeStore(metadata(), [])}),
    )

    with pytest.raises(MarketDataValidationError, match="ts_recv"):
        normalize_trade_record(
            FakeRecord(1, 10_000, 102, 101, 20_000_000_000_000, 1),
            metadata=inspected,
        )


def test_coverage_plan_orders_selected_slices_by_time_not_path() -> None:
    late_path = Path("a-late.dbn.zst")
    early_path = Path("z-early.dbn.zst")
    store_factory = FakeStoreFactory(
        {
            late_path: FakeStore(
                metadata(start=200, end=300),
                [FakeRecord(1, 10_000, 200, 200, 20_000_000_000_000, 1)],
            ),
            early_path: FakeStore(
                metadata(start=100, end=200),
                [FakeRecord(1, 10_000, 100, 100, 20_000_000_000_000, 1)],
            ),
        }
    )
    late = inspect_dbn(late_path, store_factory=store_factory)
    early = inspect_dbn(early_path, store_factory=store_factory)

    plan = plan_coverage((late, early))

    assert [(slice_.path, slice_.start_ns) for slice_ in plan] == [
        (early_path, 100),
        (late_path, 200),
    ]
    events = tuple(iter_historical_trades(plan, store_factory=store_factory))
    assert [event.ts_event_ns for event in events] == [100, 200]


def test_coverage_plan_rejects_a_gap_between_supplied_sources() -> None:
    first_path = Path("first.dbn.zst")
    second_path = Path("second.dbn.zst")
    store_factory = FakeStoreFactory(
        {
            first_path: FakeStore(metadata(start=100, end=200), []),
            second_path: FakeStore(metadata(start=201, end=300), []),
        }
    )
    first = inspect_dbn(first_path, store_factory=store_factory)
    second = inspect_dbn(second_path, store_factory=store_factory)

    with pytest.raises(CoverageGapError, match="coverage gap") as captured:
        plan_coverage((first, second))
    assert captured.value.issue.code.value == "missing_coverage"


@pytest.mark.skipif(
    os.getenv("STOIC_RUN_DBN_SMOKE") != "1",
    reason="requires the local gitignored Databento tail archive",
)
def test_actual_tail_file_normalizes_a_bounded_tick_exact_sample() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    tail = (
        repository_root
        / "data/historical/GLBX.MDP3__NQ__2026-06-06__2026-06-10T16:45:00.trades.dbn.zst"
    )
    inspected = inspect_dbn(tail)
    events = tuple(iter_historical_trades(plan_coverage((inspected,)), limit=1_000))

    assert len(events) == 1_000
    assert {event.instrument.root for event in events} == {"NQ"}
    assert all(event.source == CANONICAL_SOURCE for event in events)
    assert all(event.price_nanos % event.instrument.tick_nanos == 0 for event in events)
