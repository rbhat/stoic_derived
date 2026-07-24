"""Release-bound production composition for signal and lifecycle observation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.market_data.codec import normalize_batches
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.compiler import CompilationBlocker
from stoic_derived.signal_engine.engine import SignalEngine
from stoic_derived.signal_engine.model import MarketLineage

from .codec import decode_event
from .lifecycle import LifecycleTracker
from .model import LedgerError, LedgerEvent, LedgerLimits, ReconciliationResult
from .outbox import LedgerOutbox

LIFECYCLE_SOURCE = "stoic-ledger-lifecycle/v1"


@dataclass(frozen=True, slots=True)
class LedgerRunResult:
    """Truthful production outcome with explicit no-execution semantics."""

    status: str
    blockers: tuple[dict[str, object], ...]
    signal_count: int
    event_count: int
    execution: bool = False
    orders_placed: int = 0
    ledger: ReconciliationResult | None = None

    def __post_init__(self) -> None:
        if self.status not in {"blocked", "complete"}:
            raise LedgerError("status must be blocked or complete")
        if self.status == "blocked" and (
            self.signal_count != 0 or self.event_count != 0 or self.ledger is not None
        ):
            raise LedgerError("blocked production result must remain zero and ledger-free")
        if self.execution is not False or self.orders_placed != 0:
            raise LedgerError("SP4 can never declare execution or placed orders")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "blockers": list(self.blockers),
            "event_count": self.event_count,
            "execution": self.execution,
            "ledger": self.ledger.canonical_dict() if self.ledger else None,
            "orders_placed": self.orders_placed,
            "signal_count": self.signal_count,
            "status": self.status,
        }


def readiness(
    release_path: Path | str | None = None,
    expected_sha256: str | None = None,
    public_key: Ed25519PublicKey | bytes | None = None,
) -> LedgerRunResult:
    """Inspect the unchanged SP2 release boundary without writing any ledger."""
    creation = SignalEngine.from_release(release_path, expected_sha256, public_key)
    if creation.engine is None:
        return LedgerRunResult(
            status="blocked",
            blockers=_blockers(creation.readiness.blockers),
            signal_count=0,
            event_count=0,
        )
    return LedgerRunResult(
        status="complete",
        blockers=(),
        signal_count=0,
        event_count=0,
        ledger=LifecycleTracker(source=LIFECYCLE_SOURCE).result,
    )


def run_release_ledger(
    batches: Iterable[FinalizedSeriesBatch],
    *,
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    outbox: LedgerOutbox,
    remote_events: Iterable[LedgerEvent],
    source: str = LIFECYCLE_SOURCE,
    limits: LedgerLimits | None = None,
) -> LedgerRunResult:
    """Run signed-release SP2 and durably observe its lifecycle output."""
    selected_limits = limits or LedgerLimits()
    creation = SignalEngine.from_release(release_path, expected_sha256, public_key)
    if creation.engine is None:
        return LedgerRunResult(
            status="blocked",
            blockers=_blockers(creation.readiness.blockers),
            signal_count=0,
            event_count=0,
        )

    normalized = normalize_batches(batches)
    seed_by_id: dict[str, LedgerEvent] = {}
    for event in remote_events:
        if not isinstance(event, LedgerEvent):
            raise LedgerError("remote_events must contain LedgerEvent values")
        seed_by_id[event.event_id] = event
    for payload in outbox.undelivered_event_bytes():
        event = decode_event(payload, limits=selected_limits)
        existing = seed_by_id.setdefault(event.event_id, event)
        if existing.canonical_bytes() != event.canonical_bytes():
            raise LedgerError("remote and local event ID bytes disagree")
    tracker = LifecycleTracker(
        source=source,
        limits=selected_limits,
        events=tuple(seed_by_id[event_id] for event_id in sorted(seed_by_id)),
    )
    engine = creation.engine
    active_by_root = _active_lineages(tracker.result)
    signal_count = 0
    inserted_event_count = 0

    for batch in normalized:
        previous = active_by_root.get(batch.lineage.root)
        if previous is not None and previous != batch.lineage:
            retired = tracker.retire_lineage(
                previous.identity,
                boundary_ts_ns=_roll_boundary(batch),
            )
            inserted_event_count += len(outbox.enqueue(retired))
            engine.retire_lineage(previous)
        active_by_root[batch.lineage.root] = batch.lineage

        signal_batch = engine.ingest(batch)
        signal_count += len(signal_batch.signals)
        signal_events = tracker.observe_signals(signal_batch.signals)
        inserted_event_count += len(outbox.enqueue(signal_events))
        lifecycle_events = tracker.ingest(batch)
        inserted_event_count += len(outbox.enqueue(lifecycle_events))

    return LedgerRunResult(
        status="complete",
        blockers=(),
        signal_count=signal_count,
        event_count=inserted_event_count,
        ledger=tracker.result,
    )


def _blockers(values: tuple[CompilationBlocker, ...]) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for blocker in values:
        result.append(
            {
                "code": blocker.code.value,
                "message": blocker.message,
                "rule_id": blocker.rule_id,
            }
        )
    return tuple(result)


def _active_lineages(result: ReconciliationResult) -> dict[str, MarketLineage]:
    by_root: dict[str, MarketLineage] = {}
    for view in result.views:
        for record in view.records:
            if record.state.value not in {"pending", "active"}:
                continue
            existing = by_root.setdefault(record.signal.lineage.root, record.signal.lineage)
            if existing != record.signal.lineage:
                raise LedgerError("multiple active physical lineages share one root")
    return by_root


def _roll_boundary(batch: FinalizedSeriesBatch) -> int:
    return batch.finalized_through_ns


__all__ = [
    "LIFECYCLE_SOURCE",
    "LedgerRunResult",
    "readiness",
    "run_release_ledger",
]
