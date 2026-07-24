"""Public composition of signed-release programs, causal alignment, and evaluation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.signal_engine.alignment import (
    AlignmentFailure,
    CausalAligner,
    CausalSnapshot,
    FinalizedSeriesBatch,
)
from stoic_derived.signal_engine.compiler import (
    CompilationReadiness,
    CompiledProfile,
    StrategyProgram,
    compile_production_release,
)
from stoic_derived.signal_engine.evaluator import (
    ENGINE_VERSION,
    SIGNAL_SOURCE,
    ProfileEvaluation,
    evaluate_profile_for_program,
)
from stoic_derived.signal_engine.model import (
    MarketLineage,
    Role,
    SignalBatch,
    SignalRecord,
    SignalType,
    SignalValidationError,
    Suppression,
    SuppressionCode,
    TimeframePlan,
)

_ENGINE_CONSTRUCTION = object()
_APPROVED_REARM_POLICY = "once_per_execute_bar"
_MAX_ACTIVE_LINEAGES = 4


@dataclass(frozen=True, slots=True)
class EngineCreation:
    """The only public release-to-engine boundary, including blocked readiness."""

    engine: SignalEngine | None
    program: StrategyProgram | None
    readiness: CompilationReadiness

    def __post_init__(self) -> None:
        if (self.engine is None) != (self.program is None):
            raise ValueError("engine and program must either both be present or both be absent")
        if self.program is None and self.readiness.ready:
            raise ValueError("ready engine creation requires a program")
        if self.program is not None and not self.readiness.ready:
            raise ValueError("blocked engine creation cannot contain a program")


class SignalEngine:
    """Stateful replay-safe composition over finalized lineage-scoped batches."""

    def __init__(self, _program: StrategyProgram, *, _construction: object) -> None:
        if _construction is not _ENGINE_CONSTRUCTION:
            raise TypeError("SignalEngine must be created with from_release")
        self._program = _program
        grouped: dict[SignalType, list[CompiledProfile]] = defaultdict(list)
        for profile in _program.profiles:
            grouped[SignalType(profile.trade_type)].append(profile)
        self._profiles = {
            signal_type: tuple(
                sorted(
                    profiles,
                    key=lambda profile: (
                        profile.setup_type,
                        profile.direction,
                        profile.rule_id,
                    ),
                )
            )
            for signal_type, profiles in grouped.items()
        }
        self._aligners: dict[MarketLineage, dict[SignalType, CausalAligner]] = {}

    @property
    def program(self) -> StrategyProgram:
        """Return the immutable program selected by the signed release boundary."""
        return self._program

    @property
    def active_lineages(self) -> tuple[MarketLineage, ...]:
        """Return active physical lineages in deterministic order."""
        return tuple(sorted(self._aligners, key=lambda lineage: lineage.identity))

    def retire_lineage(self, lineage: MarketLineage) -> bool:
        """Discard one fully drained physical lineage at an explicit roll boundary."""
        if not isinstance(lineage, MarketLineage):
            raise TypeError("lineage must be a MarketLineage")
        return self._aligners.pop(lineage, None) is not None

    @classmethod
    def from_release(
        cls,
        release_path: Path | str | None,
        expected_sha256: str | None,
        public_key: Ed25519PublicKey | bytes | None = None,
    ) -> EngineCreation:
        """Create an engine only from a pinned, signed, semantically-ready release."""
        compilation = compile_production_release(release_path, expected_sha256, public_key)
        if compilation.program is None:
            return EngineCreation(None, None, compilation.readiness)
        engine = cls(compilation.program, _construction=_ENGINE_CONSTRUCTION)
        return EngineCreation(engine, compilation.program, compilation.readiness)

    @classmethod
    def _from_program_for_test(cls, program: StrategyProgram) -> SignalEngine:
        """Private test seam for mechanical evaluator coverage, never a live boundary."""
        return cls(program, _construction=_ENGINE_CONSTRUCTION)

    def ingest(self, batch: FinalizedSeriesBatch) -> SignalBatch:
        """Atomically align and evaluate one committed lineage-scoped batch."""
        aligners = self._aligners_for(batch.lineage)
        candidates: list[ProfileEvaluation] = []
        failures: list[Suppression] = []

        # Each aligner emits an execute-bar identity at most once while it is
        # retained. Older input is rejected by the monotonic watermark, so no
        # unbounded engine-level replay set is needed.
        for signal_type in sorted(aligners, key=lambda item: item.value):
            for outcome in aligners[signal_type].ingest(batch):
                if outcome.failure is not None:
                    failures.append(self._suppression_from_alignment(outcome.failure))
                    continue
                assert outcome.snapshot is not None
                snapshot = outcome.snapshot
                for profile in self._profiles[signal_type]:
                    candidates.append(self._evaluate_snapshot(profile, snapshot))

        signals: list[SignalRecord] = []
        suppressions = list(failures)
        for result in candidates:
            if result.signal is not None:
                signals.append(result.signal)
            else:
                assert result.suppression is not None
                suppressions.append(result.suppression)
        return SignalBatch(
            batch.lineage,
            batch.finalized_through_ns,
            tuple(sorted(signals, key=lambda signal: signal.signal_id)),
            tuple(sorted(suppressions, key=lambda suppression: suppression.identity)),
        )

    submit = ingest

    def _aligners_for(self, lineage: MarketLineage) -> Mapping[SignalType, CausalAligner]:
        existing = self._aligners.get(lineage)
        if existing is not None:
            return existing
        if len(self._aligners) >= _MAX_ACTIVE_LINEAGES:
            raise SignalValidationError(
                "active lineage bound reached; retire a fully drained lineage before continuing"
            )
        role_offsets = dict(self._program.lookback_by_role)
        lookback = {Role(role): role_offsets[role] + 1 for role in ("htf", "setup", "execute")}
        lookback[Role.MANAGE] = 1
        history_limit = max(lookback.values())
        created = {
            signal_type: CausalAligner(
                self._plan_for(signal_type),
                lineage=lineage,
                lookback_bars=lookback,
                history_limit=history_limit,
            )
            for signal_type in self._profiles
        }
        self._aligners[lineage] = created
        return created

    def _plan_for(self, signal_type: SignalType) -> TimeframePlan:
        from stoic_derived.signal_engine.model import TIMEFRAME_PLANS

        return TIMEFRAME_PLANS[signal_type]

    def _evaluate_snapshot(
        self, profile: CompiledProfile, snapshot: CausalSnapshot
    ) -> ProfileEvaluation:
        if profile.rearm_policy != _APPROVED_REARM_POLICY:
            return ProfileEvaluation(
                suppression=Suppression(
                    code=SuppressionCode.SEMANTIC_UNSUPPORTED,
                    detail=f"unsupported signed rearm policy: {profile.rearm_policy}",
                    source=SIGNAL_SOURCE,
                    release_file_sha256=self._program.release_sha256,
                    rulebook_version=self._program.rulebook_version,
                    engine_version=ENGINE_VERSION,
                    signal_type=SignalType(profile.trade_type),
                    signal_ts_ns=snapshot.execute_bar.end_ns,
                    lineage=snapshot.lineage,
                    rule_id=profile.rule_id,
                    references=snapshot.causal_bar_ids,
                )
            )
        binding = profile.market_data_binding
        lineage = snapshot.lineage
        if (
            binding.source != lineage.source
            or binding.schema_version != lineage.market_data_schema
            or binding.calendar_fingerprint != lineage.calendar_fingerprint
            or binding.aggregation_fingerprint != lineage.aggregation_fingerprint
            or binding.tick_nanos != snapshot.execute_bar.instrument.tick_nanos
        ):
            return ProfileEvaluation(
                suppression=Suppression(
                    code=SuppressionCode.LINEAGE_MISMATCH,
                    detail="snapshot does not match the signed market-data binding",
                    source=SIGNAL_SOURCE,
                    release_file_sha256=self._program.release_sha256,
                    rulebook_version=self._program.rulebook_version,
                    engine_version=ENGINE_VERSION,
                    signal_type=SignalType(profile.trade_type),
                    signal_ts_ns=snapshot.execute_bar.end_ns,
                    lineage=lineage,
                    rule_id=profile.rule_id,
                    references=snapshot.causal_bar_ids,
                )
            )
        return evaluate_profile_for_program(
            profile,
            release_file_sha256=self._program.release_sha256,
            rulebook_version=self._program.rulebook_version,
            history=snapshot.history,
            lineage=snapshot.lineage,
            execute_bar=snapshot.execute_bar,
            causal_bar_ids=snapshot.causal_bar_ids,
            source=SIGNAL_SOURCE,
            engine_version=ENGINE_VERSION,
        )

    def _suppression_from_alignment(self, failure: AlignmentFailure) -> Suppression:
        return Suppression(
            code=failure.code,
            detail=failure.detail,
            source=SIGNAL_SOURCE,
            release_file_sha256=self._program.release_sha256,
            rulebook_version=self._program.rulebook_version,
            engine_version=ENGINE_VERSION,
            signal_type=failure.signal_type,
            signal_ts_ns=failure.execute_bar.end_ns,
            lineage=failure.lineage,
            rule_id=None,
            references=failure.references,
        )


__all__ = ["EngineCreation", "SignalEngine"]
