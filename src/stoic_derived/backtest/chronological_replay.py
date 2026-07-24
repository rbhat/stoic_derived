"""Chronological, non-optimizing historical replay folds.

The folds are explicitly labelled retrospective replay.  They do not fit,
select, promote, or claim genuine out-of-sample performance.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.backtest.codec import normalize_batches
from stoic_derived.backtest.model import (
    BacktestResult,
    BacktestValidationError,
    ChronologicalReplayFold,
    ChronologicalReplayPlan,
    EvidenceClass,
    ObservationReason,
    SimulationPolicy,
)
from stoic_derived.backtest.runner import _run_release_replay
from stoic_derived.signal_engine import FinalizedSeriesBatch


def run_chronological_replay(
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    batches: Iterable[FinalizedSeriesBatch],
    policy: SimulationPolicy,
    replay_plan: ChronologicalReplayPlan,
) -> tuple[BacktestResult, ...]:
    """Run isolated fresh-engine historical folds without any optimization path."""
    if not isinstance(policy, SimulationPolicy):
        raise BacktestValidationError("policy must be a SimulationPolicy")
    if not isinstance(replay_plan, ChronologicalReplayPlan):
        raise BacktestValidationError("replay_plan must be a ChronologicalReplayPlan")
    accepted = normalize_batches(batches)
    if len(accepted) > policy.max_accepted_batches:
        raise BacktestValidationError("max_accepted_batches bound exceeded")

    return tuple(
        _run_fold(
            fold,
            replay_plan,
            release_path,
            expected_sha256,
            public_key,
            accepted,
            policy,
        )
        for fold in replay_plan.folds
    )


def _run_fold(
    fold: ChronologicalReplayFold,
    replay_plan: ChronologicalReplayPlan,
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    batches: tuple[FinalizedSeriesBatch, ...],
    policy: SimulationPolicy,
) -> BacktestResult:
    fold_batches = _batches_for_fold(batches, fold)
    return _run_release_replay(
        release_path,
        expected_sha256,
        public_key,
        fold_batches,
        policy,
        evidence_class=EvidenceClass.RETROSPECTIVE_REPLAY,
        terminal_reason=ObservationReason.FOLD_END,
        plan_context={"chronological_plan_id": replay_plan.plan_id, "fold": fold.canonical_dict()},
        signal_interval=(fold.evaluation.start_ns, fold.evaluation.end_ns),
        observation_end_ns=fold.evaluation.end_ns,
    )


def _batches_for_fold(
    batches: tuple[FinalizedSeriesBatch, ...], fold: ChronologicalReplayFold
) -> tuple[FinalizedSeriesBatch, ...]:
    """Keep exact bars/gaps inside one fold's [warmup, evaluation) horizon.

    A source transaction can contain multiple horizons.  The derived transaction
    retains each selected immutable record unchanged and only narrows the
    committed watermark to its selected evidence; no bar or lineage is altered.
    """
    lower = fold.warmup.start_ns
    upper = fold.evaluation.end_ns
    selected: list[FinalizedSeriesBatch] = []
    for batch in batches:
        bars = tuple(bar for bar in batch.bars if lower <= bar.end_ns < upper)
        gaps = tuple(gap for gap in batch.gaps if gap.start_ns < upper and lower < gap.end_ns)
        if not bars and not gaps:
            continue
        watermark = max([min(batch.finalized_through_ns, upper)] + [gap.end_ns for gap in gaps])
        selected.append(FinalizedSeriesBatch(batch.lineage, watermark, bars, gaps))
    return normalize_batches(selected)
