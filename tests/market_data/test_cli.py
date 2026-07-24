"""CLI projections for bounded market-data inspection and replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from stoic_derived.market_data.calendar import CmeEquityIndexCalendar
from stoic_derived.market_data.cli import inspect_paths, sample_paths
from stoic_derived.market_data.model import MarketDataValidationError


@dataclass(frozen=True, slots=True)
class FakeMetadata:
    version: int = 1
    dataset: str = "GLBX.MDP3"
    schema: str = "trades"
    stype_in: str = "continuous"
    stype_out: str = "instrument_id"
    symbols: list[str] = field(default_factory=lambda: ["NQ.c.0"])
    mappings: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: {
            "NQ.c.0": [
                {
                    "start_date": date(1970, 1, 1),
                    "end_date": date(2100, 1, 1),
                    "symbol": "101",
                }
            ]
        }
    )
    start: int = 1_780_876_800_000_000_000
    end: int = 1_780_876_920_000_000_000
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


class FakeFactory:
    def __init__(self, path: Path, store: FakeStore) -> None:
        self.path = path
        self.store = store

    def __call__(self, path: Path) -> FakeStore:
        assert path == self.path
        return self.store


def test_inspect_paths_projects_validated_metadata_and_coverage() -> None:
    path = Path("tail.dbn.zst")
    factory = FakeFactory(path, FakeStore(FakeMetadata(), []))

    payload = inspect_paths((path,), store_factory=factory)

    assert payload["coverage"] == [
        {
            "end_ns": 1_780_876_920_000_000_000,
            "path": "tail.dbn.zst",
            "root": "NQ",
            "start_ns": 1_780_876_800_000_000_000,
        }
    ]


def test_sample_paths_normalizes_and_builds_all_six_timeframes() -> None:
    path = Path("tail.dbn.zst")
    start = 1_780_876_800_000_000_000  # 2026-06-08 00:00 UTC, regular session
    records = [
        FakeRecord(1, 101, start + 1, start + 2, 29_083_500_000_000, 3, sequence=1),
        FakeRecord(
            1,
            101,
            start + 60_000_000_001,
            start + 60_000_000_002,
            29_082_500_000_000,
            1,
            sequence=2,
        ),
    ]
    factory = FakeFactory(path, FakeStore(FakeMetadata(), records))

    payload = sample_paths(
        (path,),
        record_limit=2,
        store_factory=factory,
        calendar=CmeEquityIndexCalendar(
            version="test",
            coverage_start=date(2026, 6, 1),
            coverage_end=date(2026, 6, 15),
            provenance=("test-fixture",),
        ),
    )

    bars = payload["bars"]
    assert isinstance(bars, list)
    assert payload["event_count"] == 2
    assert {bar["timeframe"] for bar in bars} == {"1m", "5m", "15m", "60m", "D", "W"}
    assert all(len(bar["bar_id"]) == 64 and len(bar["series_id"]) == 64 for bar in bars)
    assert payload["issues"] == []


def test_helpers_reject_empty_paths_and_boolean_record_limits() -> None:
    with pytest.raises(MarketDataValidationError, match="path"):
        inspect_paths(())
    with pytest.raises(MarketDataValidationError, match="record_limit"):
        sample_paths((Path("unused"),), record_limit=True)
