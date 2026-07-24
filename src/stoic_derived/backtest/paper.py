"""Incremental, non-executing paper observations over committed SP1 batches.

This module keeps paper validation deliberately observational.  Its public
entry point accepts a pinned release boundary and immutable committed batches;
it has no engine, strategy, signal, fixture, broker, or order-routing input.
Checkpoints retain canonical market evidence so a restart deterministically
replays state instead of serializing a mutable engine.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.backtest.codec import batch_identity, batch_projection, normalize_batches
from stoic_derived.backtest.model import (
    BacktestResult,
    BacktestStatus,
    EvidenceClass,
    HalfOpenInterval,
    ObservationReason,
    ObservationState,
    SimulationPolicy,
    TradeRecord,
    canonical_json_bytes,
)
from stoic_derived.backtest.runner import _run_release_replay
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch

_PAPER_SCHEMA_VERSION = "paper-checkpoint/v1"


class PaperValidationError(ValueError):
    """Raised when a paper checkpoint or resume request is unsafe."""


class PaperStatus(StrEnum):
    """The operational paper state, distinct from a result's research status."""

    BLOCKED = "blocked"
    ACTIVE = "active"
    COMPLETE = "complete"


def _require_sha256_or_none(value: object, name: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperValidationError(f"{name} must be a lowercase SHA-256 hex digest or None")
    return value


def _key_fingerprint(public_key: Ed25519PublicKey | bytes | None) -> str | None:
    if public_key is None:
        return None
    if isinstance(public_key, bytes):
        return sha256(public_key).hexdigest()
    if isinstance(public_key, Ed25519PublicKey):
        raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return sha256(raw).hexdigest()
    raise PaperValidationError("public_key must be Ed25519PublicKey, bytes, or None")


def _active_state_digest(trades: tuple[TradeRecord, ...]) -> str:
    return sha256(
        canonical_json_bytes({"active_observations": [trade.canonical_dict() for trade in trades]})
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperCheckpoint:
    """Immutable, content-addressed restart evidence for one paper horizon.

    ``accepted_batches`` is intentionally complete canonical evidence rather
    than a file path or an opaque host-local cursor.  The active records make
    the state digest auditable while resume still reconstructs all state by
    replaying the batches through the release-bound runner.
    """

    release_sha256: str | None
    signing_key_fingerprint: str | None
    policy_id: str
    horizon: HalfOpenInterval
    accepted_batches: tuple[FinalizedSeriesBatch, ...]
    active_observations: tuple[TradeRecord, ...]
    observed_through_ns: int
    status: PaperStatus
    complete: bool
    execution: bool = False
    orders_placed: int = 0
    schema_version: str = _PAPER_SCHEMA_VERSION
    active_state_digest: str = field(init=False)
    checkpoint_id: str = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256_or_none(self.release_sha256, "release_sha256")
        _require_sha256_or_none(self.signing_key_fingerprint, "signing_key_fingerprint")
        _require_sha256_or_none(self.policy_id, "policy_id")
        if not isinstance(self.horizon, HalfOpenInterval):
            raise PaperValidationError("horizon must be a HalfOpenInterval")
        if not isinstance(self.accepted_batches, tuple) or any(
            not isinstance(batch, FinalizedSeriesBatch) for batch in self.accepted_batches
        ):
            raise PaperValidationError(
                "accepted_batches must be a tuple of FinalizedSeriesBatch values"
            )
        try:
            normalized = normalize_batches(self.accepted_batches)
        except ValueError as exc:
            raise PaperValidationError(
                "accepted_batches must be canonical and non-conflicting"
            ) from exc
        if normalized != self.accepted_batches:
            raise PaperValidationError("accepted_batches must not contain replay duplicates")
        if not isinstance(self.active_observations, tuple) or any(
            not isinstance(trade, TradeRecord) for trade in self.active_observations
        ):
            raise PaperValidationError("active_observations must be a tuple of TradeRecord values")
        if any(
            trade.state not in {ObservationState.PENDING, ObservationState.OPEN}
            for trade in self.active_observations
        ):
            raise PaperValidationError(
                "active_observations must contain only pending or open records"
            )
        if (
            tuple(sorted(self.active_observations, key=lambda trade: trade.trade_id))
            != self.active_observations
        ):
            raise PaperValidationError("active_observations must be canonically ordered")
        if len({trade.trade_id for trade in self.active_observations}) != len(
            self.active_observations
        ):
            raise PaperValidationError("active_observations must be unique")
        if (
            not isinstance(self.observed_through_ns, int)
            or isinstance(self.observed_through_ns, bool)
            or self.observed_through_ns < 0
        ):
            raise PaperValidationError("observed_through_ns must be a non-negative integer")
        if not isinstance(self.status, PaperStatus):
            raise PaperValidationError("status must be a PaperStatus")
        if not isinstance(self.complete, bool):
            raise PaperValidationError("complete must be a bool")
        if self.status == PaperStatus.BLOCKED:
            if self.complete or self.active_observations:
                raise PaperValidationError(
                    "blocked checkpoints have no active observations and are incomplete"
                )
        elif self.status == PaperStatus.ACTIVE:
            if self.complete:
                raise PaperValidationError("active checkpoints cannot be complete")
        elif not self.complete or self.active_observations:
            raise PaperValidationError("complete checkpoints must be drained and complete")
        if self.execution is not False:
            raise PaperValidationError("paper observations never execute orders")
        if self.orders_placed != 0:
            raise PaperValidationError("paper observations place zero orders")
        if self.schema_version != _PAPER_SCHEMA_VERSION:
            raise PaperValidationError("unsupported paper checkpoint schema_version")
        object.__setattr__(
            self, "active_state_digest", _active_state_digest(self.active_observations)
        )
        object.__setattr__(self, "checkpoint_id", sha256(self._content_bytes()).hexdigest())

    def _content_dict(self) -> dict[str, object]:
        return {
            "accepted_batches": [batch_projection(batch) for batch in self.accepted_batches],
            "active_observation_ids": [trade.trade_id for trade in self.active_observations],
            "active_observations": [trade.canonical_dict() for trade in self.active_observations],
            "active_state_digest": self.active_state_digest,
            "complete": self.complete,
            "execution": False,
            "horizon": self.horizon.canonical_dict(),
            "observed_through_ns": self.observed_through_ns,
            "orders_placed": 0,
            "policy_id": self.policy_id,
            "release_sha256": self.release_sha256,
            "schema_version": self.schema_version,
            "signing_key_fingerprint": self.signing_key_fingerprint,
            "status": self.status.value,
        }

    def _content_bytes(self) -> bytes:
        return canonical_json_bytes(self._content_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "checkpoint_id": self.checkpoint_id}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class PaperObservation:
    """One deterministic incremental paper result and its restart checkpoint."""

    result: BacktestResult
    checkpoint: PaperCheckpoint

    def __post_init__(self) -> None:
        if not isinstance(self.result, BacktestResult):
            raise PaperValidationError("result must be a BacktestResult")
        if not isinstance(self.checkpoint, PaperCheckpoint):
            raise PaperValidationError("checkpoint must be a PaperCheckpoint")
        if self.result.evidence_class is not EvidenceClass.PAPER_FORWARD:
            raise PaperValidationError("paper results must be paper_forward")
        if self.result.execution is not False or self.result.orders_placed != 0:
            raise PaperValidationError("paper results never execute orders")
        if self.result.status is BacktestStatus.BLOCKED:
            if self.checkpoint.status != PaperStatus.BLOCKED:
                raise PaperValidationError("blocked result requires a blocked checkpoint")
        elif self.checkpoint.status == PaperStatus.BLOCKED:
            raise PaperValidationError("ready result cannot have a blocked checkpoint")


def observe_paper(
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    batches: Iterable[FinalizedSeriesBatch],
    policy: SimulationPolicy,
    horizon: HalfOpenInterval,
    *,
    checkpoint: PaperCheckpoint | None = None,
) -> PaperObservation:
    """Observe canonical committed batches without changing live signal behavior.

    A resume always replays checkpoint evidence plus the strictly canonical new
    suffix through the same public-release runner.  Exact replayed inputs are
    idempotent; a novel batch after operational completion is rejected.
    """
    if not isinstance(policy, SimulationPolicy):
        raise PaperValidationError("policy must be a SimulationPolicy")
    if not isinstance(horizon, HalfOpenInterval):
        raise PaperValidationError("horizon must be a HalfOpenInterval")
    release_sha256 = _require_sha256_or_none(expected_sha256, "expected_sha256")
    key_fingerprint = _key_fingerprint(public_key)
    try:
        new_batches = normalize_batches(batches)
    except ValueError as exc:
        raise PaperValidationError("batches must be canonical committed evidence") from exc

    prior_batches: tuple[FinalizedSeriesBatch, ...] = ()
    prior_watermark = 0
    if checkpoint is not None:
        _validate_resume_identity(checkpoint, release_sha256, key_fingerprint, policy, horizon)
        _validate_checkpoint_replay(
            checkpoint,
            release_path,
            expected_sha256,
            public_key,
            policy,
        )
        prior_batches = checkpoint.accepted_batches
        prior_watermark = checkpoint.observed_through_ns

    known_ids = {batch_identity(batch) for batch in prior_batches}
    novel_batches = tuple(batch for batch in new_batches if batch_identity(batch) not in known_ids)
    if checkpoint is not None and checkpoint.complete and novel_batches:
        raise PaperValidationError("a complete paper horizon accepts no novel batches")
    try:
        accepted_batches = normalize_batches((*prior_batches, *novel_batches))
    except ValueError as exc:
        raise PaperValidationError("new batches conflict with checkpoint evidence") from exc
    if len(accepted_batches) > policy.max_accepted_batches:
        raise PaperValidationError("max_accepted_batches bound exceeded")

    observed_through_ns = max(
        (prior_watermark, *(batch.finalized_through_ns for batch in novel_batches)), default=0
    )
    horizon_reached = observed_through_ns >= horizon.end_ns
    _validate_checkpoint_byte_bound(
        PaperCheckpoint(
            release_sha256=release_sha256,
            signing_key_fingerprint=key_fingerprint,
            policy_id=policy.policy_id,
            horizon=horizon,
            accepted_batches=accepted_batches,
            active_observations=(),
            observed_through_ns=observed_through_ns,
            status=PaperStatus.ACTIVE,
            complete=False,
        ),
        policy,
    )
    result = _run_release_replay(
        release_path,
        expected_sha256,
        public_key,
        accepted_batches,
        policy,
        evidence_class=EvidenceClass.PAPER_FORWARD,
        terminal_reason=(ObservationReason.END_OF_DATA if horizon_reached else None),
        plan_context={
            "horizon": horizon.canonical_dict(),
            "paper_schema_version": _PAPER_SCHEMA_VERSION,
        },
        signal_interval=(horizon.start_ns, horizon.end_ns),
        observation_end_ns=horizon.end_ns,
    )
    active = tuple(
        sorted(
            (
                trade
                for trade in result.trades
                if trade.state in {ObservationState.PENDING, ObservationState.OPEN}
            ),
            key=lambda trade: trade.trade_id,
        )
    )
    if result.status is BacktestStatus.BLOCKED:
        status = PaperStatus.BLOCKED
        complete = False
    elif horizon_reached and not active:
        status = PaperStatus.COMPLETE
        complete = True
    else:
        status = PaperStatus.ACTIVE
        complete = False
    next_checkpoint = PaperCheckpoint(
        release_sha256=release_sha256,
        signing_key_fingerprint=key_fingerprint,
        policy_id=policy.policy_id,
        horizon=horizon,
        accepted_batches=accepted_batches,
        active_observations=active,
        observed_through_ns=observed_through_ns,
        status=status,
        complete=complete,
    )
    _validate_checkpoint_byte_bound(next_checkpoint, policy)
    return PaperObservation(result=result, checkpoint=next_checkpoint)


def _validate_resume_identity(
    checkpoint: PaperCheckpoint,
    release_sha256: str | None,
    key_fingerprint: str | None,
    policy: SimulationPolicy,
    horizon: HalfOpenInterval,
) -> None:
    if not isinstance(checkpoint, PaperCheckpoint):
        raise PaperValidationError("checkpoint must be a PaperCheckpoint")
    _validate_checkpoint_byte_bound(checkpoint, policy)
    if checkpoint.release_sha256 != release_sha256:
        raise PaperValidationError("checkpoint release identity does not match")
    if checkpoint.signing_key_fingerprint != key_fingerprint:
        raise PaperValidationError("checkpoint signing key identity does not match")
    if checkpoint.policy_id != policy.policy_id:
        raise PaperValidationError("checkpoint policy identity does not match")
    if checkpoint.horizon != horizon:
        raise PaperValidationError("checkpoint horizon does not match")


def _validate_checkpoint_byte_bound(checkpoint: PaperCheckpoint, policy: SimulationPolicy) -> None:
    if len(checkpoint.canonical_bytes()) > policy.max_artifact_bytes:
        raise PaperValidationError("checkpoint byte bound exceeded")


def _validate_checkpoint_replay(
    checkpoint: PaperCheckpoint,
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    policy: SimulationPolicy,
) -> None:
    """Reject a checkpoint whose recorded active state is not reproducible."""
    observed_through_ns = max(
        (batch.finalized_through_ns for batch in checkpoint.accepted_batches), default=0
    )
    horizon_reached = observed_through_ns >= checkpoint.horizon.end_ns
    result = _run_release_replay(
        release_path,
        expected_sha256,
        public_key,
        checkpoint.accepted_batches,
        policy,
        evidence_class=EvidenceClass.PAPER_FORWARD,
        terminal_reason=(ObservationReason.END_OF_DATA if horizon_reached else None),
        plan_context={
            "horizon": checkpoint.horizon.canonical_dict(),
            "paper_schema_version": _PAPER_SCHEMA_VERSION,
        },
        signal_interval=(checkpoint.horizon.start_ns, checkpoint.horizon.end_ns),
        observation_end_ns=checkpoint.horizon.end_ns,
    )
    active = tuple(
        sorted(
            (
                trade
                for trade in result.trades
                if trade.state in {ObservationState.PENDING, ObservationState.OPEN}
            ),
            key=lambda trade: trade.trade_id,
        )
    )
    if result.status is BacktestStatus.BLOCKED:
        status, complete = PaperStatus.BLOCKED, False
    elif horizon_reached and not active:
        status, complete = PaperStatus.COMPLETE, True
    else:
        status, complete = PaperStatus.ACTIVE, False
    if (
        checkpoint.observed_through_ns != observed_through_ns
        or checkpoint.status is not status
        or checkpoint.complete != complete
        or checkpoint.active_observations != active
        or checkpoint.active_state_digest != _active_state_digest(active)
    ):
        raise PaperValidationError("checkpoint state does not reconcile to its accepted evidence")
