"""Immutable, research-only contracts for SP3 observational backtesting.

This module deliberately contains no engine, release, strategy, fixture, broker,
or order-routing dependency.  It records deterministic research observations only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from hashlib import sha256
from math import gcd
from typing import Any, TypeGuard

from stoic_derived.market_data.model import Timeframe
from stoic_derived.signal_engine.model import (
    TIMEFRAME_PLANS,
    Direction,
    MarketLineage,
    SetupType,
    SignalRecord,
    SignalType,
    Suppression,
    SuppressionCode,
)

SCHEMA_VERSION = "backtest/v1"
SIMULATOR_ALGORITHM_VERSION = "conservative-causal-one-minute/v1"
METRICS_ALGORITHM_VERSION = "descriptive-exact-r/v1"
ARTIFACT_ALGORITHM_VERSION = "content-addressed-json/v1"


class BacktestValidationError(ValueError):
    """Raised when an observational research contract is invalid or unsafe."""


class EvidenceClass(StrEnum):
    """Truthful provenance labels; neither is a live-readiness claim."""

    RETROSPECTIVE_REPLAY = "retrospective_replay"
    PAPER_FORWARD = "paper_forward"


class BacktestStatus(StrEnum):
    """A research run is either safely blocked or observationally complete."""

    BLOCKED = "blocked"
    COMPLETE = "complete"


class ObservationState(StrEnum):
    """The only permitted state machine for one independent observation."""

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    UNRESOLVED = "unresolved"


class ObservationReason(StrEnum):
    """Stable terminal reasons; these are evidence limitations, never orders."""

    STOP = "stop"
    TARGET = "target"
    SESSION_FLATTEN = "session_flatten"
    END_OF_DATA = "end_of_data"
    FOLD_END = "fold_end"
    CONTRACT_ROLL = "contract_roll"
    SESSION_CUTOFF = "session_cutoff"
    MISSING_CUTOFF_BAR = "missing_cutoff_bar"
    DEGRADED_DATA = "degraded_data"
    COVERAGE_GAP = "coverage_gap"
    AMBIGUOUS_OBSERVATION = "ambiguous_observation"


class FillKind(StrEnum):
    """The constrained fill vocabulary of the conservative simulator."""

    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    SESSION_FLATTEN = "session_flatten"


class WarningCode(StrEnum):
    """Deterministic limitations attached to research evidence."""

    INSUFFICIENT_SAMPLE = "insufficient_sample"
    MULTIPLE_COMPARISONS = "multiple_comparisons"
    END_OF_DATA = "end_of_data"
    FOLD_END = "fold_end"
    CONTRACT_ROLL = "contract_roll"
    SESSION_CUTOFF = "session_cutoff"
    MISSING_CUTOFF_BAR = "missing_cutoff_bar"
    DEGRADED_DATA = "degraded_data"
    COVERAGE_GAP = "coverage_gap"
    AMBIGUOUS_OBSERVATION = "ambiguous_observation"
    BOUND_EXCEEDED = "bound_exceeded"


class MetricScope(StrEnum):
    """Whether a metric preserves one contract or summarizes one logical root."""

    PHYSICAL_CONTRACT = "physical_contract"
    ROOT_SUMMARY = "root_summary"


def _is_plain_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise BacktestValidationError(f"{name} must be a non-empty string")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if not _is_plain_int(value) or value < 0:
        raise BacktestValidationError(f"{name} must be a non-negative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not _is_plain_int(value) or value <= 0:
        raise BacktestValidationError(f"{name} must be a positive integer")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BacktestValidationError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _require_sorted_unique_strings(
    values: object, name: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise BacktestValidationError(f"{name} must be a tuple of non-empty strings")
    if not allow_empty and not values:
        raise BacktestValidationError(f"{name} must not be empty")
    if tuple(sorted(values)) != values or len(set(values)) != len(values):
        raise BacktestValidationError(f"{name} must be sorted and unique")
    return values


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Encode normalized values as canonical UTF-8 JSON without float coercion."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _decimal_string(numerator: int, denominator: int) -> str:
    if numerator == 0:
        return "0"
    sign = "-" if numerator < 0 else ""
    numerator = abs(numerator)
    reduced_denominator = denominator
    twos = 0
    fives = 0
    while reduced_denominator % 2 == 0:
        reduced_denominator //= 2
        twos += 1
    while reduced_denominator % 5 == 0:
        reduced_denominator //= 5
        fives += 1
    if reduced_denominator != 1:
        return f"{sign}{numerator}/{denominator}"
    scale = max(twos, fives)
    scaled = numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(scaled).zfill(scale + 1)
    return f"{sign}{digits[:-scale]}.{digits[-scale:]}" if scale else f"{sign}{digits}"


@dataclass(frozen=True, slots=True)
class ExactR:
    """A signed, reduced rational risk multiple with no binary float representation."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if not _is_plain_int(self.numerator):
            raise BacktestValidationError("numerator must be an integer")
        _require_positive_int(self.denominator, "denominator")
        if self.numerator == 0:
            object.__setattr__(self, "denominator", 1)
        elif gcd(abs(self.numerator), self.denominator) != 1:
            raise BacktestValidationError("R numerator and denominator must be reduced")

    @classmethod
    def from_fraction(cls, value: Fraction) -> ExactR:
        if not isinstance(value, Fraction):
            raise BacktestValidationError("R must be a Fraction")
        return cls(value.numerator, value.denominator)

    @classmethod
    def from_ticks(cls, ticks: int, planned_risk_ticks: int) -> ExactR:
        return cls.from_fraction(
            Fraction(
                _require_nonnegative_or_signed_int(ticks, "ticks"),
                _require_positive_int(planned_risk_ticks, "planned_risk_ticks"),
            )
        )

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    @property
    def decimal_string(self) -> str:
        return _decimal_string(self.numerator, self.denominator)

    def canonical_dict(self) -> dict[str, object]:
        return {
            "decimal": self.decimal_string,
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


SignedR = ExactR


def _require_nonnegative_or_signed_int(value: object, name: str) -> int:
    if not _is_plain_int(value):
        raise BacktestValidationError(f"{name} must be an integer")
    return value


@dataclass(frozen=True, slots=True)
class SimulationPolicy:
    """Explicit, versioned costs, assumptions, and fail-closed state bounds."""

    entry_slippage_ticks: int
    exit_slippage_ticks: int
    fees_ticks_round_turn: int
    zero_costs_declared: bool
    max_active_observations: int
    max_active_lineages: int
    max_retained_gaps: int
    max_accepted_batches: int
    max_output_records: int
    max_artifact_bytes: int
    simulator_algorithm_version: str = SIMULATOR_ALGORITHM_VERSION
    schema_version: str = SCHEMA_VERSION
    policy_id: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("entry_slippage_ticks", "exit_slippage_ticks", "fees_ticks_round_turn"):
            _require_nonnegative_int(getattr(self, name), name)
        if not isinstance(self.zero_costs_declared, bool):
            raise BacktestValidationError("zero_costs_declared must be a bool")
        all_costs_zero = (
            self.entry_slippage_ticks == 0
            and self.exit_slippage_ticks == 0
            and self.fees_ticks_round_turn == 0
        )
        if all_costs_zero != self.zero_costs_declared:
            raise BacktestValidationError(
                "zero-costs declaration must exactly match whether every declared cost is zero"
            )
        for name in (
            "max_active_observations",
            "max_active_lineages",
            "max_retained_gaps",
            "max_accepted_batches",
            "max_output_records",
            "max_artifact_bytes",
        ):
            _require_positive_int(getattr(self, name), name)
        _require_nonempty_string(self.simulator_algorithm_version, "simulator_algorithm_version")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(self, "policy_id", sha256(self._content_bytes()).hexdigest())

    def init_dict(self) -> dict[str, object]:
        return {
            "entry_slippage_ticks": self.entry_slippage_ticks,
            "exit_slippage_ticks": self.exit_slippage_ticks,
            "fees_ticks_round_turn": self.fees_ticks_round_turn,
            "zero_costs_declared": self.zero_costs_declared,
            "max_active_observations": self.max_active_observations,
            "max_active_lineages": self.max_active_lineages,
            "max_retained_gaps": self.max_retained_gaps,
            "max_accepted_batches": self.max_accepted_batches,
            "max_output_records": self.max_output_records,
            "max_artifact_bytes": self.max_artifact_bytes,
            "simulator_algorithm_version": self.simulator_algorithm_version,
            "schema_version": self.schema_version,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self.init_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self.init_dict(), "policy_id": self.policy_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class SimulatedFillRecord:
    """One research-only simulated fill tied to a source one-minute bar."""

    signal_id: str
    kind: FillKind
    price_ticks: int
    event_ts_ns: int
    policy_id: str
    source_bar_id: str
    research_only: bool = True
    schema_version: str = SCHEMA_VERSION
    fill_id: str = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.signal_id, "signal_id")
        if not isinstance(self.kind, FillKind):
            raise BacktestValidationError("kind must be a FillKind")
        _require_positive_int(self.price_ticks, "price_ticks")
        _require_nonnegative_int(self.event_ts_ns, "event_ts_ns")
        _require_sha256(self.policy_id, "policy_id")
        _require_sha256(self.source_bar_id, "source_bar_id")
        if self.research_only is not True:
            raise BacktestValidationError("simulated fills must be research-only")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(self, "fill_id", sha256(self._content_bytes()).hexdigest())

    def init_dict(self) -> dict[str, object]:
        return {
            "signal_id": self.signal_id,
            "kind": self.kind,
            "price_ticks": self.price_ticks,
            "event_ts_ns": self.event_ts_ns,
            "policy_id": self.policy_id,
            "source_bar_id": self.source_bar_id,
            "research_only": self.research_only,
            "schema_version": self.schema_version,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                **self.init_dict(),
                "kind": self.kind.value,
            }
        )

    def canonical_dict(self) -> dict[str, object]:
        return {**json.loads(self._content_bytes()), "fill_id": self.fill_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


_CLOSED_REASON_FOR_KIND = {
    FillKind.STOP: ObservationReason.STOP,
    FillKind.TARGET: ObservationReason.TARGET,
    FillKind.SESSION_FLATTEN: ObservationReason.SESSION_FLATTEN,
}
_UNRESOLVED_REASONS = frozenset(
    {
        ObservationReason.END_OF_DATA,
        ObservationReason.FOLD_END,
        ObservationReason.CONTRACT_ROLL,
        ObservationReason.SESSION_CUTOFF,
        ObservationReason.MISSING_CUTOFF_BAR,
        ObservationReason.DEGRADED_DATA,
        ObservationReason.COVERAGE_GAP,
        ObservationReason.AMBIGUOUS_OBSERVATION,
    }
)


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One signal's complete observational lifecycle and exact tick/R accounting."""

    signal: SignalRecord
    policy_id: str
    fees_ticks_round_turn: int
    state: ObservationState
    fills: tuple[SimulatedFillRecord, ...] = ()
    gross_ticks: int | None = None
    net_ticks: int | None = None
    gross_r: ExactR | None = None
    net_r: ExactR | None = None
    terminal_reason: ObservationReason | None = None
    schema_version: str = SCHEMA_VERSION
    trade_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.signal, SignalRecord):
            raise BacktestValidationError("signal must be a SignalRecord")
        _require_sha256(self.policy_id, "policy_id")
        _require_nonnegative_int(self.fees_ticks_round_turn, "fees_ticks_round_turn")
        if not isinstance(self.state, ObservationState):
            raise BacktestValidationError("state must be an ObservationState")
        if not isinstance(self.fills, tuple) or any(
            not isinstance(fill, SimulatedFillRecord) for fill in self.fills
        ):
            raise BacktestValidationError("fills must be a tuple of SimulatedFillRecord values")
        if any(fill.signal_id != self.signal.signal_id for fill in self.fills):
            raise BacktestValidationError("fills must share the signal provenance")
        if any(fill.policy_id != self.policy_id for fill in self.fills):
            raise BacktestValidationError("fills must share the trade policy")
        if len({fill.fill_id for fill in self.fills}) != len(self.fills):
            raise BacktestValidationError("fills must not contain duplicate records")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        self._validate_lifecycle()
        object.__setattr__(self, "trade_id", sha256(self._content_bytes()).hexdigest())

    @property
    def lineage(self) -> MarketLineage:
        return self.signal.lineage

    @property
    def exit_ts_ns(self) -> int | None:
        return self.fills[-1].event_ts_ns if self.state is ObservationState.CLOSED else None

    def _validate_lifecycle(self) -> None:
        accounting = (self.gross_ticks, self.net_ticks, self.gross_r, self.net_r)
        if self.state is ObservationState.PENDING:
            if (
                self.fills
                or any(value is not None for value in accounting)
                or self.terminal_reason is not None
            ):
                raise BacktestValidationError(
                    "pending observations cannot contain fills or accounting"
                )
            return
        if self.state is ObservationState.OPEN:
            if (
                len(self.fills) != 1
                or self.fills[0].kind is not FillKind.ENTRY
                or any(value is not None for value in accounting)
                or self.terminal_reason is not None
            ):
                raise BacktestValidationError("open observations require exactly one entry fill")
            return
        if self.state is ObservationState.UNRESOLVED:
            if len(self.fills) > 1 or (self.fills and self.fills[0].kind is not FillKind.ENTRY):
                raise BacktestValidationError(
                    "unresolved observations may contain at most one entry fill"
                )
            if (
                any(value is not None for value in accounting)
                or self.terminal_reason not in _UNRESOLVED_REASONS
            ):
                raise BacktestValidationError(
                    "unresolved observations require an unresolved terminal reason"
                )
            return
        if self.state is not ObservationState.CLOSED:
            raise BacktestValidationError("unsupported observation state")
        if len(self.fills) != 2 or self.fills[0].kind is not FillKind.ENTRY:
            raise BacktestValidationError("closed trades require entry then exactly one exit fill")
        entry, exit_fill = self.fills
        expected_reason = _CLOSED_REASON_FOR_KIND.get(exit_fill.kind)
        if expected_reason is None or self.terminal_reason is not expected_reason:
            raise BacktestValidationError("closed trade terminal reason must match its exit fill")
        if exit_fill.event_ts_ns < entry.event_ts_ns:
            raise BacktestValidationError("closed trade exit cannot precede its entry")
        if exit_fill.event_ts_ns == entry.event_ts_ns and not (
            exit_fill.kind is FillKind.STOP and exit_fill.source_bar_id == entry.source_bar_id
        ):
            raise BacktestValidationError(
                "same-time entry and exit require a conservative same-bar stop"
            )
        if (
            not _is_plain_int(self.gross_ticks)
            or not _is_plain_int(self.net_ticks)
            or not isinstance(self.gross_r, ExactR)
            or not isinstance(self.net_r, ExactR)
        ):
            raise BacktestValidationError("closed trades require exact tick and R accounting")
        directional_ticks = (
            exit_fill.price_ticks - entry.price_ticks
            if self.signal.direction is Direction.LONG
            else entry.price_ticks - exit_fill.price_ticks
        )
        if self.gross_ticks != directional_ticks:
            raise BacktestValidationError("closed trade gross_ticks must match its simulated fills")
        if self.net_ticks > self.gross_ticks:
            raise BacktestValidationError("closed trade net_ticks cannot exceed gross_ticks")
        if self.net_ticks != self.gross_ticks - self.fees_ticks_round_turn:
            raise BacktestValidationError(
                "closed trade net_ticks must subtract round-turn fees exactly once"
            )
        planned_risk = abs(self.signal.entry_ticks - self.signal.stop_ticks)
        if self.gross_r != ExactR.from_ticks(self.gross_ticks, planned_risk):
            raise BacktestValidationError(
                "closed trade gross_r must match planned-risk tick accounting"
            )
        if self.net_r != ExactR.from_ticks(self.net_ticks, planned_risk):
            raise BacktestValidationError(
                "closed trade net_r must match planned-risk tick accounting"
            )

    def init_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "policy_id": self.policy_id,
            "fees_ticks_round_turn": self.fees_ticks_round_turn,
            "state": self.state,
            "fills": self.fills,
            "gross_ticks": self.gross_ticks,
            "net_ticks": self.net_ticks,
            "gross_r": self.gross_r,
            "net_r": self.net_r,
            "terminal_reason": self.terminal_reason,
            "schema_version": self.schema_version,
        }

    def _content_dict(self) -> dict[str, object]:
        return {
            "fills": [fill.canonical_dict() for fill in self.fills],
            "gross_r": self.gross_r.canonical_dict() if self.gross_r else None,
            "gross_ticks": self.gross_ticks,
            "fees_ticks_round_turn": self.fees_ticks_round_turn,
            "net_r": self.net_r.canonical_dict() if self.net_r else None,
            "net_ticks": self.net_ticks,
            "policy_id": self.policy_id,
            "schema_version": self.schema_version,
            "signal": self.signal.canonical_dict(),
            "state": self.state.value,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason else None,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "trade_id": self.trade_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class RunWarning:
    """A typed, deterministic research limitation with canonical provenance."""

    code: WarningCode
    detail: str
    references: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    warning_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.code, WarningCode):
            raise BacktestValidationError("code must be a WarningCode")
        _require_nonempty_string(self.detail, "detail")
        _require_sorted_unique_strings(self.references, "references")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(self, "warning_id", sha256(self._content_bytes()).hexdigest())

    def init_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "detail": self.detail,
            "references": self.references,
            "schema_version": self.schema_version,
        }

    def _content_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "references": list(self.references),
            "schema_version": self.schema_version,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "warning_id": self.warning_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class MetricGroup:
    """A physical-contract partition or same-root summary partition."""

    scope: MetricScope
    root: str
    instrument_id: int | None
    signal_type: SignalType
    execute_timeframe: Timeframe
    direction: Direction
    setup_type: SetupType
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MetricScope):
            raise BacktestValidationError("scope must be a MetricScope")
        if self.root not in {"NQ", "ES"}:
            raise BacktestValidationError("root must be one of NQ or ES")
        if self.scope is MetricScope.PHYSICAL_CONTRACT:
            _require_positive_int(self.instrument_id, "instrument_id")
        elif self.instrument_id is not None:
            raise BacktestValidationError("root summaries cannot name one instrument_id")
        if not isinstance(self.signal_type, SignalType):
            raise BacktestValidationError("signal_type must be a SignalType")
        if not isinstance(self.execute_timeframe, Timeframe):
            raise BacktestValidationError("execute_timeframe must be a Timeframe")
        if self.execute_timeframe is not TIMEFRAME_PLANS[self.signal_type].execute:
            raise BacktestValidationError(
                "execute_timeframe must match the signal type's fixed plan"
            )
        if not isinstance(self.direction, Direction):
            raise BacktestValidationError("direction must be a Direction")
        if not isinstance(self.setup_type, SetupType):
            raise BacktestValidationError("setup_type must be a SetupType")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction.value,
            "execute_timeframe": self.execute_timeframe.value,
            "instrument_id": self.instrument_id,
            "root": self.root,
            "schema_version": self.schema_version,
            "scope": self.scope.value,
            "setup_type": self.setup_type.value,
            "signal_type": self.signal_type.value,
        }

    @property
    def identity(self) -> str:
        return sha256(canonical_json_bytes(self.canonical_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class ExclusionGroup:
    """A suppression partition using only provenance SP2 actually supplies."""

    code: SuppressionCode
    root: str | None
    instrument_id: int | None
    signal_type: SignalType | None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.code, SuppressionCode):
            raise BacktestValidationError("code must be a SuppressionCode")
        if self.root is not None and self.root not in {"NQ", "ES"}:
            raise BacktestValidationError("root must be NQ, ES, or None")
        if self.instrument_id is not None:
            _require_positive_int(self.instrument_id, "instrument_id")
        if (self.root is None) != (self.instrument_id is None):
            raise BacktestValidationError(
                "root and instrument_id must either both be present or both be absent"
            )
        if self.signal_type is not None and not isinstance(self.signal_type, SignalType):
            raise BacktestValidationError("signal_type must be a SignalType or None")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "instrument_id": self.instrument_id,
            "root": self.root,
            "schema_version": self.schema_version,
            "signal_type": self.signal_type.value if self.signal_type else None,
        }

    @property
    def identity(self) -> str:
        return sha256(canonical_json_bytes(self.canonical_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class ExclusionMetric:
    """A descriptive suppression count, separate from trade outcomes."""

    group: ExclusionGroup
    count: int
    schema_version: str = SCHEMA_VERSION
    exclusion_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.group, ExclusionGroup):
            raise BacktestValidationError("group must be an ExclusionGroup")
        _require_positive_int(self.count, "count")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(
            self,
            "exclusion_id",
            sha256(canonical_json_bytes(self._content_dict())).hexdigest(),
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "group": self.group.canonical_dict(),
            "schema_version": self.schema_version,
        }

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "exclusion_id": self.exclusion_id}


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """One closed-trade point, ordered by exit time then trade identity."""

    trade_id: str
    exit_ts_ns: int
    cumulative_net_ticks: int
    cumulative_net_r: ExactR
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.trade_id, "trade_id")
        _require_nonnegative_int(self.exit_ts_ns, "exit_ts_ns")
        _require_nonnegative_or_signed_int(self.cumulative_net_ticks, "cumulative_net_ticks")
        if not isinstance(self.cumulative_net_r, ExactR):
            raise BacktestValidationError("cumulative_net_r must be an ExactR")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "cumulative_net_r": self.cumulative_net_r.canonical_dict(),
            "cumulative_net_ticks": self.cumulative_net_ticks,
            "exit_ts_ns": self.exit_ts_ns,
            "schema_version": self.schema_version,
            "trade_id": self.trade_id,
        }


