"""Immutable, deterministic contracts for the SP2 signal engine.

This module deliberately models data only.  It has no strategy evaluation,
wall-clock, network, execution, ledger, or backtest dependency.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from hashlib import sha256
from math import gcd
from types import MappingProxyType
from typing import Any, TypeGuard

from stoic_derived.market_data.model import FinalBar, Timeframe

SCHEMA_VERSION = "signal-engine/v1"
CONFIDENCE_MIN = 0
CONFIDENCE_MAX = 100


class SignalValidationError(ValueError):
    """Raised when a value cannot safely enter the deterministic signal path."""


class SignalType(StrEnum):
    """The four Vision-pinned trade types."""

    SCALP = "Scalp"
    DAY = "Day"
    SWING = "Swing"
    POSITION = "Position"


class Direction(StrEnum):
    """Trade orientation, independent of any predicate implementation."""

    LONG = "long"
    SHORT = "short"


class SetupType(StrEnum):
    """The closed setup vocabulary published by SP0."""

    BREAK_AND_RETEST = "break_and_retest"
    SWING_FAILURE_PATTERN = "swing_failure_pattern"


class Role(StrEnum):
    """A timeframe's fixed role in a multi-timeframe plan."""

    HTF = "htf"
    SETUP = "setup"
    EXECUTE = "execute"
    MANAGE = "manage"


class SuppressionCode(StrEnum):
    """Stable, auditable reasons for a deliberately absent signal."""

    RELEASE_UNAVAILABLE = "release_unavailable"
    SEMANTIC_UNSUPPORTED = "semantic_unsupported"
    MISSING_CONTEXT = "missing_context"
    INSUFFICIENT_LOOKBACK = "insufficient_lookback"
    DEGRADED_DATA = "degraded_data"
    COVERAGE_GAP = "coverage_gap"
    LINEAGE_MISMATCH = "lineage_mismatch"
    PREDICATE_NOT_MATCHED = "predicate_not_matched"
    UNFILLABLE_PRICE = "unfillable_price"
    OFF_TICK_PRICE = "off_tick_price"
    INVALID_ORIENTATION = "invalid_orientation"
    INVALID_R = "invalid_r"
    INVALID_CONFIDENCE = "invalid_confidence"


