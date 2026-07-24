"""Strict canonical JSON codec for immutable ledger event objects."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any, NoReturn, cast

from stoic_derived.market_data.model import (
    FinalBar,
    InstrumentSpec,
    QualityState,
    Timeframe,
)
from stoic_derived.signal_engine.model import (
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
)

from .model import EventKind, LedgerError, LedgerEvent, LedgerLimits


class LedgerCodecError(LedgerError):
    """Raised when external event bytes are not exact canonical evidence."""


_EVENT_FIELDS = {
    "broker_fill_claimed",
    "event_id",
    "event_kind",
    "execution",
    "fence_token",
    "lineage",
    "market_bar",
    "observed_ts_ns",
    "orders_placed",
    "predecessor_semantic_id",
    "price_ticks",
    "reason",
    "schema_version",
    "semantic_id",
    "signal",
    "signal_id",
    "signal_sha256",
    "signal_type",
    "source",
    "source_partition",
}

_SIGNAL_FIELDS = {
    "causal_bar_ids",
    "confidence",
    "direction",
    "engine_version",
    "entry_model",
    "entry_ticks",
    "lineage",
    "release_file_sha256",
    "risk_reward",
    "rule_id",
    "rulebook_version",
    "schema_version",
    "setup_type",
    "signal_id",
    "signal_ts_ns",
    "signal_type",
    "source",
    "stop_ticks",
    "target_ticks",
    "timeframe_plan",
}

_LINEAGE_FIELDS = {
    "aggregation_fingerprint",
    "calendar_fingerprint",
    "continuous_symbol",
    "instrument_id",
    "market_data_schema",
    "root",
    "source",
}

_BAR_FIELDS = {
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
}


def decode_event(
    value: str | bytes | Mapping[str, object],
    *,
    limits: LedgerLimits | None = None,
) -> LedgerEvent:
    """Decode one exact canonical event and rederive every claimed identity."""
    selected_limits = limits or LedgerLimits()
    if isinstance(value, bytes) and len(value) > selected_limits.max_event_bytes:
        raise LedgerCodecError("event exceeds max_event_bytes")
    if isinstance(value, str) and len(value.encode("utf-8")) > selected_limits.max_event_bytes:
        raise LedgerCodecError("event exceeds max_event_bytes")
    payload = _load_object(value)
    _require_fields(payload, _EVENT_FIELDS, "event")
    if payload["execution"] is not False:
        raise LedgerCodecError("event.execution must be false")
    if payload["orders_placed"] != 0 or isinstance(payload["orders_placed"], bool):
        raise LedgerCodecError("event.orders_placed must be zero")
    if payload["broker_fill_claimed"] is not False:
        raise LedgerCodecError("event.broker_fill_claimed must be false")

    signal_value = payload["signal"]
    signal = None if signal_value is None else _decode_signal(signal_value, "event.signal")
    bar_value = payload["market_bar"]
    market_bar = None if bar_value is None else _decode_bar(bar_value, "event.market_bar")
    try:
        event = LedgerEvent(
            kind=EventKind(_string(payload["event_kind"], "event.event_kind")),
            signal_type=SignalType(_string(payload["signal_type"], "event.signal_type")),
            signal_id=_string(payload["signal_id"], "event.signal_id"),
            signal_sha256=_string(payload["signal_sha256"], "event.signal_sha256"),
            lineage=_decode_lineage(payload["lineage"], "event.lineage"),
            observed_ts_ns=_nonnegative_int(payload["observed_ts_ns"], "event.observed_ts_ns"),
            source=_string(payload["source"], "event.source"),
            predecessor_semantic_id=_optional_string(
                payload["predecessor_semantic_id"], "event.predecessor_semantic_id"
            ),
            signal=signal,
            market_bar=market_bar,
            price_ticks=_optional_positive_int(payload["price_ticks"], "event.price_ticks"),
            reason=_optional_string(payload["reason"], "event.reason"),
            fence_token=_optional_positive_int(payload["fence_token"], "event.fence_token"),
            schema_version=_string(payload["schema_version"], "event.schema_version"),
        )
    except (ValueError, TypeError) as exc:
        raise LedgerCodecError(f"invalid ledger event: {exc}") from exc

    if _string(payload["semantic_id"], "event.semantic_id") != event.semantic_id:
        raise LedgerCodecError("event.semantic_id does not match canonical content")
    if _string(payload["event_id"], "event.event_id") != event.event_id:
        raise LedgerCodecError("event.event_id does not match canonical content")
    if _string(payload["source_partition"], "event.source_partition") != event.source_partition:
        raise LedgerCodecError("event.source_partition does not match source")
    if payload != event.canonical_dict():
        raise LedgerCodecError("event is not the exact canonical projection")
    if len(event.canonical_bytes()) > selected_limits.max_event_bytes:
        raise LedgerCodecError("event exceeds max_event_bytes")
    return event


def encode_events_jsonl(
    events: Iterable[LedgerEvent],
    *,
    limits: LedgerLimits | None = None,
) -> bytes:
    """Encode a canonical event set ordered by event identity."""
    selected_limits = limits or LedgerLimits()
    by_id: dict[str, LedgerEvent] = {}
    for event in events:
        if not isinstance(event, LedgerEvent):
            raise LedgerCodecError("events must contain LedgerEvent values")
        existing = by_id.setdefault(event.event_id, event)
        if existing.canonical_bytes() != event.canonical_bytes():
            raise LedgerCodecError("event_id collision with different bytes")
    if len(by_id) > selected_limits.max_events_per_reconcile:
        raise LedgerCodecError("event count exceeds max_events_per_reconcile")
    ordered = tuple(by_id[event_id] for event_id in sorted(by_id))
    if not ordered:
        return b""
    for event in ordered:
        if len(event.canonical_bytes()) > selected_limits.max_event_bytes:
            raise LedgerCodecError("event exceeds max_event_bytes")
    return b"\n".join(event.canonical_bytes() for event in ordered) + b"\n"


def decode_events_jsonl(
    value: str | bytes,
    *,
    limits: LedgerLimits | None = None,
) -> tuple[LedgerEvent, ...]:
    """Decode exact canonical event JSONL and reject silent reordering."""
    selected_limits = limits or LedgerLimits()
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LedgerCodecError("event JSONL must be UTF-8") from exc
    elif isinstance(value, str):
        text = value
    else:
        raise LedgerCodecError("event JSONL must be str or bytes")
    if not text:
        return ()
    if not text.endswith("\n"):
        raise LedgerCodecError("event JSONL must end with a newline")
    lines = text.splitlines()
    if any(not line for line in lines):
        raise LedgerCodecError("event JSONL cannot contain blank lines")
    if len(lines) > selected_limits.max_events_per_reconcile:
        raise LedgerCodecError("event count exceeds max_events_per_reconcile")
    events = tuple(decode_event(line, limits=selected_limits) for line in lines)
    expected = tuple(sorted(events, key=lambda event: event.event_id))
    if events != expected:
        raise LedgerCodecError("events must be ordered by event_id")
    if len({event.event_id for event in events}) != len(events):
        raise LedgerCodecError("event JSONL cannot repeat event IDs")
    if any(
        line.encode("utf-8") != event.canonical_bytes()
        for line, event in zip(lines, events, strict=True)
    ):
        raise LedgerCodecError("event JSONL must use exact canonical encoding")
    return events


def _decode_signal(value: object, name: str) -> SignalRecord:
    payload = _mapping(value, name)
    _require_fields(payload, _SIGNAL_FIELDS, name)
    risk = _mapping(payload["risk_reward"], f"{name}.risk_reward")
    _require_fields(risk, {"decimal", "denominator", "numerator"}, f"{name}.risk_reward")
    plan = _mapping(payload["timeframe_plan"], f"{name}.timeframe_plan")
    _require_fields(
        plan,
        {"execute", "htf", "manage", "setup", "signal_type"},
        f"{name}.timeframe_plan",
    )
    causal = payload["causal_bar_ids"]
    if not isinstance(causal, list):
        raise LedgerCodecError(f"{name}.causal_bar_ids must be an array")
    try:
        signal = SignalRecord(
            signal_type=SignalType(_string(payload["signal_type"], f"{name}.signal_type")),
            direction=Direction(_string(payload["direction"], f"{name}.direction")),
            entry_ticks=_positive_int(payload["entry_ticks"], f"{name}.entry_ticks"),
            stop_ticks=_positive_int(payload["stop_ticks"], f"{name}.stop_ticks"),
            target_ticks=_positive_int(payload["target_ticks"], f"{name}.target_ticks"),
            risk_reward=RationalR(
                numerator=_positive_int(risk["numerator"], f"{name}.risk_reward.numerator"),
                denominator=_positive_int(risk["denominator"], f"{name}.risk_reward.denominator"),
            ),
            setup_type=SetupType(_string(payload["setup_type"], f"{name}.setup_type")),
            entry_model=_string(payload["entry_model"], f"{name}.entry_model"),
            confidence=_nonnegative_int(payload["confidence"], f"{name}.confidence"),
            signal_ts_ns=_nonnegative_int(payload["signal_ts_ns"], f"{name}.signal_ts_ns"),
            source=_string(payload["source"], f"{name}.source"),
            release_file_sha256=_string(
                payload["release_file_sha256"], f"{name}.release_file_sha256"
            ),
            rulebook_version=_string(payload["rulebook_version"], f"{name}.rulebook_version"),
            rule_id=_string(payload["rule_id"], f"{name}.rule_id"),
            engine_version=_string(payload["engine_version"], f"{name}.engine_version"),
            lineage=_decode_lineage(payload["lineage"], f"{name}.lineage"),
            causal_bar_ids=tuple(
                _string(item, f"{name}.causal_bar_ids[{index}]")
                for index, item in enumerate(causal)
            ),
            schema_version=_string(payload["schema_version"], f"{name}.schema_version"),
        )
    except (ValueError, TypeError) as exc:
        raise LedgerCodecError(f"invalid {name}: {exc}") from exc
    if payload != signal.canonical_dict():
        raise LedgerCodecError(f"{name} is not the exact canonical signal projection")
    return signal


def _decode_lineage(value: object, name: str) -> MarketLineage:
    payload = _mapping(value, name)
    _require_fields(payload, _LINEAGE_FIELDS, name)
    try:
        return MarketLineage(
            source=_string(payload["source"], f"{name}.source"),
            root=_string(payload["root"], f"{name}.root"),
            continuous_symbol=_string(payload["continuous_symbol"], f"{name}.continuous_symbol"),
            instrument_id=_positive_int(payload["instrument_id"], f"{name}.instrument_id"),
            calendar_fingerprint=_string(
                payload["calendar_fingerprint"], f"{name}.calendar_fingerprint"
            ),
            aggregation_fingerprint=_string(
                payload["aggregation_fingerprint"], f"{name}.aggregation_fingerprint"
            ),
            market_data_schema=_string(payload["market_data_schema"], f"{name}.market_data_schema"),
        )
    except (ValueError, TypeError) as exc:
        raise LedgerCodecError(f"invalid {name}: {exc}") from exc


def _decode_bar(value: object, name: str) -> FinalBar:
    payload = _mapping(value, name)
    _require_fields(payload, _BAR_FIELDS, name)
    trading_value = payload["trading_date"]
    if trading_value is None:
        trading_date = None
    else:
        trading_text = _string(trading_value, f"{name}.trading_date")
        try:
            trading_date = date.fromisoformat(trading_text)
        except ValueError as exc:
            raise LedgerCodecError(f"{name}.trading_date must be ISO-8601") from exc
        if trading_date.isoformat() != trading_text:
            raise LedgerCodecError(f"{name}.trading_date must be canonical ISO-8601")
    try:
        bar = FinalBar(
            source=_string(payload["source"], f"{name}.source"),
            instrument=InstrumentSpec(
                root=_string(payload["root"], f"{name}.root"),
                continuous_symbol=_string(
                    payload["continuous_symbol"], f"{name}.continuous_symbol"
                ),
            ),
            instrument_id=_positive_int(payload["instrument_id"], f"{name}.instrument_id"),
            timeframe=Timeframe(_string(payload["timeframe"], f"{name}.timeframe")),
            calendar_fingerprint=_string(
                payload["calendar_fingerprint"], f"{name}.calendar_fingerprint"
            ),
            aggregation_fingerprint=_string(
                payload["aggregation_fingerprint"], f"{name}.aggregation_fingerprint"
            ),
            start_ns=_nonnegative_int(payload["start_ns"], f"{name}.start_ns"),
            end_ns=_nonnegative_int(payload["end_ns"], f"{name}.end_ns"),
            trading_date=trading_date,
            open_ticks=_positive_int(payload["open_ticks"], f"{name}.open_ticks"),
            high_ticks=_positive_int(payload["high_ticks"], f"{name}.high_ticks"),
            low_ticks=_positive_int(payload["low_ticks"], f"{name}.low_ticks"),
            close_ticks=_positive_int(payload["close_ticks"], f"{name}.close_ticks"),
            volume=_positive_int(payload["volume"], f"{name}.volume"),
            trade_count=_positive_int(payload["trade_count"], f"{name}.trade_count"),
            first_event_ns=_nonnegative_int(payload["first_event_ns"], f"{name}.first_event_ns"),
            last_event_ns=_nonnegative_int(payload["last_event_ns"], f"{name}.last_event_ns"),
            quality=QualityState(_string(payload["quality"], f"{name}.quality")),
            schema_version=_string(payload["schema_version"], f"{name}.schema_version"),
        )
    except (ValueError, TypeError) as exc:
        raise LedgerCodecError(f"invalid {name}: {exc}") from exc
    if payload != bar.canonical_dict():
        raise LedgerCodecError(f"{name} is not the exact canonical bar projection")
    return bar


def _load_object(value: str | bytes | Mapping[str, object]) -> dict[str, object]:
    if isinstance(value, Mapping):
        raw: object = dict(value)
    else:
        if isinstance(value, bytes):
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LedgerCodecError("event JSON must be UTF-8") from exc
        elif isinstance(value, str):
            text = value
        else:
            raise LedgerCodecError("event JSON must be str, bytes, or mapping")
        try:
            raw = json.loads(
                text,
                object_pairs_hook=_no_duplicate_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, LedgerCodecError):
                raise
            raise LedgerCodecError("invalid event JSON") from exc
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise LedgerCodecError("event JSON must be an object with string keys")
    return cast(dict[str, object], raw)


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerCodecError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise LedgerCodecError(f"non-finite JSON number is forbidden: {value}")


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise LedgerCodecError(f"{name} must be an object with string keys")
    return cast(dict[str, object], value)


def _require_fields(payload: Mapping[str, object], expected: set[str], name: str) -> None:
    actual = set(payload)
    if actual == expected:
        return
    details: list[str] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if extra:
        details.append(f"unknown {', '.join(extra)}")
    raise LedgerCodecError(f"{name} fields are invalid: {'; '.join(details)}")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerCodecError(f"{name} must be a non-empty string")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LedgerCodecError(f"{name} must be a non-negative integer")
    return value


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LedgerCodecError(f"{name} must be a positive integer")
    return value


def _optional_positive_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


__all__ = [
    "LedgerCodecError",
    "decode_event",
    "decode_events_jsonl",
    "encode_events_jsonl",
]