@dataclass(frozen=True, slots=True)
class MetricRecord:
    """Descriptive exact metrics; no field is a live promotion or gate."""

    group: MetricGroup
    contract_count: int
    closed_count: int
    pending_count: int
    open_count: int
    unresolved_count: int
    win_count: int
    win_rate: ExactR | None
    expectancy_r: ExactR | None
    average_win_r: ExactR | None
    average_loss_r: ExactR | None
    maximum_drawdown_r: ExactR | None
    maximum_drawdown_ticks: int | None
    warning_codes: tuple[WarningCode, ...] = ()
    metrics_algorithm_version: str = METRICS_ALGORITHM_VERSION
    schema_version: str = SCHEMA_VERSION
    metric_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.group, MetricGroup):
            raise BacktestValidationError("group must be a MetricGroup")
        for name in (
            "contract_count",
            "closed_count",
            "pending_count",
            "open_count",
            "unresolved_count",
            "win_count",
        ):
            _require_nonnegative_int(getattr(self, name), name)
        if self.win_count > self.closed_count:
            raise BacktestValidationError("win_count cannot exceed closed_count")
        if self.contract_count < 1:
            raise BacktestValidationError(
                "contract_count must retain at least one physical contract"
            )
        for name in (
            "expectancy_r",
            "win_rate",
            "average_win_r",
            "average_loss_r",
            "maximum_drawdown_r",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, ExactR):
                raise BacktestValidationError(f"{name} must be an ExactR or None")
        if self.maximum_drawdown_ticks is not None:
            _require_nonnegative_int(self.maximum_drawdown_ticks, "maximum_drawdown_ticks")
        if self.closed_count == 0 and self.win_rate is not None:
            raise BacktestValidationError("win_rate must be None without closed trades")
        if self.closed_count > 0 and self.win_rate != ExactR.from_fraction(
            Fraction(self.win_count, self.closed_count)
        ):
            raise BacktestValidationError("win_rate must exactly match wins over closed trades")
        if self.group.scope is MetricScope.PHYSICAL_CONTRACT and self.contract_count != 1:
            raise BacktestValidationError("physical-contract metrics require contract_count 1")
        if not isinstance(self.warning_codes, tuple) or any(
            not isinstance(code, WarningCode) for code in self.warning_codes
        ):
            raise BacktestValidationError("warning_codes must be a tuple of WarningCode values")
        if tuple(
            sorted(self.warning_codes, key=lambda code: code.value)
        ) != self.warning_codes or len(set(self.warning_codes)) != len(self.warning_codes):
            raise BacktestValidationError("warning_codes must be sorted and unique")
        if self.closed_count < 30 and WarningCode.INSUFFICIENT_SAMPLE not in self.warning_codes:
            raise BacktestValidationError("small closed samples require insufficient_sample")
        _require_nonempty_string(self.metrics_algorithm_version, "metrics_algorithm_version")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(self, "metric_id", sha256(self._content_bytes()).hexdigest())

    def _content_dict(self) -> dict[str, object]:
        return {
            "average_loss_r": self.average_loss_r.canonical_dict() if self.average_loss_r else None,
            "average_win_r": self.average_win_r.canonical_dict() if self.average_win_r else None,
            "closed_count": self.closed_count,
            "contract_count": self.contract_count,
            "expectancy_r": self.expectancy_r.canonical_dict() if self.expectancy_r else None,
            "group": self.group.canonical_dict(),
            "maximum_drawdown_r": self.maximum_drawdown_r.canonical_dict()
            if self.maximum_drawdown_r
            else None,
            "maximum_drawdown_ticks": self.maximum_drawdown_ticks,
            "metrics_algorithm_version": self.metrics_algorithm_version,
            "open_count": self.open_count,
            "pending_count": self.pending_count,
            "schema_version": self.schema_version,
            "unresolved_count": self.unresolved_count,
            "warning_codes": [code.value for code in self.warning_codes],
            "win_count": self.win_count,
            "win_rate": self.win_rate.canonical_dict() if self.win_rate else None,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "metric_id": self.metric_id}


