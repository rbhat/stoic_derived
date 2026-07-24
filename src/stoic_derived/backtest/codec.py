"""Strict, content-addressed JSONL codec for immutable SP1/SP2 batches.

This module deliberately knows only the public immutable market and alignment
contracts.  It neither reads raw DBN nor accepts paths, strategy material, or
engine objects.  Consequently a batch identity describes market evidence, not
where that evidence happened to be stored or how a strategy may use it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date
from hashlib import sha256
from typing import Any, NoReturn, Protocol, cast

from stoic_derived.market_data.model import (
    FinalBar,
    InstrumentSpec,
    QualityState,
    Timeframe,
    canonical_json_bytes,
)
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import CoverageGap, MarketLineage

BATCH_CODEC_SCHEMA_VERSION = "backtest-batch/v1"


class CodecError(ValueError):
    """Raised when external batch evidence is malformed or non-canonical."""


class _Readable(Protocol):
    def read(self) -> str | bytes: ...


def batch_projection(batch: FinalizedSeriesBatch) -> dict[str, object]:
    """Return the complete SP3-owned canonical projection of one batch."""
    if not isinstance(batch, FinalizedSeriesBatch):
        raise CodecError("batch must be a FinalizedSeriesBatch")
    return {
        "bars": [bar.canonical_dict() for bar in batch.bars],
        "finalized_through_ns": batch.finalized_through_ns,
        "gaps": [gap.canonical_dict() for gap in batch.gaps],
        "lineage": batch.lineage.canonical_dict(),
        "schema_version": BATCH_CODEC_SCHEMA_VERSION,
    }


def canonical_batch_bytes(batch: FinalizedSeriesBatch) -> bytes:
    """Encode a batch as canonical UTF-8 JSON used for its stable identity."""
    return canonical_json_bytes(batch_projection(batch))


def batch_identity(batch: FinalizedSeriesBatch) -> str:
    """Return the SHA-256 identity of the complete canonical batch evidence."""
    return sha256(canonical_batch_bytes(batch)).hexdigest()


def batch_order_key(batch: FinalizedSeriesBatch) -> tuple[int, str, bytes]:
    """Return the only permitted caller-input ordering key."""
    if not isinstance(batch, FinalizedSeriesBatch):
        raise CodecError("batch must be a FinalizedSeriesBatch")
    return (batch.finalized_through_ns, batch.lineage.identity, canonical_batch_bytes(batch))


def normalize_batches(batches: Iterable[FinalizedSeriesBatch]) -> tuple[FinalizedSeriesBatch, ...]:
    """Validate caller order and remove only exact, adjacent replay duplicates.

    This function intentionally does not sort.  A caller that supplies a
    descending or otherwise non-canonical sequence has lost provenance order,
    so accepting it after a convenient sort would hide an unsafe replay.
    """
    accepted: list[FinalizedSeriesBatch] = []
    previous_key: tuple[int, str, bytes] | None = None
    per_lineage_watermark: dict[str, int] = {}
    bars_by_interval: dict[tuple[str, str, int, int], str] = {}
    gaps_by_interval: dict[tuple[str, str, int, int], str] = {}
    seen_identities: set[str] = set()

    for batch in batches:
        if not isinstance(batch, FinalizedSeriesBatch):
            raise CodecError("batches must contain FinalizedSeriesBatch values")
        key = batch_order_key(batch)
        if previous_key is not None and key < previous_key:
            raise CodecError("batches must be in canonical input order")
        previous_key = key

        lineage_identity = batch.lineage.identity
        previous_watermark = per_lineage_watermark.get(lineage_identity)
        if previous_watermark is not None and batch.finalized_through_ns < previous_watermark:
            raise CodecError("per-lineage finalized watermark regressed")
        per_lineage_watermark[lineage_identity] = batch.finalized_through_ns

        identity = batch_identity(batch)
        if identity in seen_identities:
            continue
        _validate_nonconflicting_intervals(batch, bars_by_interval, gaps_by_interval)
        seen_identities.add(identity)
        accepted.append(batch)
    return tuple(accepted)


def _validate_nonconflicting_intervals(
    batch: FinalizedSeriesBatch,
    bars_by_interval: dict[tuple[str, str, int, int], str],
    gaps_by_interval: dict[tuple[str, str, int, int], str],
) -> None:
    lineage_identity = batch.lineage.identity
    for bar in batch.bars:
        key = (lineage_identity, bar.timeframe.value, bar.start_ns, bar.end_ns)
        existing = bars_by_interval.setdefault(key, bar.identity)
        if existing != bar.identity:
            raise CodecError("conflicting bars share a physical lineage timeframe interval")
    for gap in batch.gaps:
        key = (lineage_identity, gap.timeframe.value, gap.start_ns, gap.end_ns)
        existing = gaps_by_interval.setdefault(key, gap.identity)
        if existing != gap.identity:
            raise CodecError("conflicting gaps share a physical lineage timeframe interval")


def encode_batch_jsonl(batches: Iterable[FinalizedSeriesBatch]) -> bytes:
    """Encode strictly ordered batches as canonical newline-delimited JSON."""
    normalized = normalize_batches(batches)
    if not normalized:
        return b""
    return b"\n".join(canonical_batch_bytes(batch) for batch in normalized) + b"\n"


def decode_batch(value: str | bytes | Mapping[str, object]) -> FinalizedSeriesBatch:
    """Decode and validate one batch record, including all nested SP1/SP2 data."""
    payload = _load_json_object(value)
    _require_exact_fields(
        payload,
        {"bars", "finalized_through_ns", "gaps", "lineage", "schema_version"},
        "batch",
    )
    if (
        _require_string(payload["schema_version"], "batch.schema_version")
        != BATCH_CODEC_SCHEMA_VERSION
    ):
        raise CodecError("unsupported batch schema_version")
    lineage = _decode_lineage(payload["lineage"], "batch.lineage")
    finalized_through_ns = _require_nonnegative_int(
        payload["finalized_through_ns"], "batch.finalized_through_ns"
    )
    bars_value = payload["bars"]
    gaps_value = payload["gaps"]
    if not isinstance(bars_value, list):
        raise CodecError("batch.bars must be an array")
    if not isinstance(gaps_value, list):
        raise CodecError("batch.gaps must be an array")
    bars = tuple(_decode_bar(item, f"batch.bars[{index}]") for index, item in enumerate(bars_value))
    gaps = tuple(
        _decode_gap(item, lineage, f"batch.gaps[{index}]") for index, item in enumerate(gaps_value)
    )
    try:
        batch = FinalizedSeriesBatch(lineage, finalized_through_ns, bars, gaps)
    except ValueError as exc:
        raise CodecError(f"invalid finalized series batch: {exc}") from exc

    # FinalizedSeriesBatch safely canonicalizes its internals for SP2.  External
    # evidence must already be canonical, otherwise accepting it would silently
    # rewrite a caller's claimed historical ordering or duplicate records.
    if tuple(bar.identity for bar in bars) != tuple(bar.identity for bar in batch.bars):
        raise CodecError("batch.bars must be complete, unique, and canonical-order")
    if tuple(gap.identity for gap in gaps) != tuple(gap.identity for gap in batch.gaps):
        raise CodecError("batch.gaps must be unique and canonical-order")
    if payload != batch_projection(batch):
        raise CodecError("batch is not the exact canonical projection")
    return batch


def decode_batches_jsonl(value: str | bytes) -> tuple[FinalizedSeriesBatch, ...]:
    """Decode a canonical batch JSONL document and preserve caller order."""
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CodecError("batch JSONL must be UTF-8") from exc
    elif isinstance(value, str):
        text = value
    else:
        raise CodecError("batch JSONL must be str or bytes")
    if not text:
        return ()
    if not text.endswith("\n"):
        raise CodecError("batch JSONL must end with a newline")
    lines = text.split("\n")[:-1]
    if any(not line for line in lines):
        raise CodecError("batch JSONL cannot contain blank lines")
    decoded = tuple(decode_batch(line) for line in lines)
    if any(
        line.encode("utf-8") != canonical_batch_bytes(batch)
        for line, batch in zip(lines, decoded, strict=True)
    ):
        raise CodecError("batch JSONL records must use exact canonical encoding")
    return normalize_batches(decoded)


def read_batches_jsonl(stream: _Readable) -> tuple[FinalizedSeriesBatch, ...]:
    """Read JSONL from an already-open stream; paths never enter an identity."""
    if not hasattr(stream, "read"):
        raise CodecError("stream must provide read()")
    value = stream.read()
    if not isinstance(value, (str, bytes)):
        raise CodecError("stream.read() must return str or bytes")
    return decode_batches_jsonl(value)


# Readable aliases for the two common plural spellings.  They intentionally
# share the same implementation so both keep the exact fail-closed semantics.
encode_batches_jsonl = encode_batch_jsonl
decode_batch_jsonl = decode_batches_jsonl


def _load_json_object(value: str | bytes | Mapping[str, object]) -> dict[str, object]:
    if isinstance(value, Mapping):
        raw: object = dict(value)
    else:
        if isinstance(value, bytes):
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise CodecError("batch JSON must be UTF-8") from exc
        elif isinstance(value, str):
            text = value
        else:
            raise CodecError("batch JSON must be str, bytes, or a mapping")
        try:
            raw = json.loads(
                text,
                object_pairs_hook=_no_duplicate_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, CodecError):
                raise
            raise CodecError("invalid batch JSON") from exc
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise CodecError("batch JSON must be an object with string keys")
    return cast(dict[str, object], raw)


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CodecError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise CodecError(f"non-finite JSON number is forbidden: {value}")


def _decode_lineage(value: object, name: str) -> MarketLineage:
    payload = _require_mapping(value, name)
    _require_exact_fields(
        payload,
        {
            "aggregation_fingerprint",
            "calendar_fingerprint",
            "continuous_symbol",
            "instrument_id",
            "market_data_schema",
            "root",
            "source",
        },
        name,
    )
    try:
        return MarketLineage(
            source=_require_string(payload["source"], f"{name}.source"),
            root=_require_string(payload["root"], f"{name}.root"),
            continuous_symbol=_require_string(
                payload["continuous_symbol"], f"{name}.continuous_symbol"
            ),
            instrument_id=_require_positive_int(payload["instrument_id"], f"{name}.instrument_id"),
            calendar_fingerprint=_require_string(
                payload["calendar_fingerprint"], f"{name}.calendar_fingerprint"
            ),
            aggregation_fingerprint=_require_string(
                payload["aggregation_fingerprint"], f"{name}.aggregation_fingerprint"
            ),
            market_data_schema=_require_string(
                payload["market_data_schema"], f"{name}.market_data_schema"
            ),
        )
    except ValueError as exc:
        raise CodecError(f"invalid {name}: {exc}") from exc


def _decode_bar(value: object, name: str) -> FinalBar:
    payload = _require_mapping(value, name)
    _require_exact_fields(
        payload,
        {
            "aggregation_fingerprint",
            "calendar_fingerprint",
            "close_ticks",
            "continuous_symbol",
            "end_ns",
            "first_event_ns",
            "high_ticks",
            "instrument_id",
            "last_event_ns",
            "low_ticks",
            "open_ticks",
            "quality",
            "root",
            "schema_version",
            "source",
            "start_ns",
            "timeframe",
            "trade_count",
            "trading_date",
            "volume",
        },
        name,
    )
    trading_date_value = payload["trading_date"]
    if trading_date_value is None:
        trading_date: date | None = None
    else:
        text = _require_string(trading_date_value, f"{name}.trading_date")
        try:
            trading_date = date.fromisoformat(text)
        except ValueError as exc:
            raise CodecError(f"{name}.trading_date must be ISO-8601") from exc
        if trading_date.isoformat() != text:
            raise CodecError(f"{name}.trading_date must be canonical ISO-8601")
    try:
        return FinalBar(
            source=_require_string(payload["source"], f"{name}.source"),
            instrument=InstrumentSpec(
                root=_require_string(payload["root"], f"{name}.root"),
                continuous_symbol=_require_string(
                    payload["continuous_symbol"], f"{name}.continuous_symbol"
                ),
            ),
            instrument_id=_require_positive_int(payload["instrument_id"], f"{name}.instrument_id"),
            timeframe=Timeframe(_require_string(payload["timeframe"], f"{name}.timeframe")),
            calendar_fingerprint=_require_string(
                payload["calendar_fingerprint"], f"{name}.calendar_fingerprint"
            ),
            aggregation_fingerprint=_require_string(
                payload["aggregation_fingerprint"], f"{name}.aggregation_fingerprint"
            ),
            start_ns=_require_nonnegative_int(payload["start_ns"], f"{name}.start_ns"),
            end_ns=_require_nonnegative_int(payload["end_ns"], f"{name}.end_ns"),
            trading_date=trading_date,
            open_ticks=_require_positive_int(payload["open_ticks"], f"{name}.open_ticks"),
            high_ticks=_require_positive_int(payload["high_ticks"], f"{name}.high_ticks"),
            low_ticks=_require_positive_int(payload["low_ticks"], f"{name}.low_ticks"),
            close_ticks=_require_positive_int(payload["close_ticks"], f"{name}.close_ticks"),
            volume=_require_positive_int(payload["volume"], f"{name}.volume"),
            trade_count=_require_positive_int(payload["trade_count"], f"{name}.trade_count"),
            first_event_ns=_require_nonnegative_int(
                payload["first_event_ns"], f"{name}.first_event_ns"
            ),
            last_event_ns=_require_nonnegative_int(
                payload["last_event_ns"], f"{name}.last_event_ns"
            ),
            quality=QualityState(_require_string(payload["quality"], f"{name}.quality")),
            schema_version=_require_string(payload["schema_version"], f"{name}.schema_version"),
        )
    except ValueError as exc:
        raise CodecError(f"invalid {name}: {exc}") from exc


def _decode_gap(value: object, lineage: MarketLineage, name: str) -> CoverageGap:
    payload = _require_mapping(value, name)
    _require_exact_fields(payload, {"end_ns", "lineage", "reason", "start_ns", "timeframe"}, name)
    gap_lineage = _decode_lineage(payload["lineage"], f"{name}.lineage")
    if gap_lineage != lineage:
        raise CodecError(f"{name}.lineage must equal batch.lineage")
    try:
        return CoverageGap(
            lineage=gap_lineage,
            timeframe=Timeframe(_require_string(payload["timeframe"], f"{name}.timeframe")),
            start_ns=_require_nonnegative_int(payload["start_ns"], f"{name}.start_ns"),
            end_ns=_require_nonnegative_int(payload["end_ns"], f"{name}.end_ns"),
            reason=_require_string(payload["reason"], f"{name}.reason"),
        )
    except ValueError as exc:
        raise CodecError(f"invalid {name}: {exc}") from exc


def _require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise CodecError(f"{name} must be an object with string keys")
    return cast(dict[str, object], value)


def _require_exact_fields(value: Mapping[str, object], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unknown {', '.join(extra)}")
        raise CodecError(f"{name} fields are invalid: {'; '.join(detail)}")


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CodecError(f"{name} must be a non-empty string")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CodecError(f"{name} must be a non-negative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CodecError(f"{name} must be a positive integer")
    return value


__all__ = [
    "BATCH_CODEC_SCHEMA_VERSION",
    "CodecError",
    "batch_identity",
    "batch_order_key",
    "batch_projection",
    "canonical_batch_bytes",
    "decode_batch",
    "decode_batch_jsonl",
    "decode_batches_jsonl",
    "encode_batch_jsonl",
    "encode_batches_jsonl",
    "normalize_batches",
    "read_batches_jsonl",
]
