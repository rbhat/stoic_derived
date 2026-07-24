"""Fail-closed SP4 authority reads and exact observational projection."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Literal, Protocol, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.ledger.codec import decode_event
from stoic_derived.ledger.drive import DriveLedgerError, DriveLedgerStore
from stoic_derived.ledger.model import LedgerRecord, LedgerState, ReconciliationResult
from stoic_derived.ledger.outbox import LedgerOutbox
from stoic_derived.ledger.reconcile import reconcile_events
from stoic_derived.ledger.runner import readiness
from stoic_derived.signal_engine.model import Direction

from .models import (
    ConflictResponse,
    ExactRResponse,
    LedgerBlocked,
    LedgerErrorState,
    LedgerReady,
    LedgerSnapshotResponse,
    ObservationResponse,
)


def utc_string(timestamp_ns: int) -> str:
    """Serialize an integer UTC nanosecond timestamp without local conversion."""
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    value = datetime.fromtimestamp(seconds, tz=UTC)
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    fraction = f"{nanoseconds:09d}".rstrip("0")
    return f"{base}{f'.{fraction}' if fraction else ''}Z"


def exact_r_display(value: Fraction) -> str:
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    scale = max(twos, fives)
    sign = "-" if value.numerator < 0 else ""
    scaled = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(scaled).zfill(scale + 1)
    return f"{sign}{digits[:-scale]}.{digits[-scale:]}" if scale else f"{sign}{digits}"


def _project_record(record: LedgerRecord, *, generated_at_ns: int) -> ObservationResponse:
    signal = record.signal
    pnl_ticks: int | None = None
    pnl_r: ExactRResponse | None = None
    if record.state is LedgerState.CLOSED:
        if record.entry_price_ticks is None or record.close_price_ticks is None:
            raise ValueError("closed ledger record is missing observed prices")
        if signal.direction is Direction.LONG:
            pnl_ticks = record.close_price_ticks - record.entry_price_ticks
        else:
            pnl_ticks = record.entry_price_ticks - record.close_price_ticks
        planned_risk = abs(signal.entry_ticks - signal.stop_ticks)
        exact = Fraction(pnl_ticks, planned_risk)
        pnl_r = ExactRResponse(
            numerator=exact.numerator,
            denominator=exact.denominator,
            display=exact_r_display(exact),
        )

    hold_seconds: int | None = None
    if record.entry_observed_ts_ns is not None:
        end_ns = (
            record.close_observed_ts_ns
            if record.close_observed_ts_ns is not None
            else generated_at_ns
        )
        hold_seconds = max(0, (end_ns - record.entry_observed_ts_ns) // 1_000_000_000)

    return ObservationResponse(
        signal_id=signal.signal_id,
        instrument=cast(Literal["NQ", "ES"], signal.instrument),
        signal_type=signal.signal_type.value,
        state=record.state.value,
        direction=signal.direction.value,
        setup_type=signal.setup_type.value,
        confidence=signal.confidence,
        signal_ts_utc=utc_string(signal.signal_ts_ns),
        planned_entry_price_ticks=signal.entry_ticks,
        planned_stop_price_ticks=signal.stop_ticks,
        planned_target_price_ticks=signal.target_ticks,
        entry_observed_ts_utc=(
            utc_string(record.entry_observed_ts_ns)
            if record.entry_observed_ts_ns is not None
            else None
        ),
        entry_observed_price_ticks=record.entry_price_ticks,
        close_observed_ts_utc=(
            utc_string(record.close_observed_ts_ns)
            if record.close_observed_ts_ns is not None
            else None
        ),
        close_observed_price_ticks=record.close_price_ticks,
        terminal_reason=record.terminal_reason,
        observed_pnl_ticks=pnl_ticks,
        observed_pnl_r=pnl_r,
        hold_seconds=hold_seconds,
        conflicts=tuple(
            ConflictResponse(code=conflict.code.value, detail=conflict.detail)
            for conflict in record.conflicts
        ),
    )


def project_reconciliation(
    result: ReconciliationResult,
    *,
    generated_at_ns: int,
) -> LedgerReady:
    projected = tuple(
        _project_record(record, generated_at_ns=generated_at_ns)
        for view in result.views
        for record in view.records
    )
    order = {
        "Scalp": 0,
        "Day": 1,
        "Swing": 2,
        "Position": 3,
    }

    def key(item: ObservationResponse) -> tuple[int, str, str]:
        return (order[item.signal_type], item.signal_ts_utc, item.signal_id)

    return LedgerReady(
        open_observations=tuple(
            sorted(
                (
                    item
                    for item in projected
                    if item.state in {LedgerState.PENDING.value, LedgerState.ACTIVE.value}
                ),
                key=key,
                reverse=True,
            )
        ),
        closed_observations=tuple(
            sorted(
                (item for item in projected if item.state == LedgerState.CLOSED.value),
                key=key,
                reverse=True,
            )
        ),
        unresolved_observations=tuple(
            sorted(
                (item for item in projected if item.state == LedgerState.UNRESOLVED.value),
                key=key,
                reverse=True,
            )
        ),
    )


class LedgerAuthority(Protocol):
    def snapshot(self, *, generated_at_ns: int) -> LedgerSnapshotResponse: ...

    def refresh(self, *, generated_at_ns: int) -> LedgerSnapshotResponse: ...

    def publish(self, *, generated_at_ns: int) -> tuple[LedgerSnapshotResponse, int]: ...

    def drive_status(self) -> tuple[bool, str, str | None]: ...

    def outbox_status(self) -> tuple[int, int, int]: ...


class ProductionLedgerAuthority:
    """The sole production projection: release gate, Drive, undelivered outbox."""

    def __init__(
        self,
        *,
        outbox: LedgerOutbox,
        drive_store: DriveLedgerStore | None,
        release_path: Path | str | None,
        release_sha256: str | None,
        release_public_key: Ed25519PublicKey | bytes | None,
    ) -> None:
        self._outbox = outbox
        self._drive_store = drive_store
        self._release_path = release_path
        self._release_sha256 = release_sha256
        self._release_public_key = release_public_key

    def snapshot(self, *, generated_at_ns: int) -> LedgerSnapshotResponse:
        preflight = readiness(
            self._release_path,
            self._release_sha256,
            self._release_public_key,
        )
        if preflight.status == "blocked":
            blockers = tuple(
                sorted({f"{item['code']}: {item['message']}" for item in preflight.blockers})
            )
            return LedgerSnapshotResponse(
                generated_at_utc=utc_string(generated_at_ns),
                ledger=LedgerBlocked(blockers=blockers),
            )
        if self._drive_store is None:
            return LedgerSnapshotResponse(
                generated_at_utc=utc_string(generated_at_ns),
                ledger=LedgerBlocked(blockers=("Drive ledger configuration is unavailable",)),
            )
        try:
            self._drive_store.verify_acknowledged(self._outbox)
            by_id = {event.event_id: event for event in self._drive_store.read_events()}
            for payload in self._outbox.undelivered_event_bytes():
                event = decode_event(payload)
                existing = by_id.setdefault(event.event_id, event)
                if existing.canonical_bytes() != event.canonical_bytes():
                    raise DriveLedgerError("Drive and undelivered outbox event bytes disagree")
            result = reconcile_events(tuple(by_id[event_id] for event_id in sorted(by_id)))
            projection: LedgerReady | LedgerErrorState = project_reconciliation(
                result,
                generated_at_ns=generated_at_ns,
            )
        except Exception as exc:
            if not isinstance(exc, (DriveLedgerError, OSError, ValueError)):
                raise
            projection = LedgerErrorState(detail="Verified ledger authority is unavailable")
        return LedgerSnapshotResponse(
            generated_at_utc=utc_string(generated_at_ns),
            ledger=projection,
        )

    def refresh(self, *, generated_at_ns: int) -> LedgerSnapshotResponse:
        return self.snapshot(generated_at_ns=generated_at_ns)

    def publish(self, *, generated_at_ns: int) -> tuple[LedgerSnapshotResponse, int]:
        snapshot = self.snapshot(generated_at_ns=generated_at_ns)
        if snapshot.ledger.status != "ready" or self._drive_store is None:
            return snapshot, 0
        published = self._drive_store.publish_pending(self._outbox)
        return self.snapshot(generated_at_ns=generated_at_ns), len(published)

    def drive_status(self) -> tuple[bool, str, str | None]:
        if self._drive_store is None:
            return False, "Drive authority is not configured", None
        state = self._drive_store.readiness()
        return (
            state.ready,
            (
                "Drive authority is verified"
                if state.ready
                else "Drive authority verification failed"
            ),
            state.principal,
        )

    def outbox_status(self) -> tuple[int, int, int]:
        pending = self._outbox.pending()
        acknowledged = self._outbox.acknowledged()
        return (
            len(pending),
            len(acknowledged),
            max((item.attempts for item in pending), default=0),
        )


__all__ = [
    "LedgerAuthority",
    "ProductionLedgerAuthority",
    "exact_r_display",
    "project_reconciliation",
    "utc_string",
]