@dataclass(frozen=True, slots=True)
class HalfOpenInterval:
    """A precise [start, end) time window used to prevent fold leakage."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.start_ns, "start_ns")
        _require_nonnegative_int(self.end_ns, "end_ns")
        if self.start_ns >= self.end_ns:
            raise BacktestValidationError("half-open interval start_ns must be before end_ns")

    def canonical_dict(self) -> dict[str, int]:
        return {"end_ns": self.end_ns, "start_ns": self.start_ns}


@dataclass(frozen=True, slots=True)
class ChronologicalReplayFold:
    """One fresh-engine, non-optimizing chronological replay fold."""

    fold_id: str
    warmup: HalfOpenInterval
    context: HalfOpenInterval
    embargo: HalfOpenInterval
    evaluation: HalfOpenInterval
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_string(self.fold_id, "fold_id")
        for name in ("warmup", "context", "embargo", "evaluation"):
            if not isinstance(getattr(self, name), HalfOpenInterval):
                raise BacktestValidationError(f"{name} must be a HalfOpenInterval")
        if not (
            self.warmup.end_ns <= self.context.start_ns
            and self.context.end_ns <= self.embargo.start_ns
            and self.embargo.end_ns <= self.evaluation.start_ns
        ):
            raise BacktestValidationError(
                "fold intervals must be chronological and non-overlapping"
            )
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "context": self.context.canonical_dict(),
            "embargo": self.embargo.canonical_dict(),
            "evaluation": self.evaluation.canonical_dict(),
            "fold_id": self.fold_id,
            "schema_version": self.schema_version,
            "warmup": self.warmup.canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class ChronologicalReplayPlan:
    """A chronological measurement plan, explicitly not an optimizer or selector."""

    folds: tuple[ChronologicalReplayFold, ...]
    evidence_class: EvidenceClass = EvidenceClass.RETROSPECTIVE_REPLAY
    schema_version: str = SCHEMA_VERSION
    plan_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.folds, tuple) or not self.folds:
            raise BacktestValidationError("folds must be a non-empty tuple")
        if any(not isinstance(fold, ChronologicalReplayFold) for fold in self.folds):
            raise BacktestValidationError("folds must contain ChronologicalReplayFold values")
        ids = tuple(fold.fold_id for fold in self.folds)
        if len(set(ids)) != len(ids):
            raise BacktestValidationError("fold_id values must be unique")
        if (
            tuple(sorted(self.folds, key=lambda fold: (fold.evaluation.start_ns, fold.fold_id)))
            != self.folds
        ):
            raise BacktestValidationError("folds must be ordered chronologically by evaluation")
        for prior, current in zip(self.folds, self.folds[1:], strict=False):
            if prior.evaluation.end_ns > current.evaluation.start_ns:
                raise BacktestValidationError("fold evaluation intervals must not overlap")
        if self.evidence_class is not EvidenceClass.RETROSPECTIVE_REPLAY:
            raise BacktestValidationError("chronological replay must be retrospective_replay")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        object.__setattr__(self, "plan_id", sha256(self._content_bytes()).hexdigest())

    def _content_dict(self) -> dict[str, object]:
        return {
            "evidence_class": self.evidence_class.value,
            "folds": [fold.canonical_dict() for fold in self.folds],
            "schema_version": self.schema_version,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "plan_id": self.plan_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Immutable ordered research output that can never claim execution."""

    evidence_class: EvidenceClass
    status: BacktestStatus
    plan_id: str
    readiness_blockers: tuple[str, ...] = ()
    signals: tuple[SignalRecord, ...] = ()
    suppressions: tuple[Suppression, ...] = ()
    fills: tuple[SimulatedFillRecord, ...] = ()
    trades: tuple[TradeRecord, ...] = ()
    equity: tuple[EquityPoint, ...] = ()
    metrics: tuple[MetricRecord, ...] = ()
    exclusions: tuple[ExclusionMetric, ...] = ()
    warnings: tuple[RunWarning, ...] = ()
    execution: bool = False
    orders_placed: int = 0
    artifact_algorithm_version: str = ARTIFACT_ALGORITHM_VERSION
    schema_version: str = SCHEMA_VERSION
    run_id: str = field(init=False)
    manifest_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_class, EvidenceClass):
            raise BacktestValidationError("evidence_class must be an EvidenceClass")
        if not isinstance(self.status, BacktestStatus):
            raise BacktestValidationError("status must be a BacktestStatus")
        _require_sha256(self.plan_id, "plan_id")
        _require_sorted_unique_strings(self.readiness_blockers, "readiness_blockers")
        self._validate_ordered_outputs()
        if self.execution is not False:
            raise BacktestValidationError("execution must be false for research-only output")
        if self.orders_placed != 0:
            raise BacktestValidationError("orders_placed must be 0 for research-only output")
        _require_nonempty_string(self.artifact_algorithm_version, "artifact_algorithm_version")
        if self.schema_version != SCHEMA_VERSION:
            raise BacktestValidationError("unsupported schema_version")
        if self.status is BacktestStatus.BLOCKED:
            if not self.readiness_blockers:
                raise BacktestValidationError("blocked results require readiness blockers")
            if any(
                (
                    self.signals,
                    self.fills,
                    self.trades,
                    self.equity,
                    self.metrics,
                    self.exclusions,
                )
            ):
                raise BacktestValidationError("blocked results must have a zero trade population")
        elif self.readiness_blockers:
            raise BacktestValidationError("complete results cannot retain readiness blockers")
        object.__setattr__(self, "run_id", sha256(self._content_bytes()).hexdigest())
        object.__setattr__(self, "manifest_id", sha256(self.canonical_bytes()).hexdigest())

    @classmethod
    def blocked(
        cls,
        *,
        evidence_class: EvidenceClass,
        plan_id: str,
        readiness_blockers: tuple[str, ...],
    ) -> BacktestResult:
        return cls(
            evidence_class=evidence_class,
            status=BacktestStatus.BLOCKED,
            plan_id=plan_id,
            readiness_blockers=readiness_blockers,
        )

    def _validate_ordered_outputs(self) -> None:
        checks: tuple[tuple[object, type[object], str, Any], ...] = (
            (self.signals, SignalRecord, "signals", lambda value: value.signal_id),
            (self.suppressions, Suppression, "suppressions", lambda value: value.identity),
            (self.fills, SimulatedFillRecord, "fills", lambda value: value.fill_id),
            (self.trades, TradeRecord, "trades", lambda value: value.trade_id),
            (self.metrics, MetricRecord, "metrics", lambda value: value.metric_id),
            (
                self.exclusions,
                ExclusionMetric,
                "exclusions",
                lambda value: value.exclusion_id,
            ),
            (self.warnings, RunWarning, "warnings", lambda value: value.warning_id),
        )
        for values, record_type, name, key in checks:
            if not isinstance(values, tuple) or any(
                not isinstance(value, record_type) for value in values
            ):
                raise BacktestValidationError(
                    f"{name} must be a tuple of {record_type.__name__} values"
                )
            if tuple(sorted(values, key=key)) != values:
                raise BacktestValidationError(f"{name} must be canonically ordered")
        if not isinstance(self.equity, tuple) or any(
            not isinstance(point, EquityPoint) for point in self.equity
        ):
            raise BacktestValidationError("equity must be a tuple of EquityPoint values")
        if (
            tuple(sorted(self.equity, key=lambda point: (point.exit_ts_ns, point.trade_id)))
            != self.equity
        ):
            raise BacktestValidationError("equity must be ordered by exit_ts_ns and trade_id")

    def _content_dict(self) -> dict[str, object]:
        return {
            "artifact_algorithm_version": self.artifact_algorithm_version,
            "equity": [point.canonical_dict() for point in self.equity],
            "evidence_class": self.evidence_class.value,
            "execution": False,
            "exclusions": [exclusion.canonical_dict() for exclusion in self.exclusions],
            "fills": [fill.canonical_dict() for fill in self.fills],
            "metrics": [metric.canonical_dict() for metric in self.metrics],
            "orders_placed": 0,
            "plan_id": self.plan_id,
            "readiness_blockers": list(self.readiness_blockers),
            "schema_version": self.schema_version,
            "signals": [signal.canonical_dict() for signal in self.signals],
            "status": self.status.value,
            "suppressions": [suppression.canonical_dict() for suppression in self.suppressions],
            "trades": [trade.canonical_dict() for trade in self.trades],
            "warnings": [warning.canonical_dict() for warning in self.warnings],
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "run_id": self.run_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())
