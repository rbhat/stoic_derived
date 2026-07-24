"""Release-bound, causal observational replay over the public SP2 engine.

This module measures immutable historical evidence.  It cannot construct a
strategy program, alter a signal, or affect a live engine.  Simulated fills
remain research observations and never represent broker activity.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.backtest.codec import (
    BATCH_CODEC_SCHEMA_VERSION,
    batch_identity,
    normalize_batches,
)
from stoic_derived.backtest.metrics import build_equity, build_exclusions, build_metrics
from stoic_derived.backtest.model import (
    ARTIFACT_ALGORITHM_VERSION,
    METRICS_ALGORITHM_VERSION,
    SIMULATOR_ALGORITHM_VERSION,
    BacktestResult,
    BacktestStatus,
    BacktestValidationError,
    EvidenceClass,
    ObservationReason,
    SimulationPolicy,
    canonical_json_bytes,
)
from stoic_derived.backtest.simulator import _OutcomeTracker
from stoic_derived.market_data.model import FinalBar, Timeframe
from stoic_derived.signal_engine import FinalizedSeriesBatch, MarketLineage, SignalEngine


def production_readiness() -> BacktestResult:
    """Report current release-bound SP3 readiness without loading draft strategy material."""
    policy = SimulationPolicy(
        entry_slippage_ticks=1,
        exit_slippage_ticks=1,
        fees_ticks_round_turn=1,
        zero_costs_declared=False,
        max_active_observations=1,
        max_active_lineages=1,
        max_retained_gaps=1,
        max_accepted_batches=1,
        max_output_records=1,
        max_artifact_bytes=1,
    )
    return run_replay(None, None, None, (), policy)


def run_replay(
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    batches: Iterable[FinalizedSeriesBatch],
    policy: SimulationPolicy,
) -> BacktestResult:
    """Replay committed batches through a pinned release as retrospective evidence.

    This public entry point always uses the public signed-release boundary.  A
    release that is not ready is an ordinary successful result with a zero
    population; it is not replaced with local strategy material.
    """
    return _run_release_replay(
        release_path,
        expected_sha256,
        public_key,
        batches,
        policy,
        evidence_class=EvidenceClass.RETROSPECTIVE_REPLAY,
    )


def _run_release_replay(
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    batches: Iterable[FinalizedSeriesBatch],
    policy: SimulationPolicy,
    *,
    evidence_class: EvidenceClass,
    terminal_reason: ObservationReason | None = ObservationReason.END_OF_DATA,
    plan_context: Mapping[str, object] | None = None,
    signal_interval: tuple[int, int] | None = None,
    observation_end_ns: int | None = None,
    admit_signal: Callable[[int], bool] | None = None,
) -> BacktestResult:
    """Private shared release-based composition for paper and fold consumers.

    ``admit_signal`` is deliberately private plumbing for chronological folds;
    public callers cannot inject records or modify the engine's decisions.
    """
    if not isinstance(policy, SimulationPolicy):
        raise BacktestValidationError("policy must be a SimulationPolicy")
    if not isinstance(evidence_class, EvidenceClass):
        raise BacktestValidationError("evidence_class must be an EvidenceClass")
    if terminal_reason not in {
        None,
        ObservationReason.END_OF_DATA,
        ObservationReason.FOLD_END,
    }:
        raise BacktestValidationError("terminal_reason must be end_of_data, fold_end, or None")
    if plan_context is not None and not isinstance(plan_context, Mapping):
        raise BacktestValidationError("plan_context must be a mapping or None")
    if admit_signal is not None and not callable(admit_signal):
        raise BacktestValidationError("admit_signal must be callable or None")
    _validate_signal_interval(signal_interval)
    if not isinstance(observation_end_ns, (int, type(None))) or isinstance(
        observation_end_ns, bool
    ):
        raise BacktestValidationError("observation_end_ns must be an integer or None")
    if observation_end_ns is not None and observation_end_ns < 0:
        raise BacktestValidationError("observation_end_ns must be non-negative")

    accepted = _cap_observation_horizon(normalize_batches(batches), observation_end_ns)
    if len(accepted) > policy.max_accepted_batches:
        raise BacktestValidationError("max_accepted_batches bound exceeded")
    plan_id = _plan_id(
        expected_sha256=expected_sha256,
        public_key=public_key,
        policy=policy,
        batches=accepted,
        evidence_class=evidence_class,
        plan_context={
            "caller": _canonical_context(plan_context),
            "observation_end_ns": observation_end_ns,
            "signal_interval": list(signal_interval) if signal_interval is not None else None,
            "terminal_reason": terminal_reason.value if terminal_reason is not None else None,
        },
    )

    # This is intentionally the only production creation boundary in SP3.
    creation = SignalEngine.from_release(release_path, expected_sha256, public_key)
    if creation.engine is None:
        blockers = tuple(
            sorted(
                f"{blocker.code.value}: {blocker.message}"
                for blocker in creation.readiness.blockers
            )
        )
        if not blockers:
            raise BacktestValidationError("blocked release must provide readiness blockers")
        return BacktestResult.blocked(
            evidence_class=evidence_class,
            plan_id=plan_id,
            readiness_blockers=blockers,
        )

    return _run_with_engine(
        engine=creation.engine,
        batches=accepted,
        policy=policy,
        plan_id=plan_id,
        evidence_class=evidence_class,
        terminal_reason=terminal_reason,
        admit_signal=_admission_predicate(signal_interval, admit_signal),
    )


def _run_with_engine(
    *,
    engine: SignalEngine,
    batches: Iterable[FinalizedSeriesBatch],
    policy: SimulationPolicy,
    plan_id: str,
    evidence_class: EvidenceClass = EvidenceClass.RETROSPECTIVE_REPLAY,
    terminal_reason: ObservationReason | None = ObservationReason.END_OF_DATA,
    admit_signal: Callable[[int], bool] | None = None,
) -> BacktestResult:
    """Private mechanics seam for tests and fresh-engine chronological folds only."""
    if not isinstance(engine, SignalEngine):
        raise BacktestValidationError("engine must be a SignalEngine")
    if not isinstance(policy, SimulationPolicy):
        raise BacktestValidationError("policy must be a SimulationPolicy")
    if not isinstance(evidence_class, EvidenceClass):
        raise BacktestValidationError("evidence_class must be an EvidenceClass")
    if terminal_reason not in {
        None,
        ObservationReason.END_OF_DATA,
        ObservationReason.FOLD_END,
    }:
        raise BacktestValidationError("terminal_reason must be end_of_data, fold_end, or None")
    if admit_signal is not None and not callable(admit_signal):
        raise BacktestValidationError("admit_signal must be callable or None")

    accepted = normalize_batches(batches)
    if len(accepted) > policy.max_accepted_batches:
        raise BacktestValidationError("max_accepted_batches bound exceeded")

    tracker = _OutcomeTracker(policy)
    observed_signals: dict[str, Any] = {}
    observed_suppressions: dict[str, Any] = {}
    active_lineage_by_root: dict[str, MarketLineage] = {}
    retired_lineages: set[str] = set()

    for batch in accepted:
        _retire_prior_root_lineage(
            batch.lineage,
            active_lineage_by_root,
            retired_lineages,
            tracker,
            engine,
        )

        # Ingest before registering decisions or observing future one-minute
        # evidence.  SignalBatch remains untouched; stored records are the
        # exact immutable values emitted by SP2.
        outcome = engine.ingest(batch)
        for signal in outcome.signals:
            if admit_signal is not None and not admit_signal(signal.signal_ts_ns):
                continue
            existing = observed_signals.get(signal.signal_id)
            if existing is not None and existing != signal:
                raise BacktestValidationError("conflicting emitted signal identity")
            if existing is None:
                observed_signals[signal.signal_id] = signal
                tracker.register(signal)
        for suppression in outcome.suppressions:
            if (
                admit_signal is not None
                and suppression.signal_ts_ns is not None
                and not admit_signal(suppression.signal_ts_ns)
            ):
                continue
            existing = observed_suppressions.get(suppression.identity)
            if existing is not None and existing != suppression:
                raise BacktestValidationError("conflicting emitted suppression identity")
            observed_suppressions[suppression.identity] = suppression

        # Gaps are known before any eligible complete one-minute observation in
        # this committed batch.  Equal-time decisions above were registered in
        # signal-id order by the public SignalBatch contract.
        for gap in batch.gaps:
            tracker.observe_gap(gap)
        for bar in _one_minute_observation_order(batch.bars):
            tracker.observe_bar(bar, gaps=batch.gaps)
        tracker.observe_watermark(batch.lineage, batch.finalized_through_ns)
        _ensure_partial_output_bound(observed_signals, observed_suppressions, tracker, policy)

    if terminal_reason is not None:
        tracker.finish(terminal_reason)
    signals = tuple(sorted(observed_signals.values(), key=lambda signal: signal.signal_id))
    suppressions = tuple(
        sorted(observed_suppressions.values(), key=lambda suppression: suppression.identity)
    )
    trades = tuple(sorted(tracker.trade_records, key=lambda trade: trade.trade_id))
    fills = tuple(
        sorted((fill for trade in trades for fill in trade.fills), key=lambda fill: fill.fill_id)
    )
    warnings = tracker.warnings
    equity = build_equity(trades)
    metrics = build_metrics(trades)
    exclusions = build_exclusions(suppressions)
    _ensure_final_output_bound(
        signals, suppressions, fills, trades, warnings, equity, metrics, exclusions, policy
    )
    return BacktestResult(
        evidence_class=evidence_class,
        status=BacktestStatus.COMPLETE,
        plan_id=plan_id,
        signals=signals,
        suppressions=suppressions,
        fills=fills,
        trades=trades,
        equity=equity,
        metrics=metrics,
        exclusions=exclusions,
        warnings=warnings,
    )


def _retire_prior_root_lineage(
    lineage: MarketLineage,
    active_lineage_by_root: dict[str, MarketLineage],
    retired_lineages: set[str],
    tracker: _OutcomeTracker,
    engine: SignalEngine,
) -> None:
    if lineage.identity in retired_lineages:
        raise BacktestValidationError("retired physical lineage reappeared")
    prior = active_lineage_by_root.get(lineage.root)
    if prior is None:
        active_lineage_by_root[lineage.root] = lineage
        return
    if prior == lineage:
        return
    # The tracker resolves pending/open observations before the public engine
    # drops its alignment state, preventing any fill from crossing a roll.
    tracker.retire_lineage(prior)
    engine.retire_lineage(prior)
    retired_lineages.add(prior.identity)
    active_lineage_by_root[lineage.root] = lineage


def _one_minute_observation_order(bars: tuple[FinalBar, ...]) -> tuple[FinalBar, ...]:
    return tuple(
        sorted(
            (bar for bar in bars if bar.timeframe is Timeframe.ONE_MINUTE),
            key=lambda bar: (bar.end_ns, bar.identity),
        )
    )


def _plan_id(
    *,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None,
    policy: SimulationPolicy,
    batches: tuple[FinalizedSeriesBatch, ...],
    evidence_class: EvidenceClass,
    plan_context: Mapping[str, object] | None,
) -> str:
    context = _canonical_context(plan_context)
    payload = {
        "artifact_algorithm_version": ARTIFACT_ALGORITHM_VERSION,
        "batch_codec_schema_version": BATCH_CODEC_SCHEMA_VERSION,
        "batch_ids": [batch_identity(batch) for batch in batches],
        "evidence_class": evidence_class.value,
        "metrics_algorithm_version": METRICS_ALGORITHM_VERSION,
        "plan_context": context,
        "release_sha256": expected_sha256,
        "signing_key_fingerprint": _key_fingerprint(public_key),
        "simulator_algorithm_version": SIMULATOR_ALGORITHM_VERSION,
        "policy_id": policy.policy_id,
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def _key_fingerprint(public_key: Ed25519PublicKey | bytes | None) -> str | None:
    if public_key is None:
        return None
    if isinstance(public_key, bytes):
        return sha256(public_key).hexdigest()
    if isinstance(public_key, Ed25519PublicKey):
        raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return sha256(raw).hexdigest()
    raise BacktestValidationError("public_key must be Ed25519PublicKey, bytes, or None")


def _canonical_context(context: Mapping[str, object] | None) -> dict[str, object] | None:
    if context is None:
        return None
    try:
        encoded = canonical_json_bytes(dict(context))
    except (TypeError, ValueError) as exc:
        raise BacktestValidationError("plan_context must be canonical JSON data") from exc
    # Round-trip ensures no caller-owned mapping or host object enters the plan.
    import json

    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - dict(context) guarantees this
        raise BacktestValidationError("plan_context must encode to an object")
    return decoded


def _validate_signal_interval(interval: tuple[int, int] | None) -> None:
    if interval is None:
        return
    if (
        not isinstance(interval, tuple)
        or len(interval) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in interval)
        or interval[0] < 0
        or interval[0] >= interval[1]
    ):
        raise BacktestValidationError(
            "signal_interval must be a non-empty half-open integer interval"
        )


def _admission_predicate(
    interval: tuple[int, int] | None, predicate: Callable[[int], bool] | None
) -> Callable[[int], bool] | None:
    if interval is None:
        return predicate

    def admit(timestamp: int) -> bool:
        return interval[0] <= timestamp < interval[1] and (
            predicate(timestamp) if predicate is not None else True
        )

    return admit


def _cap_observation_horizon(
    batches: tuple[FinalizedSeriesBatch, ...], end_ns: int | None
) -> tuple[FinalizedSeriesBatch, ...]:
    if end_ns is None:
        return batches
    capped: list[FinalizedSeriesBatch] = []
    for batch in batches:
        bars = tuple(bar for bar in batch.bars if bar.end_ns < end_ns)
        # A gap touching the horizon is evidence that the horizon is not fully
        # observable.  Keep its immutable full interval rather than silently
        # dropping it merely because its end lies beyond the boundary.
        gaps = tuple(gap for gap in batch.gaps if gap.start_ns < end_ns)
        if not bars and not gaps:
            continue
        # SP2 admits a completed execute bar only when it is strictly before
        # the committed watermark.  Preserve the source watermark (capped at
        # the exclusive observation horizon) instead of collapsing it to the
        # final selected bar end.  A retained overlapping gap may require a
        # later watermark so its unchanged interval remains valid.
        watermark = max([min(batch.finalized_through_ns, end_ns)] + [gap.end_ns for gap in gaps])
        capped.append(FinalizedSeriesBatch(batch.lineage, watermark, bars, gaps))
    return normalize_batches(capped)


def _ensure_partial_output_bound(
    signals: Mapping[str, object],
    suppressions: Mapping[str, object],
    tracker: _OutcomeTracker,
    policy: SimulationPolicy,
) -> None:
    count = len(signals) + len(suppressions)
    count += len(tracker.trade_records) + sum(len(trade.fills) for trade in tracker.trade_records)
    count += len(tracker.warnings)
    if count > policy.max_output_records:
        raise BacktestValidationError("max_output_records bound exceeded")


def _ensure_final_output_bound(
    signals: tuple[Any, ...],
    suppressions: tuple[Any, ...],
    fills: tuple[Any, ...],
    trades: tuple[Any, ...],
    warnings: tuple[Any, ...],
    equity: tuple[Any, ...],
    metrics: tuple[Any, ...],
    exclusions: tuple[Any, ...],
    policy: SimulationPolicy,
) -> None:
    if (
        len(signals)
        + len(suppressions)
        + len(fills)
        + len(trades)
        + len(warnings)
        + len(equity)
        + len(metrics)
        + len(exclusions)
        > policy.max_output_records
    ):
        raise BacktestValidationError("max_output_records bound exceeded")