def _is_plain_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SignalValidationError(f"{name} must be a non-empty string")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if not _is_plain_int(value) or value < 0:
        raise SignalValidationError(f"{name} must be a non-negative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not _is_plain_int(value) or value <= 0:
        raise SignalValidationError(f"{name} must be a positive integer")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SignalValidationError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _require_sorted_unique(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise SignalValidationError(f"{name} must be a non-empty tuple of strings")
    if tuple(sorted(values)) != values or len(set(values)) != len(values):
        raise SignalValidationError(f"{name} must be sorted and unique")
    return values


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode normalized data as canonical UTF-8 JSON without float coercion."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


@dataclass(frozen=True, slots=True)
class TimeframePlan:
    """One complete, fixed Vision timeframe plan."""

    signal_type: SignalType
    htf: Timeframe
    setup: Timeframe
    execute: Timeframe
    manage: Timeframe

    def __post_init__(self) -> None:
        if not isinstance(self.signal_type, SignalType):
            raise SignalValidationError("signal_type must be a SignalType")
        for role in Role:
            if not isinstance(getattr(self, role.value), Timeframe):
                raise SignalValidationError(f"{role.value} must be a Timeframe")

    def for_role(self, role: Role) -> Timeframe:
        if not isinstance(role, Role):
            raise SignalValidationError("role must be a Role")
        return {
            Role.HTF: self.htf,
            Role.SETUP: self.setup,
            Role.EXECUTE: self.execute,
            Role.MANAGE: self.manage,
        }[role]

    def canonical_dict(self) -> dict[str, str]:
        return {
            "execute": self.execute.value,
            "htf": self.htf.value,
            "manage": self.manage.value,
            "setup": self.setup.value,
            "signal_type": self.signal_type.value,
        }


TIMEFRAME_PLANS: Mapping[SignalType, TimeframePlan] = MappingProxyType(
    {
        SignalType.SCALP: TimeframePlan(
            SignalType.SCALP,
            Timeframe.FIFTEEN_MINUTES,
            Timeframe.FIVE_MINUTES,
            Timeframe.ONE_MINUTE,
            Timeframe.FIVE_MINUTES,
        ),
        SignalType.DAY: TimeframePlan(
            SignalType.DAY,
            Timeframe.SIXTY_MINUTES,
            Timeframe.FIVE_MINUTES,
            Timeframe.ONE_MINUTE,
            Timeframe.FIVE_MINUTES,
        ),
        SignalType.SWING: TimeframePlan(
            SignalType.SWING,
            Timeframe.DAILY,
            Timeframe.SIXTY_MINUTES,
            Timeframe.FIFTEEN_MINUTES,
            Timeframe.SIXTY_MINUTES,
        ),
        SignalType.POSITION: TimeframePlan(
            SignalType.POSITION,
            Timeframe.WEEKLY,
            Timeframe.DAILY,
            Timeframe.SIXTY_MINUTES,
            Timeframe.DAILY,
        ),
    }
)
FIXED_TIMEFRAME_PLANS = TIMEFRAME_PLANS

_RELEASE_TIMEFRAMES: Mapping[str, Timeframe] = MappingProxyType(
    {
        "1m": Timeframe.ONE_MINUTE,
        "5m": Timeframe.FIVE_MINUTES,
        "15m": Timeframe.FIFTEEN_MINUTES,
        "60m": Timeframe.SIXTY_MINUTES,
        "1d": Timeframe.DAILY,
        "1w": Timeframe.WEEKLY,
    }
)


def timeframe_from_release_value(value: str) -> Timeframe:
    """Translate the SP0 release's ``1d``/``1w`` notation to SP1 timeframes."""
    if not isinstance(value, str) or value not in _RELEASE_TIMEFRAMES:
        raise SignalValidationError("unsupported release timeframe")
    return _RELEASE_TIMEFRAMES[value]


timeframe_from_rulebook = timeframe_from_release_value


@dataclass(frozen=True, slots=True)
class MarketLineage:
    """The single physical-market lineage from which a snapshot may be built."""

    source: str
    root: str
    continuous_symbol: str
    instrument_id: int
    calendar_fingerprint: str
    aggregation_fingerprint: str
    market_data_schema: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.source, "source")
        _require_nonempty_string(self.root, "root")
        expected_symbols = {"NQ": "NQ.c.0", "ES": "ES.c.0"}
        if self.root not in expected_symbols:
            raise SignalValidationError("root must be one of NQ or ES")
        if self.continuous_symbol != expected_symbols[self.root]:
            raise SignalValidationError("continuous_symbol does not match root")
        _require_positive_int(self.instrument_id, "instrument_id")
        _require_sha256(self.calendar_fingerprint, "calendar_fingerprint")
        _require_sha256(self.aggregation_fingerprint, "aggregation_fingerprint")
        _require_nonempty_string(self.market_data_schema, "market_data_schema")

    @classmethod
    def from_final_bar(cls, bar: FinalBar) -> MarketLineage:
        """Create the complete physical lineage carried by an immutable SP1 bar."""
        if not isinstance(bar, FinalBar):
            raise SignalValidationError("bar must be a FinalBar")
        return cls(
            source=bar.source,
            root=bar.instrument.root,
            continuous_symbol=bar.instrument.continuous_symbol,
            instrument_id=bar.instrument_id,
            calendar_fingerprint=bar.calendar_fingerprint,
            aggregation_fingerprint=bar.aggregation_fingerprint,
            market_data_schema=bar.schema_version,
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "aggregation_fingerprint": self.aggregation_fingerprint,
            "calendar_fingerprint": self.calendar_fingerprint,
            "continuous_symbol": self.continuous_symbol,
            "instrument_id": self.instrument_id,
            "market_data_schema": self.market_data_schema,
            "root": self.root,
            "source": self.source,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """One known missing half-open interval; it is never silently repaired."""

    lineage: MarketLineage
    timeframe: Timeframe
    start_ns: int
    end_ns: int
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        if not isinstance(self.timeframe, Timeframe):
            raise SignalValidationError("timeframe must be a Timeframe")
        _require_nonnegative_int(self.start_ns, "start_ns")
        _require_nonnegative_int(self.end_ns, "end_ns")
        if self.start_ns >= self.end_ns:
            raise SignalValidationError("start_ns must be before end_ns")
        _require_nonempty_string(self.reason, "reason")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "end_ns": self.end_ns,
            "lineage": self.lineage.canonical_dict(),
            "reason": self.reason,
            "start_ns": self.start_ns,
            "timeframe": self.timeframe.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class RationalR:
    """A positive, reduced risk multiple with no binary floating-point value."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _require_positive_int(self.numerator, "numerator")
        _require_positive_int(self.denominator, "denominator")
        if gcd(self.numerator, self.denominator) != 1:
            raise SignalValidationError("R numerator and denominator must be reduced")

    @classmethod
    def from_fraction(cls, value: Fraction) -> RationalR:
        if not isinstance(value, Fraction) or value <= 0:
            raise SignalValidationError("R must be a positive Fraction")
        return cls(numerator=value.numerator, denominator=value.denominator)

    @classmethod
    def from_prices(
        cls, direction: Direction, entry_ticks: int, stop_ticks: int, target_ticks: int
    ) -> RationalR:
        """Calculate reward/risk exactly from integer ticks and validated orientation."""
        _require_positive_int(entry_ticks, "entry_ticks")
        _require_positive_int(stop_ticks, "stop_ticks")
        _require_positive_int(target_ticks, "target_ticks")
        if direction is Direction.LONG:
            if not stop_ticks < entry_ticks < target_ticks:
                raise SignalValidationError("long orientation requires stop < entry < target")
            return cls.from_fraction(Fraction(target_ticks - entry_ticks, entry_ticks - stop_ticks))
        if direction is Direction.SHORT:
            if not target_ticks < entry_ticks < stop_ticks:
                raise SignalValidationError("short orientation requires target < entry < stop")
            return cls.from_fraction(Fraction(entry_ticks - target_ticks, stop_ticks - entry_ticks))
        raise SignalValidationError("direction must be a Direction")

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    @property
    def decimal_string(self) -> str:
        """Return an exact finite decimal, or exact ``numerator/denominator`` otherwise."""
        denominator = self.denominator
        twos = 0
        fives = 0
        while denominator % 2 == 0:
            denominator //= 2
            twos += 1
        while denominator % 5 == 0:
            denominator //= 5
            fives += 1
        if denominator != 1:
            return f"{self.numerator}/{self.denominator}"
        scale = max(twos, fives)
        scaled = self.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
        digits = str(scaled).zfill(scale + 1)
        return f"{digits[:-scale]}.{digits[-scale:]}" if scale else digits

    def canonical_dict(self) -> dict[str, object]:
        return {
            "decimal": self.decimal_string,
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


@dataclass(frozen=True, slots=True)
class SignalRecord:
    """A complete, content-addressed signal with exhaustive causal provenance."""

    signal_type: SignalType
    direction: Direction
    entry_ticks: int
    stop_ticks: int
    target_ticks: int
    risk_reward: RationalR
    setup_type: SetupType
    entry_model: str
    confidence: int
    signal_ts_ns: int
    source: str
    release_file_sha256: str
    rulebook_version: str
    rule_id: str
    engine_version: str
    lineage: MarketLineage
    causal_bar_ids: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    signal_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.signal_type, SignalType):
            raise SignalValidationError("signal_type must be a SignalType")
        if not isinstance(self.direction, Direction):
            raise SignalValidationError("direction must be a Direction")
        for name in ("entry_ticks", "stop_ticks", "target_ticks"):
            _require_positive_int(getattr(self, name), name)
        if not isinstance(self.risk_reward, RationalR):
            raise SignalValidationError("risk_reward must be a RationalR")
        if self.risk_reward != RationalR.from_prices(
            self.direction, self.entry_ticks, self.stop_ticks, self.target_ticks
        ):
            raise SignalValidationError("risk_reward must exactly match entry, stop, and target")
        if not isinstance(self.setup_type, SetupType):
            raise SignalValidationError("setup_type must be a SetupType")
        _require_nonempty_string(self.entry_model, "entry_model")
        if (
            not _is_plain_int(self.confidence)
            or not CONFIDENCE_MIN <= self.confidence <= CONFIDENCE_MAX
        ):
            raise SignalValidationError("confidence must be an integer from 0 through 100")
        _require_nonnegative_int(self.signal_ts_ns, "signal_ts_ns")
        for name in ("source", "rulebook_version", "rule_id", "engine_version"):
            _require_nonempty_string(getattr(self, name), name)
        _require_sha256(self.release_file_sha256, "release_file_sha256")
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        _require_sorted_unique(self.causal_bar_ids, "causal_bar_ids")
        for index, bar_id in enumerate(self.causal_bar_ids):
            _require_sha256(bar_id, f"causal_bar_ids[{index}]")
        if self.schema_version != SCHEMA_VERSION:
            raise SignalValidationError("unsupported schema_version")
        object.__setattr__(self, "signal_id", sha256(self._content_bytes()).hexdigest())

    @property
    def instrument(self) -> str:
        """Return the Vision-facing logical instrument name."""
        return self.lineage.root

    @property
    def timeframe_plan(self) -> TimeframePlan:
        return TIMEFRAME_PLANS[self.signal_type]

    def _content_dict(self) -> dict[str, object]:
        return {
            "causal_bar_ids": list(self.causal_bar_ids),
            "confidence": self.confidence,
            "direction": self.direction.value,
            "engine_version": self.engine_version,
            "entry_model": self.entry_model,
            "entry_ticks": self.entry_ticks,
            "lineage": self.lineage.canonical_dict(),
            "release_file_sha256": self.release_file_sha256,
            "risk_reward": self.risk_reward.canonical_dict(),
            "rule_id": self.rule_id,
            "rulebook_version": self.rulebook_version,
            "schema_version": self.schema_version,
            "setup_type": self.setup_type.value,
            "signal_ts_ns": self.signal_ts_ns,
            "signal_type": self.signal_type.value,
            "source": self.source,
            "stop_ticks": self.stop_ticks,
            "target_ticks": self.target_ticks,
            "timeframe_plan": self.timeframe_plan.canonical_dict(),
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "signal_id": self.signal_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class Suppression:
    """A deterministic audit fact explaining why no complete signal was emitted."""

    code: SuppressionCode
    detail: str
    source: str
    release_file_sha256: str
    rulebook_version: str
    engine_version: str
    signal_type: SignalType | None = None
    signal_ts_ns: int | None = None
    lineage: MarketLineage | None = None
    rule_id: str | None = None
    references: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.code, SuppressionCode):
            raise SignalValidationError("code must be a SuppressionCode")
        for name in ("detail", "source", "rulebook_version", "engine_version"):
            _require_nonempty_string(getattr(self, name), name)
        _require_sha256(self.release_file_sha256, "release_file_sha256")
        if self.signal_type is not None and not isinstance(self.signal_type, SignalType):
            raise SignalValidationError("signal_type must be a SignalType or None")
        if self.signal_ts_ns is not None:
            _require_nonnegative_int(self.signal_ts_ns, "signal_ts_ns")
        if self.lineage is not None and not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage or None")
        if self.rule_id is not None:
            _require_nonempty_string(self.rule_id, "rule_id")
        if any(not isinstance(reference, str) or not reference for reference in self.references):
            raise SignalValidationError("references must be strings")
        if tuple(sorted(self.references)) != self.references or len(set(self.references)) != len(
            self.references
        ):
            raise SignalValidationError("references must be sorted and unique")
        if self.schema_version != SCHEMA_VERSION:
            raise SignalValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "engine_version": self.engine_version,
            "lineage": self.lineage.canonical_dict() if self.lineage else None,
            "references": list(self.references),
            "release_file_sha256": self.release_file_sha256,
            "rule_id": self.rule_id,
            "rulebook_version": self.rulebook_version,
            "schema_version": self.schema_version,
            "signal_ts_ns": self.signal_ts_ns,
            "signal_type": self.signal_type.value if self.signal_type else None,
            "source": self.source,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class Decision:
    """Exactly one signal or suppression for a deterministic evaluation attempt."""

    signal: SignalRecord | None = None
    suppression: Suppression | None = None

    def __post_init__(self) -> None:
        if (self.signal is None) == (self.suppression is None):
            raise SignalValidationError("decision must contain exactly one signal or suppression")
        if self.signal is not None and not isinstance(self.signal, SignalRecord):
            raise SignalValidationError("signal must be a SignalRecord")
        if self.suppression is not None and not isinstance(self.suppression, Suppression):
            raise SignalValidationError("suppression must be a Suppression")

    def canonical_dict(self) -> dict[str, object]:
        if self.signal is not None:
            return {"kind": "signal", "signal": self.signal.canonical_dict()}
        assert self.suppression is not None
        return {"kind": "suppression", "suppression": self.suppression.canonical_dict()}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


SignalDecision = Decision


@dataclass(frozen=True, slots=True)
class SignalBatch:
    """Canonical, ordered output records for one finalized physical lineage."""

    lineage: MarketLineage
    finalized_through_ns: int
    signals: tuple[SignalRecord, ...] = ()
    suppressions: tuple[Suppression, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        _require_nonnegative_int(self.finalized_through_ns, "finalized_through_ns")
        if any(not isinstance(signal, SignalRecord) for signal in self.signals):
            raise SignalValidationError("signals must contain SignalRecord values")
        if any(signal.lineage != self.lineage for signal in self.signals):
            raise SignalValidationError("signals must share the batch lineage")
        if tuple(sorted(self.signals, key=lambda signal: signal.signal_id)) != self.signals:
            raise SignalValidationError("signals must be ordered by signal_id")
        if any(not isinstance(suppression, Suppression) for suppression in self.suppressions):
            raise SignalValidationError("suppressions must contain Suppression values")
        if any(
            suppression.lineage is not None and suppression.lineage != self.lineage
            for suppression in self.suppressions
        ):
            raise SignalValidationError("suppressions must share the batch lineage")
        if (
            tuple(sorted(self.suppressions, key=lambda suppression: suppression.identity))
            != self.suppressions
        ):
            raise SignalValidationError("suppressions must be ordered by identity")
        if self.schema_version != SCHEMA_VERSION:
            raise SignalValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "finalized_through_ns": self.finalized_through_ns,
            "lineage": self.lineage.canonical_dict(),
            "schema_version": self.schema_version,
            "signals": [signal.canonical_dict() for signal in self.signals],
            "suppressions": [suppression.canonical_dict() for suppression in self.suppressions],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluationBatch:
    """Canonical ordered decisions from one closed-bar evaluation batch."""

    lineage: MarketLineage
    finalized_through_ns: int
    decisions: tuple[Decision, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        _require_nonnegative_int(self.finalized_through_ns, "finalized_through_ns")
        if any(not isinstance(decision, Decision) for decision in self.decisions):
            raise SignalValidationError("decisions must contain Decision values")
        if tuple(sorted(self.decisions, key=lambda decision: decision.identity)) != self.decisions:
            raise SignalValidationError("decisions must be ordered by identity")
        for decision in self.decisions:
            if decision.signal is not None and decision.signal.lineage != self.lineage:
                raise SignalValidationError("signals must share the batch lineage")
            if (
                decision.suppression is not None
                and decision.suppression.lineage is not None
                and decision.suppression.lineage != self.lineage
            ):
                raise SignalValidationError("suppressions must share the batch lineage")
        if self.schema_version != SCHEMA_VERSION:
            raise SignalValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "decisions": [decision.canonical_dict() for decision in self.decisions],
            "finalized_through_ns": self.finalized_through_ns,
            "lineage": self.lineage.canonical_dict(),
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())

    @property
    def identity(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()
