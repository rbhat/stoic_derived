"""Immutable, fixed-point contracts shared by SP1, SP2, and SP3."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from typing import Any, TypeGuard

SCHEMA_VERSION = "market-data/v1"
NANOS_PER_TICK = 250_000_000


class MarketDataValidationError(ValueError):
    """Raised when data cannot safely enter the deterministic market-data path."""


class UnsupportedCalendarRangeError(MarketDataValidationError):
    """Raised when a trading date is outside a reviewed calendar horizon."""

    def __init__(self, trading_date: date, reason: str | None = None) -> None:
        self.trading_date = trading_date
        detail = reason or "calendar does not cover"
        super().__init__(f"{detail} trading date {trading_date.isoformat()}")


class Timeframe(StrEnum):
    """The complete Vision-pinned bar vocabulary."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    SIXTY_MINUTES = "60m"
    DAILY = "D"
    WEEKLY = "W"

    @property
    def duration_ns(self) -> int | None:
        """Return an intraday bucket width; session bars have calendar-defined widths."""
        durations = {
            Timeframe.ONE_MINUTE: 60_000_000_000,
            Timeframe.FIVE_MINUTES: 300_000_000_000,
            Timeframe.FIFTEEN_MINUTES: 900_000_000_000,
            Timeframe.SIXTY_MINUTES: 3_600_000_000_000,
        }
        return durations.get(self)

    @property
    def is_session_based(self) -> bool:
        return self in {Timeframe.DAILY, Timeframe.WEEKLY}


class QualityState(StrEnum):
    """Quality of a finalized bar, never inferred from a missing bar."""

    COMPLETE = "complete"
    DEGRADED = "degraded"


class IssueCode(StrEnum):
    """Stable runtime facts that must not be silently repaired."""

    DUPLICATE_REPLAY_RECORD = "duplicate_replay_record"
    EVENT_TIME_REGRESSION = "event_time_regression"
    EVENT_BEHIND_WATERMARK = "event_behind_watermark"
    LATE_EVENT_AFTER_FINALIZATION = "late_event_after_finalization"
    TRADE_OUTSIDE_SESSION = "trade_outside_session"
    MISSING_COVERAGE = "missing_coverage"
    CONTRACT_BOUNDARY = "contract_boundary"
    UNSUPPORTED_CALENDAR_RANGE = "unsupported_calendar_range"


