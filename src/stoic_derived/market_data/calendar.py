"""Versioned CME equity-index session assignment and deterministic bar buckets."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from .model import (
    MarketDataValidationError,
    Timeframe,
    UnsupportedCalendarRangeError,
    canonical_json_bytes,
)

CHICAGO = ZoneInfo("America/Chicago")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_GLOBEX_OPEN = time(17, 0)
_REGULAR_CLOSE = time(16, 0)
_PAUSE_START = time(15, 15)
_PAUSE_END = time(15, 30)
_CASH_START = time(8, 30)
_CASH_END = time(15, 0)
CALENDAR_MANIFEST_SCHEMA = "cme-equity-index-calendar/v1"


class CalendarManifestError(MarketDataValidationError):
    """Raised when a reviewed calendar manifest is malformed or incomplete."""


def _require_timestamp_ns(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MarketDataValidationError(f"{name} must be a non-negative UTC nanosecond integer")
    return value


def _require_fingerprint(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MarketDataValidationError("calendar_fingerprint must be a SHA-256 hex digest")
    return value


def _datetime_to_ns(value: datetime) -> int:
    if value.tzinfo is None:
        raise MarketDataValidationError("calendar datetime must be timezone-aware")
    delta = value.astimezone(UTC) - _EPOCH
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000_000) + delta.microseconds * 1_000


def _ns_to_chicago(value: int) -> datetime:
    seconds, remainder = divmod(value, 1_000_000_000)
    return (_EPOCH + timedelta(seconds=seconds, microseconds=remainder // 1_000)).astimezone(
        CHICAGO
    )


@dataclass(frozen=True, slots=True)
class SessionOverride:
    """A reviewed closure or early close for one CME trading date."""

    trading_date: date
    close_time: time | None
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date):
            raise MarketDataValidationError("trading_date must be a date")
        if self.close_time is not None:
            if not isinstance(self.close_time, time) or self.close_time.tzinfo is not None:
                raise MarketDataValidationError(
                    "close_time must be a timezone-naive local time or None"
                )
            if not time.min < self.close_time <= _REGULAR_CLOSE:
                raise MarketDataValidationError(
                    "close_time must be after midnight and no later than 16:00 CT"
                )
        if not isinstance(self.reason, str) or not self.reason:
            raise MarketDataValidationError("reason must be a non-empty string")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "reason": self.reason,
            "trading_date": self.trading_date.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TradingSession:
    """One half-open CME trading-date interval in UTC."""

    trading_date: date
    start_ns: int
    end_ns: int
    calendar_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date):
            raise MarketDataValidationError("trading_date must be a date")
        if self.start_ns >= self.end_ns:
            raise MarketDataValidationError("session start_ns must be before end_ns")
        _require_fingerprint(self.calendar_fingerprint)

    def contains(self, timestamp_ns: int) -> bool:
        return self.start_ns <= timestamp_ns < self.end_ns


@dataclass(frozen=True, slots=True)
class TimeBucket:
    """A half-open interval used directly by the bar aggregator."""

    timeframe: Timeframe
    start_ns: int
    end_ns: int
    trading_date: date | None
    calendar_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.timeframe, Timeframe):
            raise MarketDataValidationError("timeframe must be a Timeframe")
        if self.start_ns >= self.end_ns:
            raise MarketDataValidationError("bucket start_ns must be before end_ns")
        if self.timeframe.is_session_based and self.trading_date is None:
            raise MarketDataValidationError("daily and weekly buckets require trading_date")
        _require_fingerprint(self.calendar_fingerprint)

    def contains(self, timestamp_ns: int) -> bool:
        return self.start_ns <= timestamp_ns < self.end_ns


@dataclass(frozen=True, slots=True)
class CmeEquityIndexCalendar:
    """CME equity-index schedule, explicit exception data, and DST-safe session buckets."""

    version: str
    coverage_start: date
    coverage_end: date
    overrides: tuple[SessionOverride, ...] = ()
    provenance: tuple[str, ...] = ()
    _fingerprint: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version:
            raise MarketDataValidationError("version must be a non-empty string")
        if (
            not isinstance(self.coverage_start, date)
            or not isinstance(self.coverage_end, date)
            or self.coverage_start >= self.coverage_end
        ):
            raise MarketDataValidationError(
                "calendar coverage must be a non-empty half-open date interval"
            )
        if not isinstance(self.overrides, tuple) or not all(
            isinstance(override, SessionOverride) for override in self.overrides
        ):
            raise MarketDataValidationError("overrides must be a tuple of SessionOverride values")
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(source, str) or not source for source in self.provenance
        ):
            raise MarketDataValidationError("provenance must contain non-empty source strings")
        dates = [override.trading_date for override in self.overrides]
        if len(dates) != len(set(dates)):
            raise MarketDataValidationError("overrides may contain only one entry per trading_date")
        if any(
            not self.coverage_start <= override.trading_date < self.coverage_end
            for override in self.overrides
        ):
            raise MarketDataValidationError("calendar overrides must be inside its coverage")
        canonical_overrides = sorted(
            (override.canonical_dict() for override in self.overrides),
            key=lambda item: str(item["trading_date"]),
        )
        payload = {
            "cash_reference": ["08:30", "15:00"],
            "coverage_end": self.coverage_end.isoformat(),
            "coverage_start": self.coverage_start.isoformat(),
            "equity_pause": ["15:15", "15:30"],
            "overrides": canonical_overrides,
            "provenance": list(self.provenance),
            "regular_globex": ["17:00", "16:00"],
            "timezone": "America/Chicago",
            "version": self.version,
        }
        object.__setattr__(self, "_fingerprint", sha256(canonical_json_bytes(payload)).hexdigest())

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def _override_for(self, trading_day: date) -> SessionOverride | None:
        for override in self.overrides:
            if override.trading_date == trading_day:
                return override
        return None

    def session_for_trading_date(self, trading_day: date) -> TradingSession | None:
        """Return the regular/overridden session for a CME trading date, if open."""
        if not isinstance(trading_day, date):
            raise MarketDataValidationError("trading_day must be a date")
        if not self.provenance:
            raise UnsupportedCalendarRangeError(
                trading_day, "calendar has no reviewed schedule provenance for"
            )
        if not self.coverage_start <= trading_day < self.coverage_end:
            raise UnsupportedCalendarRangeError(trading_day)
        if trading_day.weekday() > 4:
            return None
        override = self._override_for(trading_day)
        if override is not None and override.close_time is None:
            return None
        close_local = override.close_time if override is not None else _REGULAR_CLOSE
        assert close_local is not None
        start_local = datetime.combine(trading_day - timedelta(days=1), _GLOBEX_OPEN, CHICAGO)
        end_local = datetime.combine(trading_day, close_local, CHICAGO)
        return TradingSession(
            trading_date=trading_day,
            start_ns=_datetime_to_ns(start_local),
            end_ns=_datetime_to_ns(end_local),
            calendar_fingerprint=self.fingerprint,
        )

    def session_at(self, timestamp_ns: int) -> TradingSession | None:
        """Map a UTC event instant to its regular CME trading-date session."""
        timestamp_ns = _require_timestamp_ns(timestamp_ns, "timestamp_ns")
        local = _ns_to_chicago(timestamp_ns)
        trading_day = (
            local.date() + timedelta(days=1)
            if local.timetz().replace(tzinfo=None) >= _GLOBEX_OPEN
            else local.date()
        )
        session = self.session_for_trading_date(trading_day)
        if session is None or not session.contains(timestamp_ns):
            return None
        return session

    def is_regular_trading(self, timestamp_ns: int) -> bool:
        """Return whether an event is in the tradable session excluding the equity pause."""
        if self.session_at(timestamp_ns) is None:
            return False
        local_time = _ns_to_chicago(timestamp_ns).timetz().replace(tzinfo=None)
        return not _PAUSE_START <= local_time < _PAUSE_END

    def is_cash_reference(self, timestamp_ns: int) -> bool:
        """Return whether an instant is within the half-open 08:30-15:00 CT window."""
        if self.session_at(timestamp_ns) is None:
            return False
        local_time = _ns_to_chicago(timestamp_ns).timetz().replace(tzinfo=None)
        return _CASH_START <= local_time < _CASH_END

    def bucket_at(self, timestamp_ns: int, timeframe: Timeframe) -> TimeBucket | None:
        """Return the configured half-open bucket containing an in-session event."""
        if not isinstance(timeframe, Timeframe):
            raise MarketDataValidationError("timeframe must be a Timeframe")
        buckets = self.buckets_at(timestamp_ns, (timeframe,))
        return buckets[0] if buckets else None

    def buckets_at(
        self, timestamp_ns: int, timeframes: Sequence[Timeframe]
    ) -> tuple[TimeBucket, ...]:
        """Resolve several buckets with one session and local-time lookup."""
        timestamp_ns = _require_timestamp_ns(timestamp_ns, "timestamp_ns")
        if not isinstance(timeframes, Sequence) or any(
            not isinstance(timeframe, Timeframe) for timeframe in timeframes
        ):
            raise MarketDataValidationError("timeframes must contain only Timeframe values")
        session = self.session_at(timestamp_ns)
        if session is None:
            return ()
        local_time = _ns_to_chicago(timestamp_ns).timetz().replace(tzinfo=None)
        if _PAUSE_START <= local_time < _PAUSE_END:
            return ()
        buckets: list[TimeBucket] = []
        for timeframe in timeframes:
            duration_ns = timeframe.duration_ns
            if duration_ns is not None:
                start_ns = (timestamp_ns // duration_ns) * duration_ns
                bucket = TimeBucket(
                    timeframe=timeframe,
                    start_ns=start_ns,
                    end_ns=min(start_ns + duration_ns, session.end_ns),
                    trading_date=session.trading_date,
                    calendar_fingerprint=self.fingerprint,
                )
            elif timeframe is Timeframe.DAILY:
                bucket = TimeBucket(
                    timeframe=timeframe,
                    start_ns=session.start_ns,
                    end_ns=session.end_ns,
                    trading_date=session.trading_date,
                    calendar_fingerprint=self.fingerprint,
                )
            else:
                bucket = self._weekly_bucket(session)
            buckets.append(bucket)
        return tuple(buckets)

    def _weekly_bucket(self, session: TradingSession) -> TimeBucket:
        week_start = session.trading_date - timedelta(days=session.trading_date.weekday())
        sessions = [
            candidate
            for offset in range(5)
            if (candidate := self.session_for_trading_date(week_start + timedelta(days=offset)))
            is not None
        ]
        if not sessions:
            raise MarketDataValidationError("calendar has no declared sessions in the trading week")
        return TimeBucket(
            timeframe=Timeframe.WEEKLY,
            start_ns=sessions[0].start_ns,
            end_ns=sessions[-1].end_ns,
            trading_date=week_start,
            calendar_fingerprint=self.fingerprint,
        )


def load_calendar_manifest(path: Path | str) -> CmeEquityIndexCalendar:
    """Load a strict, committed schedule bundle; arbitrary date ranges are not production input."""
    source_path = Path(path)
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CalendarManifestError(f"failed to load calendar manifest {source_path}") from exc
    expected_keys = {
        "coverage_end",
        "coverage_start",
        "overrides",
        "schema_version",
        "source_urls",
        "version",
    }
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise CalendarManifestError("calendar manifest fields do not match the v1 schema")
    if raw["schema_version"] != CALENDAR_MANIFEST_SCHEMA:
        raise CalendarManifestError("calendar manifest schema_version is unsupported")
    source_urls = raw["source_urls"]
    if (
        not isinstance(source_urls, list)
        or not source_urls
        or any(
            not isinstance(source, str) or not source.startswith("https://")
            for source in source_urls
        )
    ):
        raise CalendarManifestError("calendar manifest requires HTTPS source_urls")
    raw_overrides = raw["overrides"]
    if not isinstance(raw_overrides, list):
        raise CalendarManifestError("calendar manifest overrides must be a list")
    overrides: list[SessionOverride] = []
    for raw_override in raw_overrides:
        if not isinstance(raw_override, dict) or set(raw_override) != {
            "close_time",
            "reason",
            "trading_date",
        }:
            raise CalendarManifestError("calendar override fields do not match the v1 schema")
        try:
            trading_date = date.fromisoformat(raw_override["trading_date"])
            close_time = (
                None
                if raw_override["close_time"] is None
                else time.fromisoformat(raw_override["close_time"])
            )
            override = SessionOverride(
                trading_date=trading_date,
                close_time=close_time,
                reason=raw_override["reason"],
            )
        except (TypeError, ValueError, MarketDataValidationError) as exc:
            raise CalendarManifestError("calendar manifest has an invalid override") from exc
        overrides.append(override)
    try:
        return CmeEquityIndexCalendar(
            version=raw["version"],
            coverage_start=date.fromisoformat(raw["coverage_start"]),
            coverage_end=date.fromisoformat(raw["coverage_end"]),
            overrides=tuple(overrides),
            provenance=tuple(source_urls),
        )
    except (TypeError, ValueError, MarketDataValidationError) as exc:
        raise CalendarManifestError("calendar manifest has invalid coverage") from exc
