"""Immutable contracts for observational SP4 lifecycle ledgers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any, TypeGuard

from stoic_derived.market_data.model import FinalBar, QualityState
from stoic_derived.signal_engine.model import MarketLineage, SignalRecord, SignalType

SCHEMA_VERSION = "ledger-event/v1"
VIEW_SCHEMA_VERSION = "ledger-view/v1"


class LedgerError(ValueError):
    """Base class for fail-closed ledger validation errors."""


class EventKind(StrEnum):
    """Closed vocabulary of observational lifecycle evidence."""

    SIGNAL_OBSERVED = "signal_observed"
    ENTRY_OBSERVED = "entry_observed"
    STOP_OBSERVED = "stop_observed"
    TARGET_OBSERVED = "target_observed"
    SESSION_FLATTEN_OBSERVED = "session_flatten_observed"
    UNRESOLVED_OBSERVED = "unresolved_observed"


class LedgerState(StrEnum):
    """Every complete signal is in exactly one of these states."""

    PENDING = "pending"
    ACTIVE = "active"
    CLOSED = "closed"
    UNRESOLVED = "unresolved"


class ConflictCode(StrEnum):
    """Stable reasons why immutable evidence cannot produce one trusted chain."""

    MISSING_SIGNAL = "missing_signal"
    SIGNAL_CONFLICT = "signal_conflict"
    INVALID_TRANSITION = "invalid_transition"
    EVENT_FORK = "event_fork"
    ORPHAN_EVENT = "orphan_event"
    TERMINAL_SUCCESSOR = "terminal_successor"
    CROSS_LINEAGE = "cross_lineage"
    POSITION_CUTOFF = "position_cutoff"


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Encode normalized JSON deterministically and without binary floats."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _plain_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_nonnegative_int(value: object, name: str) -> int:
    if not _plain_int(value) or value < 0:
        raise LedgerError(f"{name} must be a non-negative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not _plain_int(value) or value <= 0:
        raise LedgerError(f"{name} must be a positive integer")
    return value


def _require_nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerError(f"{name} must be a non-empty string")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise LedgerError(f"{name} must be a lowercase SHA-256 digest")
    return value


def signal_sha256(signal: SignalRecord) -> str:
    """Digest the complete public signal record, including its claimed ID."""
    if not isinstance(signal, SignalRecord):
        raise LedgerError("signal must be a SignalRecord")
    return sha256(signal.canonical_bytes()).hexdigest()


def source_partition(source: str) -> str:
    """Map arbitrary logical source names to a safe stable partition key."""
    _require_nonempty(source, "source")
    return sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LedgerLimits:
    """Explicit safety bounds for every retained or transferred collection."""

    max_event_bytes: int = 256_000
    max_events_per_reconcile: int = 100_000
    max_signals_per_type: int = 25_000
    max_active_signals: int = 10_000
    max_source_partitions: int = 1_000
    max_market_observations: int = 100_000
    max_retained_gaps: int = 10_000
    max_outbox_rows: int = 100_000
    max_dispatch_batch: int = 1_000
    max_delivery_attempts: int = 12
    max_drive_pages: int = 1_000
    max_download_bytes: int = 256_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _require_positive_int(getattr(self, name), name)
        if self.max_download_bytes < self.max_event_bytes:
            raise LedgerError("max_download_bytes must cover max_event_bytes")
        if self.max_dispatch_batch > self.max_outbox_rows:
            raise LedgerError("max_dispatch_batch cannot exceed max_outbox_rows")


_MARKET_KINDS = frozenset(
    {
        EventKind.ENTRY_OBSERVED,
        EventKind.STOP_OBSERVED,
        EventKind.TARGET_OBSERVED,
        EventKind.SESSION_FLATTEN_OBSERVED,
    }
)


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """One immutable source assertion about a signal lifecycle."""

    kind: EventKind
    signal_type: SignalType
    signal_id: str
    signal_sha256: str
    lineage: MarketLineage
    observed_ts_ns: int
    source: str
    predecessor_semantic_id: str | None = None
    signal: SignalRecord | None = None
    market_bar: FinalBar | None = None
    price_ticks: int | None = None
    reason: str | None = None
    fence_token: int | None = None
    schema_version: str = SCHEMA_VERSION
    source_partition: str = field(init=False)
    semantic_id: str = field(init=False)
    event_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EventKind):
            raise LedgerError("kind must be an EventKind")
        if not isinstance(self.signal_type, SignalType):
            raise LedgerError("signal_type must be a SignalType")
        _require_sha256(self.signal_id, "signal_id")
        _require_sha256(self.signal_sha256, "signal_sha256")
        if not isinstance(self.lineage, MarketLineage):
            raise LedgerError("lineage must be a MarketLineage")
        _require_nonnegative_int(self.observed_ts_ns, "observed_ts_ns")
        _require_nonempty(self.source, "source")
        if self.predecessor_semantic_id is not None:
            _require_sha256(self.predecessor_semantic_id, "predecessor_semantic_id")
        if self.fence_token is not None:
            _require_positive_int(self.fence_token, "fence_token")
        if self.schema_version != SCHEMA_VERSION:
            raise LedgerError("unsupported schema_version")

        if self.kind is EventKind.SIGNAL_OBSERVED:
            self._validate_signal_event()
        elif self.kind in _MARKET_KINDS:
            self._validate_market_event()
        elif self.kind is EventKind.UNRESOLVED_OBSERVED:
            self._validate_unresolved_event()
        else:  # pragma: no cover - exhaustive enum guard
            raise LedgerError("unsupported event kind")

        partition = source_partition(self.source)
        object.__setattr__(self, "source_partition", partition)
        semantic_id = sha256(canonical_json_bytes(self._semantic_dict())).hexdigest()
        object.__setattr__(self, "semantic_id", semantic_id)
        event_id = sha256(canonical_json_bytes(self._content_dict())).hexdigest()
        object.__setattr__(self, "event_id", event_id)

    def _validate_signal_event(self) -> None:
        if self.signal is None:
            raise LedgerError("signal_observed requires the complete signal")
        if self.predecessor_semantic_id is not None:
            raise LedgerError("signal_observed cannot have a predecessor")
        if self.market_bar is not None or self.price_ticks is not None or self.reason is not None:
            raise LedgerError("signal_observed cannot carry market or terminal evidence")
        if self.fence_token is not None:
            raise LedgerError("signal_observed cannot carry a watchdog fence")
        if self.signal.signal_type is not self.signal_type:
            raise LedgerError("signal event Type does not match signal")
        if self.signal.signal_id != self.signal_id:
            raise LedgerError("signal event ID does not match signal")
        if signal_sha256(self.signal) != self.signal_sha256:
            raise LedgerError("signal event digest does not match signal")
        if self.signal.lineage != self.lineage:
            raise LedgerError("signal event lineage does not match signal")
        if self.observed_ts_ns != self.signal.signal_ts_ns:
            raise LedgerError("signal observation timestamp must equal signal timestamp")

    def _validate_market_event(self) -> None:
        if self.signal is not None:
            raise LedgerError("lifecycle observations reference, not repeat, the signal")
        if self.predecessor_semantic_id is None:
            raise LedgerError("lifecycle observation requires a predecessor")
        if not isinstance(self.market_bar, FinalBar):
            raise LedgerError("market lifecycle observation requires a FinalBar")
        if self.market_bar.quality is not QualityState.COMPLETE:
            raise LedgerError("market lifecycle observation requires a complete bar")
        if MarketLineage.from_final_bar(self.market_bar) != self.lineage:
            raise LedgerError("market bar lineage does not match event lineage")
        _require_positive_int(self.price_ticks, "price_ticks")
        if self.observed_ts_ns != self.market_bar.end_ns:
            raise LedgerError("market observation timestamp must equal source bar end")
        if self.reason is not None:
            raise LedgerError("market lifecycle observation cannot carry unresolved reason")
        if self.kind is not EventKind.SESSION_FLATTEN_OBSERVED and self.fence_token is not None:
            raise LedgerError("only watchdog terminal observations may carry a fence")

    def _validate_unresolved_event(self) -> None:
        if self.signal is not None:
            raise LedgerError("unresolved observation references, not repeats, the signal")
        if self.predecessor_semantic_id is None:
            raise LedgerError("unresolved observation requires a predecessor")
        if self.price_ticks is not None:
            raise LedgerError("unresolved observation cannot invent a price")
        _require_nonempty(self.reason, "reason")
        if self.market_bar is not None:
            if MarketLineage.from_final_bar(self.market_bar) != self.lineage:
                raise LedgerError("unresolved market bar lineage does not match")
            if self.observed_ts_ns != self.market_bar.end_ns:
                raise LedgerError("unresolved timestamp must equal source bar end")

    @classmethod
    def for_signal(cls, signal: SignalRecord, *, source: str) -> LedgerEvent:
        """Create the root observation for one complete SP2 signal."""
        return cls(
            kind=EventKind.SIGNAL_OBSERVED,
            signal_type=signal.signal_type,
            signal_id=signal.signal_id,
            signal_sha256=signal_sha256(signal),
            lineage=signal.lineage,
            observed_ts_ns=signal.signal_ts_ns,
            source=source,
            signal=signal,
        )

    @classmethod
    def for_market(
        cls,
        kind: EventKind,
        signal: SignalRecord,
        *,
        predecessor_semantic_id: str,
        market_bar: FinalBar,
        price_ticks: int,
        source: str,
        fence_token: int | None = None,
    ) -> LedgerEvent:
        """Create an entry/stop/target/cutoff market observation."""
        if kind not in _MARKET_KINDS:
            raise LedgerError("kind must be a market lifecycle observation")
        return cls(
            kind=kind,
            signal_type=signal.signal_type,
            signal_id=signal.signal_id,
            signal_sha256=signal_sha256(signal),
            lineage=signal.lineage,
            observed_ts_ns=market_bar.end_ns,
            source=source,
            predecessor_semantic_id=predecessor_semantic_id,
            market_bar=market_bar,
            price_ticks=price_ticks,
            fence_token=fence_token,
        )

    @classmethod
    def for_unresolved(
        cls,
        signal: SignalRecord,
        *,
        predecessor_semantic_id: str,
        observed_ts_ns: int,
        reason: str,
        source: str,
        market_bar: FinalBar | None = None,
        fence_token: int | None = None,
    ) -> LedgerEvent:
        """Create an explicit non-price terminal observation."""
        return cls(
            kind=EventKind.UNRESOLVED_OBSERVED,
            signal_type=signal.signal_type,
            signal_id=signal.signal_id,
            signal_sha256=signal_sha256(signal),
            lineage=signal.lineage,
            observed_ts_ns=observed_ts_ns,
            source=source,
            predecessor_semantic_id=predecessor_semantic_id,
            market_bar=market_bar,
            reason=reason,
            fence_token=fence_token,
        )

    def _semantic_dict(self) -> dict[str, object]:
        return {
            "broker_fill_claimed": False,
            "event_kind": self.kind.value,
            "execution": False,
            "lineage": self.lineage.canonical_dict(),
            "market_bar": self.market_bar.canonical_dict() if self.market_bar else None,
            "observed_ts_ns": self.observed_ts_ns,
            "orders_placed": 0,
            "predecessor_semantic_id": self.predecessor_semantic_id,
            "price_ticks": self.price_ticks,
            "reason": self.reason,
            "schema_version": self.schema_version,
            "signal": self.signal.canonical_dict() if self.signal else None,
            "signal_id": self.signal_id,
            "signal_sha256": self.signal_sha256,
            "signal_type": self.signal_type.value,
        }

    def _content_dict(self) -> dict[str, object]:
        return {
            **self._semantic_dict(),
            "fence_token": self.fence_token,
            "semantic_id": getattr(self, "semantic_id", None),
            "source": self.source,
            "source_partition": source_partition(self.source),
        }

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "event_id": self.event_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class LedgerConflict:
    """One deterministic explanation for an unresolved reconciled view."""

    code: ConflictCode
    signal_type: SignalType
    signal_id: str
    semantic_ids: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ConflictCode):
            raise LedgerError("code must be a ConflictCode")
        if not isinstance(self.signal_type, SignalType):
            raise LedgerError("signal_type must be a SignalType")
        _require_sha256(self.signal_id, "signal_id")
        if tuple(sorted(set(self.semantic_ids))) != self.semantic_ids:
            raise LedgerError("semantic_ids must be sorted and unique")
        for semantic_id in self.semantic_ids:
            _require_sha256(semantic_id, "semantic_id")
        _require_nonempty(self.detail, "detail")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "semantic_ids": list(self.semantic_ids),
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
        }


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    """Deterministic materialized state for one exact SP2 signal."""

    signal: SignalRecord
    state: LedgerState
    current_semantic_id: str
    contributing_event_ids: tuple[str, ...]
    entry_observed_ts_ns: int | None = None
    entry_price_ticks: int | None = None
    close_observed_ts_ns: int | None = None
    close_price_ticks: int | None = None
    terminal_reason: str | None = None
    conflicts: tuple[LedgerConflict, ...] = ()
    schema_version: str = VIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.signal, SignalRecord):
            raise LedgerError("signal must be a SignalRecord")
        if not isinstance(self.state, LedgerState):
            raise LedgerError("state must be a LedgerState")
        _require_sha256(self.current_semantic_id, "current_semantic_id")
        if tuple(sorted(set(self.contributing_event_ids))) != self.contributing_event_ids:
            raise LedgerError("contributing_event_ids must be sorted and unique")
        for event_id in self.contributing_event_ids:
            _require_sha256(event_id, "event_id")
        for name in ("entry_observed_ts_ns", "close_observed_ts_ns"):
            value = getattr(self, name)
            if value is not None:
                _require_nonnegative_int(value, name)
        for name in ("entry_price_ticks", "close_price_ticks"):
            value = getattr(self, name)
            if value is not None:
                _require_positive_int(value, name)
        if self.state is LedgerState.PENDING and any(
            value is not None
            for value in (
                self.entry_observed_ts_ns,
                self.entry_price_ticks,
                self.close_observed_ts_ns,
                self.close_price_ticks,
                self.terminal_reason,
            )
        ):
            raise LedgerError("pending records cannot carry entry or terminal values")
        if self.state is LedgerState.ACTIVE:
            if self.entry_observed_ts_ns is None or self.entry_price_ticks is None:
                raise LedgerError("active records require entry observation")
            if (
                self.close_observed_ts_ns is not None
                or self.close_price_ticks is not None
                or self.terminal_reason is not None
            ):
                raise LedgerError("active records cannot carry terminal values")
        if self.state is LedgerState.CLOSED and (
            self.entry_observed_ts_ns is None
            or self.entry_price_ticks is None
            or self.close_observed_ts_ns is None
            or self.close_price_ticks is None
            or self.terminal_reason is None
        ):
            raise LedgerError("closed records require entry and close observations")
        if self.state is LedgerState.UNRESOLVED and self.terminal_reason is None:
            raise LedgerError("unresolved records require a terminal reason")
        if self.conflicts and self.state is not LedgerState.UNRESOLVED:
            raise LedgerError("conflicts require unresolved state")
        if self.schema_version != VIEW_SCHEMA_VERSION:
            raise LedgerError("unsupported view schema_version")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "close_observed_ts_ns": self.close_observed_ts_ns,
            "close_price_ticks": self.close_price_ticks,
            "conflicts": [conflict.canonical_dict() for conflict in self.conflicts],
            "contributing_event_ids": list(self.contributing_event_ids),
            "current_semantic_id": self.current_semantic_id,
            "entry_observed_ts_ns": self.entry_observed_ts_ns,
            "entry_price_ticks": self.entry_price_ticks,
            "schema_version": self.schema_version,
            "signal": self.signal.canonical_dict(),
            "state": self.state.value,
            "terminal_reason": self.terminal_reason,
        }


@dataclass(frozen=True, slots=True)
class LedgerView:
    """One logically separate, deterministically ordered Type ledger."""

    signal_type: SignalType
    records: tuple[LedgerRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.signal_type, SignalType):
            raise LedgerError("signal_type must be a SignalType")
        if any(record.signal.signal_type is not self.signal_type for record in self.records):
            raise LedgerError("every record must belong to the view Type")
        if tuple(sorted(self.records, key=lambda item: item.signal.signal_id)) != self.records:
            raise LedgerError("records must be ordered by signal_id")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "records": [record.canonical_dict() for record in self.records],
            "signal_type": self.signal_type.value,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """All four Type views plus globally ordered conflict evidence."""

    views: tuple[LedgerView, ...]
    conflicts: tuple[LedgerConflict, ...]

    def __post_init__(self) -> None:
        expected = tuple(sorted(SignalType, key=lambda item: item.value))
        if tuple(view.signal_type for view in self.views) != expected:
            raise LedgerError("views must contain every Signal Type in canonical order")
        expected_conflicts = tuple(
            sorted(
                self.conflicts,
                key=lambda item: (
                    item.signal_type.value,
                    item.signal_id,
                    item.code.value,
                    item.semantic_ids,
                ),
            )
        )
        if self.conflicts != expected_conflicts:
            raise LedgerError("conflicts must be in canonical order")

    def for_type(self, signal_type: SignalType) -> LedgerView:
        for view in self.views:
            if view.signal_type is signal_type:
                return view
        raise LedgerError("missing Type view")  # pragma: no cover

    def canonical_dict(self) -> dict[str, object]:
        return {
            "conflicts": [conflict.canonical_dict() for conflict in self.conflicts],
            "execution": False,
            "orders_placed": 0,
            "views": [view.canonical_dict() for view in self.views],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


__all__ = [
    "SCHEMA_VERSION",
    "VIEW_SCHEMA_VERSION",
    "ConflictCode",
    "EventKind",
    "LedgerConflict",
    "LedgerError",
    "LedgerEvent",
    "LedgerLimits",
    "LedgerRecord",
    "LedgerState",
    "LedgerView",
    "ReconciliationResult",
    "canonical_json_bytes",
    "signal_sha256",
    "source_partition",
]
