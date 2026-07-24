"""Strict, streaming adapter for local Databento DBN trade archives.

The adapter is intentionally limited to normalizing vendor records at the
boundary.  It does not aggregate, deduplicate, repair, or reorder trades.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

from .model import (
    NANOS_PER_TICK,
    InstrumentSpec,
    IssueCode,
    MarketDataIssue,
    MarketDataValidationError,
    TradeEvent,
)

CANONICAL_SOURCE = "databento:GLBX.MDP3:trades"
DATASET = "GLBX.MDP3"
SCHEMA = "trades"
STYPE_IN = "continuous"
STYPE_OUT = "instrument_id"
COVERAGE_PRECEDENCE = "widest-coverage-then-path/v1"
_RECORD_CHUNK_BYTES = 64 * 1024


class DbnMetadataError(MarketDataValidationError):
    """Raised when a DBN archive cannot be safely identified or mapped."""


class CoverageOverlapError(MarketDataValidationError):
    """Raised when selected root coverage would be ambiguous."""


class CoverageGapError(MarketDataValidationError):
    """Raised with a typed issue when supplied sources leave missing coverage."""

    def __init__(self, root: str, start_ns: int, end_ns: int) -> None:
        self.issue = MarketDataIssue(
            code=IssueCode.MISSING_COVERAGE,
            source=CANONICAL_SOURCE,
            detail=f"coverage gap for {root}: [{start_ns}, {end_ns})",
        )
        super().__init__(self.issue.detail)


class StoreFactory(Protocol):
    """The small DBN-store surface used by metadata inspection."""

    def __call__(self, path: Path) -> Any: ...


@dataclass(frozen=True, slots=True)
class InstrumentMapping:
    """One continuous-symbol mapping interval from DBN metadata."""

    root: str
    instrument_id: int
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class DbnMetadata:
    """Validated metadata plus the exact root/instrument lookup for one source."""

    path: Path
    dataset: str
    start_ns: int
    end_ns: int
    mappings: tuple[InstrumentMapping, ...]

    @property
    def roots(self) -> tuple[str, ...]:
        return tuple(sorted({mapping.root for mapping in self.mappings}))

    def instrument_for(
        self, instrument_id: int, *, ts_event_ns: int | None = None
    ) -> InstrumentSpec:
        candidates = [
            mapping for mapping in self.mappings if mapping.instrument_id == instrument_id
        ]
        if not candidates:
            raise DbnMetadataError(f"instrument_id {instrument_id} has no DBN root mapping")
        if ts_event_ns is not None:
            event_date = date(1970, 1, 1) + timedelta(days=ts_event_ns // 86_400_000_000_000)
            if not any(
                mapping.start_date <= event_date < mapping.end_date for mapping in candidates
            ):
                raise DbnMetadataError(
                    f"instrument_id {instrument_id} mapping does not cover event date {event_date}"
                )
        for mapping in candidates:
            if ts_event_ns is None or mapping.start_date <= event_date < mapping.end_date:
                return InstrumentSpec(mapping.root, f"{mapping.root}.c.0")
        raise DbnMetadataError(f"instrument_id {instrument_id} has no DBN root mapping")


@dataclass(frozen=True, slots=True)
class CoverageSlice:
    """An explicit source/root half-open interval selected for historical replay."""

    path: Path
    root: str
    start_ns: int
    end_ns: int
    metadata: DbnMetadata


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _metadata_value(metadata: object, name: str) -> object:
    if not hasattr(metadata, name):
        raise DbnMetadataError(f"DBN metadata is missing {name}")
    return _enum_value(getattr(metadata, name))


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DbnMetadataError(f"DBN metadata {name} must be a non-empty string")
    return value


def _require_ns(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DbnMetadataError(f"DBN metadata {name} must be a non-negative integer nanosecond")
    return value


def _root_from_symbol(symbol: object) -> str:
    text = _require_text(symbol, "symbol")
    root_by_symbol = {"NQ.c.0": "NQ", "ES.c.0": "ES"}
    try:
        return root_by_symbol[text]
    except KeyError as exc:
        raise DbnMetadataError(f"unsupported DBN continuous symbol: {text}") from exc


def _parse_mapping_interval(root: str, value: object) -> InstrumentMapping:
    if not isinstance(value, Mapping):
        raise DbnMetadataError(f"mapping for {root} must be a mapping")
    raw_id = value.get("symbol")
    if not isinstance(raw_id, str) or not raw_id.isdecimal() or int(raw_id) <= 0:
        raise DbnMetadataError(f"mapping for {root} has invalid instrument symbol")
    start_date = value.get("start_date")
    end_date = value.get("end_date")
    if not isinstance(start_date, date) or not isinstance(end_date, date) or start_date >= end_date:
        raise DbnMetadataError(f"mapping for {root} has an invalid date interval")
    return InstrumentMapping(
        root=root,
        instrument_id=int(raw_id),
        start_date=start_date,
        end_date=end_date,
    )


def _default_store_factory(path: Path) -> Any:
    from databento import DBNStore
    from databento_dbn import DBNError

    try:
        return DBNStore.from_file(path)
    except (OSError, DBNError) as exc:
        raise DbnMetadataError(f"failed to open DBN source {path}") from exc


def inspect_dbn(path: Path | str, *, store_factory: StoreFactory | None = None) -> DbnMetadata:
    """Validate DBN v1 trades metadata and return its complete NQ/ES mapping."""
    source_path = Path(path)
    store = (store_factory or _default_store_factory)(source_path)
    raw = getattr(store, "metadata", None)
    if raw is None:
        raise DbnMetadataError("DBN store has no metadata")
    version = _metadata_value(raw, "version")
    if version != 1:
        raise DbnMetadataError("DBN metadata version must be 1")
    if _metadata_value(raw, "dataset") != DATASET:
        raise DbnMetadataError(f"DBN dataset must be {DATASET}")
    if _metadata_value(raw, "schema") != SCHEMA:
        raise DbnMetadataError("DBN schema must be trades")
    if _metadata_value(raw, "stype_in") != STYPE_IN:
        raise DbnMetadataError("DBN input symbology must be continuous")
    if _metadata_value(raw, "stype_out") != STYPE_OUT:
        raise DbnMetadataError("DBN output symbology must be instrument_id")
    if _metadata_value(raw, "ts_out") is not False:
        raise DbnMetadataError("DBN ts_out must be false")
    for name in ("partial", "not_found"):
        value = _metadata_value(raw, name)
        if not isinstance(value, list) or value:
            raise DbnMetadataError(f"DBN metadata {name} must be an empty list")
    start_ns = _require_ns(_metadata_value(raw, "start"), "start")
    end_ns = _require_ns(_metadata_value(raw, "end"), "end")
    if start_ns >= end_ns:
        raise DbnMetadataError("DBN metadata coverage must be a non-empty interval")
    raw_symbols = _metadata_value(raw, "symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise DbnMetadataError("DBN metadata symbols must be a non-empty list")
    roots_by_symbol = {symbol: _root_from_symbol(symbol) for symbol in raw_symbols}
    if len(roots_by_symbol) != len(raw_symbols):
        raise DbnMetadataError("DBN metadata symbols must be unique")
    raw_mappings = _metadata_value(raw, "mappings")
    if not isinstance(raw_mappings, Mapping):
        raise DbnMetadataError("DBN metadata mappings must be a mapping")
    if set(raw_mappings) != set(raw_symbols):
        raise DbnMetadataError("DBN metadata mappings must exactly match requested symbols")
    mappings: list[InstrumentMapping] = []
    seen_ids: dict[int, str] = {}
    for symbol, root in roots_by_symbol.items():
        intervals = raw_mappings.get(symbol)
        if not isinstance(intervals, list) or not intervals:
            raise DbnMetadataError(f"DBN metadata mapping is missing for {symbol}")
        parsed_intervals = sorted(
            (_parse_mapping_interval(root, interval_value) for interval_value in intervals),
            key=lambda item: item.start_date,
        )
        for previous, current in pairwise(parsed_intervals):
            if previous.end_date != current.start_date:
                raise DbnMetadataError(f"mapping intervals for {symbol} must be contiguous")
        for interval in parsed_intervals:
            previous_root = seen_ids.setdefault(interval.instrument_id, root)
            if previous_root != root:
                raise DbnMetadataError("one instrument_id cannot map to multiple roots")
            mappings.append(interval)
    return DbnMetadata(
        path=source_path,
        dataset=DATASET,
        start_ns=start_ns,
        end_ns=end_ns,
        mappings=tuple(
            sorted(mappings, key=lambda item: (item.root, item.start_date, item.instrument_id))
        ),
    )


def plan_coverage(sources: Sequence[DbnMetadata]) -> tuple[CoverageSlice, ...]:
    """Apply input-order-independent widest-coverage/path precedence.

    Wholly contained source slices are redundant. Equal slices choose the
    lexicographically lowest path. Partial overlaps remain ambiguous and fail
    closed. Individual DBN records are deliberately never deduplicated.
    """
    candidates_by_key: dict[tuple[Path, str, int, int], CoverageSlice] = {}
    for source in sources:
        for root in source.roots:
            candidate = CoverageSlice(source.path, root, source.start_ns, source.end_ns, source)
            candidates_by_key[
                (candidate.path, candidate.root, candidate.start_ns, candidate.end_ns)
            ] = candidate
    candidates = tuple(candidates_by_key.values())
    for index, candidate in enumerate(candidates):
        for other in candidates[index + 1 :]:
            if candidate.root != other.root:
                continue
            overlaps = candidate.start_ns < other.end_ns and other.start_ns < candidate.end_ns
            candidate_contains = (
                candidate.start_ns <= other.start_ns and other.end_ns <= candidate.end_ns
            )
            other_contains = (
                other.start_ns <= candidate.start_ns and candidate.end_ns <= other.end_ns
            )
            if overlaps and not candidate_contains and not other_contains:
                raise CoverageOverlapError(
                    f"partial overlap for {candidate.root}: {candidate.path} "
                    f"[{candidate.start_ns}, {candidate.end_ns})"
                )

    selected: list[CoverageSlice] = []
    for candidate in candidates:
        suppress = False
        for other in candidates:
            if candidate is other or candidate.root != other.root:
                continue
            contains = other.start_ns <= candidate.start_ns and candidate.end_ns <= other.end_ns
            strictly_wider = other.start_ns < candidate.start_ns or candidate.end_ns < other.end_ns
            same_interval_precedes = (
                other.start_ns == candidate.start_ns
                and other.end_ns == candidate.end_ns
                and other.path.as_posix() < candidate.path.as_posix()
            )
            if contains and (strictly_wider or same_interval_precedes):
                suppress = True
                break
        if not suppress:
            selected.append(candidate)

    def sort_key(item: CoverageSlice) -> tuple[int, int, str, str]:
        return (item.start_ns, item.end_ns, item.path.as_posix(), item.root)

    ordered = tuple(sorted(selected, key=sort_key))
    by_root: defaultdict[str, list[CoverageSlice]] = defaultdict(list)
    for slice_ in ordered:
        by_root[slice_.root].append(slice_)
    for root, slices in by_root.items():
        for previous, current in pairwise(slices):
            if previous.end_ns < current.start_ns:
                raise CoverageGapError(root, previous.end_ns, current.start_ns)
    return ordered


def _record_value(record: object, name: str) -> object:
    if not hasattr(record, name):
        raise MarketDataValidationError(f"Databento trade record is missing {name}")
    return _enum_value(getattr(record, name))


def _record_int(record: object, name: str, *, positive: bool = False) -> int:
    value = _record_value(record, name)
    if not isinstance(value, int) or isinstance(value, bool):
        qualifier = "positive" if positive else "non-negative"
        raise MarketDataValidationError(f"Databento trade {name} must be a {qualifier} integer")
    if value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "non-negative"
        raise MarketDataValidationError(f"Databento trade {name} must be a {qualifier} integer")
    return value


def normalize_trade_record(record: object, *, metadata: DbnMetadata) -> TradeEvent:
    """Normalize one DBN fixed-point trade without float conversion or coercion."""
    instrument_id = _record_int(record, "instrument_id", positive=True)
    price_nanos = _record_int(record, "price", positive=True)
    if price_nanos % NANOS_PER_TICK:
        raise MarketDataValidationError("Databento trade price is not aligned to the NQ/ES tick")
    action = _record_value(record, "action")
    if action != "T":
        raise MarketDataValidationError("Databento record action must be T (trade)")
    side = _record_value(record, "side")
    sides = {"A": "ask", "B": "bid", "N": "none"}
    if side not in sides:
        raise MarketDataValidationError("Databento trade side is unsupported")
    ts_event_ns = _record_int(record, "ts_event")
    ts_recv_ns = _record_int(record, "ts_recv")
    if ts_recv_ns < ts_event_ns:
        raise MarketDataValidationError("Databento trade ts_recv must not precede ts_event")
    return TradeEvent(
        source=CANONICAL_SOURCE,
        instrument=metadata.instrument_for(instrument_id, ts_event_ns=ts_event_ns),
        publisher_id=_record_int(record, "publisher_id", positive=True),
        instrument_id=instrument_id,
        ts_event_ns=ts_event_ns,
        ts_recv_ns=ts_recv_ns,
        price_ticks=price_nanos // NANOS_PER_TICK,
        size=_record_int(record, "size", positive=True),
        action="trade",
        aggressor_side=sides[side],
        flags=_record_int(record, "flags"),
        depth=_record_int(record, "depth"),
        sequence=_record_int(record, "sequence"),
    )


def _iter_raw_records(path: Path) -> Iterator[object]:
    """Decode a compressed DBN source in bounded byte chunks."""
    import databento_dbn as dbn

    compression: Any = dbn.Compression.ZSTD
    try:
        decoder = dbn.DBNDecoder(compression=compression)
        with path.open("rb") as source:
            while chunk := source.read(_RECORD_CHUNK_BYTES):
                for record in decoder.write_and_decode(chunk):
                    # The decoder emits the DBN header metadata once before the
                    # records. The already-validated store metadata owns it.
                    if isinstance(record, dbn.TradeMsg):
                        yield record
    except (OSError, dbn.DBNError) as exc:
        raise DbnMetadataError(f"failed to decode DBN source {path}") from exc


def _records_for_store(store: object, path: Path) -> Iterable[object]:
    records = getattr(store, "records", None)
    if records is not None:
        if not isinstance(records, Iterable):
            raise DbnMetadataError("injected DBN store records must be iterable")
        return records
    return _iter_raw_records(path)


def iter_historical_trades(
    coverage: Sequence[CoverageSlice],
    *,
    store_factory: StoreFactory | None = None,
    limit: int | None = None,
) -> Iterator[TradeEvent]:
    """Yield only explicitly selected coverage, preserving every selected record."""
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
        raise MarketDataValidationError("limit must be a positive integer or None")
    slices_by_path: defaultdict[Path, list[CoverageSlice]] = defaultdict(list)
    for slice_ in coverage:
        slices_by_path[slice_.path].append(slice_)
    emitted = 0
    ordered_paths = sorted(
        slices_by_path,
        key=lambda path: (
            min(slice_.start_ns for slice_ in slices_by_path[path]),
            path.as_posix(),
        ),
    )
    for path in ordered_paths:
        store = (store_factory or _default_store_factory)(path)
        for record in _records_for_store(store, path):
            event = normalize_trade_record(record, metadata=slices_by_path[path][0].metadata)
            if not any(
                slice_.root == event.instrument.root
                and slice_.start_ns <= event.ts_event_ns < slice_.end_ns
                for slice_ in slices_by_path[path]
            ):
                continue
            yield event
            emitted += 1
            if limit is not None and emitted >= limit:
                return