def _is_plain_positive_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_plain_nonnegative_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _require_nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise MarketDataValidationError(f"{name} must be a non-empty string")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not _is_plain_positive_int(value):
        raise MarketDataValidationError(f"{name} must be a positive integer")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if not _is_plain_nonnegative_int(value):
        raise MarketDataValidationError(f"{name} must be a non-negative integer")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MarketDataValidationError(f"{name} must be a SHA-256 hex digest")
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode an already-normalized mapping as canonical UTF-8 JSON."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """V1 continuous-symbol and tick-size allowlist entry."""

    root: str
    continuous_symbol: str
    tick_nanos: int = NANOS_PER_TICK

    def __post_init__(self) -> None:
        _require_nonempty_string(self.root, "root")
        _require_nonempty_string(self.continuous_symbol, "continuous_symbol")
        expected_symbols = {"NQ": "NQ.c.0", "ES": "ES.c.0"}
        if self.root not in expected_symbols:
            raise MarketDataValidationError("root must be one of NQ or ES")
        if self.continuous_symbol != expected_symbols[self.root]:
            raise MarketDataValidationError("continuous_symbol does not match root")
        if self.tick_nanos != NANOS_PER_TICK:
            raise MarketDataValidationError("tick_nanos must be the NQ/ES 0.25-point tick")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "continuous_symbol": self.continuous_symbol,
            "root": self.root,
            "tick_nanos": self.tick_nanos,
        }


@dataclass(frozen=True, slots=True)
class TradeEvent:
    """One normalized trade, preserving source-record multiplicity exactly."""

    source: str
    instrument: InstrumentSpec
    publisher_id: int
    instrument_id: int
    ts_event_ns: int
    ts_recv_ns: int
    price_ticks: int
    size: int
    action: str
    aggressor_side: str
    flags: int
    depth: int
    sequence: int
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_string(self.source, "source")
        if not isinstance(self.instrument, InstrumentSpec):
            raise MarketDataValidationError("instrument must be an InstrumentSpec")
        _require_positive_int(self.publisher_id, "publisher_id")
        _require_positive_int(self.instrument_id, "instrument_id")
        _require_nonnegative_int(self.ts_event_ns, "ts_event_ns")
        _require_nonnegative_int(self.ts_recv_ns, "ts_recv_ns")
        if self.ts_recv_ns < self.ts_event_ns:
            raise MarketDataValidationError("ts_recv_ns must not precede ts_event_ns")
        _require_positive_int(self.price_ticks, "price_ticks")
        _require_positive_int(self.size, "size")
        _require_nonempty_string(self.action, "action")
        _require_nonempty_string(self.aggressor_side, "aggressor_side")
        _require_nonnegative_int(self.flags, "flags")
        _require_nonnegative_int(self.depth, "depth")
        _require_nonnegative_int(self.sequence, "sequence")
        if self.schema_version != SCHEMA_VERSION:
            raise MarketDataValidationError("unsupported schema_version")

    @property
    def price_nanos(self) -> int:
        return self.price_ticks * self.instrument.tick_nanos

    def canonical_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "aggressor_side": self.aggressor_side,
            "continuous_symbol": self.instrument.continuous_symbol,
            "depth": self.depth,
            "flags": self.flags,
            "instrument_id": self.instrument_id,
            "price_ticks": self.price_ticks,
            "publisher_id": self.publisher_id,
            "root": self.instrument.root,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "size": self.size,
            "source": self.source,
            "ts_event_ns": self.ts_event_ns,
            "ts_recv_ns": self.ts_recv_ns,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class FinalBar:
    """A closed, immutable OHLCV bar, keyed by one Databento instrument ID."""

    source: str
    instrument: InstrumentSpec
    instrument_id: int
    timeframe: Timeframe
    calendar_fingerprint: str
    aggregation_fingerprint: str
    start_ns: int
    end_ns: int
    trading_date: date | None
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    volume: int
    trade_count: int
    first_event_ns: int
    last_event_ns: int
    quality: QualityState = QualityState.COMPLETE
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_string(self.source, "source")
        if not isinstance(self.instrument, InstrumentSpec):
            raise MarketDataValidationError("instrument must be an InstrumentSpec")
        _require_positive_int(self.instrument_id, "instrument_id")
        if not isinstance(self.timeframe, Timeframe):
            raise MarketDataValidationError("timeframe must be a Timeframe")
        for name in ("calendar_fingerprint", "aggregation_fingerprint"):
            _require_sha256(getattr(self, name), name)
        _require_nonnegative_int(self.start_ns, "start_ns")
        _require_nonnegative_int(self.end_ns, "end_ns")
        if self.start_ns >= self.end_ns:
            raise MarketDataValidationError("start_ns must be before end_ns")
        if self.timeframe.is_session_based and self.trading_date is None:
            raise MarketDataValidationError("trading_date is required for daily and weekly bars")
        if self.trading_date is not None and not isinstance(self.trading_date, date):
            raise MarketDataValidationError("trading_date must be a date or None")
        for name in ("open_ticks", "high_ticks", "low_ticks", "close_ticks"):
            _require_positive_int(getattr(self, name), name)
        if not self.low_ticks <= self.open_ticks <= self.high_ticks:
            raise MarketDataValidationError("open_ticks must be inside low/high")
        if not self.low_ticks <= self.close_ticks <= self.high_ticks:
            raise MarketDataValidationError("close_ticks must be inside low/high")
        _require_positive_int(self.volume, "volume")
        _require_positive_int(self.trade_count, "trade_count")
        _require_nonnegative_int(self.first_event_ns, "first_event_ns")
        _require_nonnegative_int(self.last_event_ns, "last_event_ns")
        if not self.start_ns <= self.first_event_ns <= self.last_event_ns < self.end_ns:
            raise MarketDataValidationError(
                "event timestamps must be inside the half-open bar interval"
            )
        if not isinstance(self.quality, QualityState):
            raise MarketDataValidationError("quality must be a QualityState")
        if self.schema_version != SCHEMA_VERSION:
            raise MarketDataValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "aggregation_fingerprint": self.aggregation_fingerprint,
            "calendar_fingerprint": self.calendar_fingerprint,
            "close_ticks": self.close_ticks,
            "continuous_symbol": self.instrument.continuous_symbol,
            "end_ns": self.end_ns,
            "first_event_ns": self.first_event_ns,
            "high_ticks": self.high_ticks,
            "instrument_id": self.instrument_id,
            "last_event_ns": self.last_event_ns,
            "low_ticks": self.low_ticks,
            "open_ticks": self.open_ticks,
            "quality": self.quality.value,
            "root": self.instrument.root,
            "schema_version": self.schema_version,
            "source": self.source,
            "start_ns": self.start_ns,
            "timeframe": self.timeframe.value,
            "trade_count": self.trade_count,
            "trading_date": self.trading_date.isoformat() if self.trading_date else None,
            "volume": self.volume,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()

    @property
    def series_id(self) -> str:
        """Identify bar semantics independently of a physical contract roll."""
        payload = {
            "aggregation_fingerprint": self.aggregation_fingerprint,
            "calendar_fingerprint": self.calendar_fingerprint,
            "continuous_symbol": self.instrument.continuous_symbol,
            "root": self.instrument.root,
            "schema_version": self.schema_version,
            "source": self.source,
            "timeframe": self.timeframe.value,
        }
        return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketDataIssue:
    """An immutable runtime quality fact emitted alongside the market stream."""

    code: IssueCode
    source: str
    detail: str
    instrument_id: int | None = None
    ts_event_ns: int | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.code, IssueCode):
            raise MarketDataValidationError("code must be an IssueCode")
        _require_nonempty_string(self.source, "source")
        _require_nonempty_string(self.detail, "detail")
        if self.instrument_id is not None:
            _require_positive_int(self.instrument_id, "instrument_id")
        if self.ts_event_ns is not None:
            _require_nonnegative_int(self.ts_event_ns, "ts_event_ns")
        if self.schema_version != SCHEMA_VERSION:
            raise MarketDataValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "instrument_id": self.instrument_id,
            "schema_version": self.schema_version,
            "source": self.source,
            "ts_event_ns": self.ts_event_ns,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ResumeCursor:
    """Per-instrument Databento timestamp-and-count reconnect checkpoint."""

    source: str
    instrument_id: int
    ts_event_ns: int
    records_at_timestamp: int
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_string(self.source, "source")
        _require_positive_int(self.instrument_id, "instrument_id")
        _require_nonnegative_int(self.ts_event_ns, "ts_event_ns")
        _require_positive_int(self.records_at_timestamp, "records_at_timestamp")
        if self.schema_version != SCHEMA_VERSION:
            raise MarketDataValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "records_at_timestamp": self.records_at_timestamp,
            "schema_version": self.schema_version,
            "source": self.source,
            "ts_event_ns": self.ts_event_ns,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()
