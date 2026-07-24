"""Committed, causal multi-timeframe bar alignment for SP2.

This module deliberately stops before predicate or signal evaluation.  It turns
one committed physical market lineage into complete, role-bound snapshots, or
an explicit reason that such a snapshot cannot safely be constructed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType

from stoic_derived.market_data.model import FinalBar, QualityState, Timeframe

from .model import (
    CoverageGap,
    MarketLineage,
    Role,
    SignalType,
    SignalValidationError,
    SuppressionCode,
    TimeframePlan,
)


def _require_nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SignalValidationError(f"{name} must be a non-negative integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SignalValidationError(f"{name} must be a positive integer")
    return value


def _bar_interval_key(bar: FinalBar) -> tuple[Timeframe, int, int]:
    return (bar.timeframe, bar.start_ns, bar.end_ns)


def _bar_sort_key(bar: FinalBar) -> tuple[int, int, str]:
    return (bar.end_ns, bar.start_ns, bar.identity)


def _gap_sort_key(gap: CoverageGap) -> tuple[str, int, int, str]:
    return (gap.timeframe.value, gap.start_ns, gap.end_ns, gap.identity)


def _overlaps(start_ns: int, end_ns: int, gap: CoverageGap) -> bool:
    """Return whether a gap overlaps a half-open required history window."""
    return gap.start_ns < end_ns and start_ns < gap.end_ns


def _intervals_overlap(left: FinalBar, right: FinalBar) -> bool:
    return left.start_ns < right.end_ns and right.start_ns < left.end_ns


@dataclass(frozen=True, slots=True)
class FinalizedSeriesBatch:
    """An immutable, lineage-scoped transaction of finalized bars and gaps."""

    lineage: MarketLineage
    finalized_through_ns: int
    bars: tuple[FinalBar, ...] = ()
    gaps: tuple[CoverageGap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        _require_nonnegative_int(self.finalized_through_ns, "finalized_through_ns")
        if any(not isinstance(bar, FinalBar) for bar in self.bars):
            raise SignalValidationError("bars must contain FinalBar values")
        if any(MarketLineage.from_final_bar(bar) != self.lineage for bar in self.bars):
            raise SignalValidationError("bars must share the batch lineage")
        if any(bar.end_ns > self.finalized_through_ns for bar in self.bars):
            raise SignalValidationError("bars must end no later than finalized_through_ns")
        if any(not isinstance(gap, CoverageGap) for gap in self.gaps):
            raise SignalValidationError("gaps must contain CoverageGap values")
        if any(gap.lineage != self.lineage for gap in self.gaps):
            raise SignalValidationError("gaps must share the batch lineage")
        if any(gap.end_ns > self.finalized_through_ns for gap in self.gaps):
            raise SignalValidationError("gaps must end no later than finalized_through_ns")

        by_interval: dict[tuple[Timeframe, int, int], FinalBar] = {}
        for bar in self.bars:
            key = _bar_interval_key(bar)
            existing = by_interval.get(key)
            if existing is not None and existing.identity != bar.identity:
                raise SignalValidationError("conflicting bars share a timeframe interval")
            by_interval[key] = bar
        canonical_bars = tuple(sorted(by_interval.values(), key=_bar_sort_key))
        by_timeframe: dict[Timeframe, list[FinalBar]] = defaultdict(list)
        for bar in canonical_bars:
            by_timeframe[bar.timeframe].append(bar)
        for bars in by_timeframe.values():
            by_start = sorted(bars, key=lambda bar: (bar.start_ns, bar.end_ns, bar.identity))
            if any(
                _intervals_overlap(previous, current) for previous, current in pairwise(by_start)
            ):
                raise SignalValidationError("bars in one timeframe cannot overlap")
        canonical_gaps = tuple(
            sorted({gap.identity: gap for gap in self.gaps}.values(), key=_gap_sort_key)
        )
        object.__setattr__(self, "bars", canonical_bars)
        object.__setattr__(self, "gaps", canonical_gaps)


@dataclass(frozen=True, slots=True)
class AlignmentFailure:
    """A typed, deterministic reason why an execute bar has no safe snapshot."""

    code: SuppressionCode
    detail: str
    signal_type: SignalType
    lineage: MarketLineage
    execute_bar: FinalBar
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in {
            SuppressionCode.MISSING_CONTEXT,
            SuppressionCode.INSUFFICIENT_LOOKBACK,
            SuppressionCode.DEGRADED_DATA,
            SuppressionCode.COVERAGE_GAP,
        }:
            raise SignalValidationError("alignment failure must use an alignment suppression code")
        if not isinstance(self.detail, str) or not self.detail:
            raise SignalValidationError("detail must be a non-empty string")
        if not isinstance(self.signal_type, SignalType):
            raise SignalValidationError("signal_type must be a SignalType")
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        if not isinstance(self.execute_bar, FinalBar):
            raise SignalValidationError("execute_bar must be a FinalBar")
        if MarketLineage.from_final_bar(self.execute_bar) != self.lineage:
            raise SignalValidationError("execute_bar must share the failure lineage")
        if (
            any(not isinstance(reference, str) or not reference for reference in self.references)
            or tuple(sorted(self.references)) != self.references
            or len(set(self.references)) != len(self.references)
        ):
            raise SignalValidationError("references must be sorted unique non-empty strings")


@dataclass(frozen=True, slots=True)
class CausalSnapshot:
    """One complete, bounded, role-bound snapshot for a closed execute bar."""

    plan: TimeframePlan
    lineage: MarketLineage
    execute_bar: FinalBar
    history: Mapping[Role, tuple[FinalBar, ...]]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, TimeframePlan):
            raise SignalValidationError("plan must be a TimeframePlan")
        if not isinstance(self.lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage")
        if not isinstance(self.execute_bar, FinalBar):
            raise SignalValidationError("execute_bar must be a FinalBar")
        if MarketLineage.from_final_bar(self.execute_bar) != self.lineage:
            raise SignalValidationError("execute_bar must share the snapshot lineage")
        if self.execute_bar.timeframe is not self.plan.execute:
            raise SignalValidationError("execute_bar must have the plan execute timeframe")
        normalized: dict[Role, tuple[FinalBar, ...]] = {}
        if set(self.history) != set(Role):
            raise SignalValidationError("history must contain exactly every Role")
        for role in Role:
            bars = self.history[role]
            if not isinstance(bars, tuple) or not bars:
                raise SignalValidationError("each role history must be a non-empty tuple")
            if any(not isinstance(bar, FinalBar) for bar in bars):
                raise SignalValidationError("history must contain FinalBar values")
            if any(MarketLineage.from_final_bar(bar) != self.lineage for bar in bars):
                raise SignalValidationError("history cannot cross a physical lineage")
            if any(bar.timeframe is not self.plan.for_role(role) for bar in bars):
                raise SignalValidationError("history timeframe does not match its role")
            if any(bar.end_ns > self.execute_bar.end_ns for bar in bars):
                raise SignalValidationError("history cannot contain future bars")
            if any(bar.quality is not QualityState.COMPLETE for bar in bars):
                raise SignalValidationError("history may contain complete bars only")
            if tuple(sorted(bars, key=_bar_sort_key)) != bars:
                raise SignalValidationError("history must be ordered by end, start, and identity")
            normalized[role] = bars
        object.__setattr__(self, "history", MappingProxyType(normalized))

    def bars_for(self, role: Role) -> tuple[FinalBar, ...]:
        """Return the bounded causal history selected for one explicit role."""
        if not isinstance(role, Role):
            raise SignalValidationError("role must be a Role")
        return self.history[role]

    @property
    def causal_bar_ids(self) -> tuple[str, ...]:
        """Return a stable deduplicated provenance list for downstream evaluation."""
        return tuple(sorted({bar.identity for bars in self.history.values() for bar in bars}))


AlignmentSnapshot = CausalSnapshot


@dataclass(frozen=True, slots=True)
class AlignmentOutcome:
    """Exactly one complete snapshot or typed alignment failure."""

    snapshot: CausalSnapshot | None = None
    failure: AlignmentFailure | None = None

    def __post_init__(self) -> None:
        if (self.snapshot is None) == (self.failure is None):
            raise SignalValidationError("alignment outcome must contain exactly one result")
        if self.snapshot is not None and not isinstance(self.snapshot, CausalSnapshot):
            raise SignalValidationError("snapshot must be a CausalSnapshot")
        if self.failure is not None and not isinstance(self.failure, AlignmentFailure):
            raise SignalValidationError("failure must be an AlignmentFailure")


class CausalAligner:
    """Stateful, bounded buffer that emits causal snapshots for one lineage.

    A committed batch is fully validated before any state changes. New data
    strictly behind an already-finalized watermark is rejected; data exactly
    at the watermark may arrive in another fragment before that timestamp is
    evaluated. Execute bars become eligible only after the watermark advances
    beyond their close, making all same-end fragments atomic.
    """

    def __init__(
        self,
        plan: TimeframePlan,
        *,
        lineage: MarketLineage | None = None,
        lookback_bars: int | Mapping[Role, int] = 1,
        history_limit: int = 512,
    ) -> None:
        if not isinstance(plan, TimeframePlan):
            raise SignalValidationError("plan must be a TimeframePlan")
        if lineage is not None and not isinstance(lineage, MarketLineage):
            raise SignalValidationError("lineage must be a MarketLineage or None")
        self._plan = plan
        self._lineage = lineage
        self._lookback = self._normalize_lookback(lookback_bars)
        self._history_limit = _require_positive_int(history_limit, "history_limit")
        if self._history_limit < max(self._lookback.values()):
            raise SignalValidationError("history_limit must cover the requested lookback")
        self._max_retained_gaps = max(64, self._history_limit * len(Timeframe) * 2)
        self._watermark: int | None = None
        self._bars: dict[Timeframe, list[FinalBar]] = defaultdict(list)
        self._bar_by_interval: dict[tuple[Timeframe, int, int], FinalBar] = {}
        self._gaps: dict[str, CoverageGap] = {}
        self._evaluated_execute_ids: set[str] = set()

    @property
    def plan(self) -> TimeframePlan:
        return self._plan

    @property
    def lineage(self) -> MarketLineage | None:
        return self._lineage

    @property
    def finalized_through_ns(self) -> int | None:
        return self._watermark

    @property
    def retained_gap_count(self) -> int:
        """Return the bounded gap-state size for operational verification."""
        return len(self._gaps)

    def _normalize_lookback(self, lookback_bars: int | Mapping[Role, int]) -> dict[Role, int]:
        if isinstance(lookback_bars, int) and not isinstance(lookback_bars, bool):
            count = _require_positive_int(lookback_bars, "lookback_bars")
            return {role: count for role in Role}
        if not isinstance(lookback_bars, Mapping) or set(lookback_bars) != set(Role):
            raise SignalValidationError("lookback_bars mapping must contain exactly every Role")
        return {
            role: _require_positive_int(lookback_bars[role], f"lookback_bars[{role.value}]")
            for role in Role
        }

    def ingest(self, batch: FinalizedSeriesBatch) -> tuple[AlignmentOutcome, ...]:
        """Atomically insert one committed batch and emit its new execute results."""
        if not isinstance(batch, FinalizedSeriesBatch):
            raise SignalValidationError("batch must be a FinalizedSeriesBatch")
        if self._lineage is not None and batch.lineage != self._lineage:
            raise SignalValidationError("batch lineage does not match this aligner")
        if self._watermark is not None and batch.finalized_through_ns < self._watermark:
            raise SignalValidationError("finalized_through_ns must be monotonic")

        new_bars = self._validate_new_bars(batch)
        new_gaps = self._validate_new_gaps(batch)
        if len(self._gaps) + len(new_gaps) > self._max_retained_gaps:
            raise SignalValidationError("retained coverage-gap bound exceeded")
        if self._watermark is not None and (
            any(bar.end_ns < self._watermark for bar in new_bars)
            or any(gap.start_ns < self._watermark for gap in new_gaps)
        ):
            raise SignalValidationError("new committed data cannot be behind watermark")

        if self._lineage is None:
            self._lineage = batch.lineage
        for bar in new_bars:
            self._bar_by_interval[_bar_interval_key(bar)] = bar
            self._bars[bar.timeframe].append(bar)
        for bars in self._bars.values():
            bars.sort(key=_bar_sort_key)
        for gap in new_gaps:
            self._gaps[gap.identity] = gap
        self._watermark = batch.finalized_through_ns

        eligible = tuple(
            bar
            for bar in self._bars[self._plan.execute]
            if bar.end_ns < batch.finalized_through_ns
            and bar.identity not in self._evaluated_execute_ids
        )
        outcomes = tuple(self._align_execute(bar) for bar in eligible)
        self._evaluated_execute_ids.update(bar.identity for bar in eligible)
        self._trim_history()
        return outcomes

    submit = ingest

    def _validate_new_bars(self, batch: FinalizedSeriesBatch) -> tuple[FinalBar, ...]:
        new_bars: list[FinalBar] = []
        for bar in batch.bars:
            existing = self._bar_by_interval.get(_bar_interval_key(bar))
            if existing is None:
                if any(
                    retained.timeframe is bar.timeframe and _intervals_overlap(retained, bar)
                    for retained in self._bars[bar.timeframe]
                ):
                    raise SignalValidationError("bar overlaps a retained timeframe interval")
                new_bars.append(bar)
            elif existing.identity != bar.identity:
                raise SignalValidationError("conflicting bar interval already exists")
        return tuple(new_bars)

    def _validate_new_gaps(self, batch: FinalizedSeriesBatch) -> tuple[CoverageGap, ...]:
        return tuple(gap for gap in batch.gaps if gap.identity not in self._gaps)

    def _align_execute(self, execute_bar: FinalBar) -> AlignmentOutcome:
        assert self._lineage is not None
        selected: dict[Role, tuple[FinalBar, ...]] = {}
        for role in Role:
            timeframe = self._plan.for_role(role)
            candidates = tuple(
                bar for bar in self._bars[timeframe] if bar.end_ns <= execute_bar.end_ns
            )
            if not candidates:
                return self._failure(
                    SuppressionCode.MISSING_CONTEXT,
                    f"missing {role.value} context at execute close",
                    execute_bar,
                )
            required = self._lookback[role]
            if len(candidates) < required:
                return self._failure(
                    SuppressionCode.INSUFFICIENT_LOOKBACK,
                    f"{role.value} history has fewer than {required} finalized bars",
                    execute_bar,
                    candidates,
                )
            history = candidates[-required:]
            degraded = tuple(bar for bar in history if bar.quality is not QualityState.COMPLETE)
            if degraded:
                return self._failure(
                    SuppressionCode.DEGRADED_DATA,
                    f"{role.value} history contains degraded finalized bars",
                    execute_bar,
                    degraded,
                )
            relevant_gaps = tuple(
                gap
                for gap in self._gaps.values()
                if gap.timeframe is timeframe
                and _overlaps(history[0].start_ns, history[-1].end_ns, gap)
            )
            if relevant_gaps:
                return self._failure(
                    SuppressionCode.COVERAGE_GAP,
                    f"{role.value} history overlaps known missing coverage",
                    execute_bar,
                    relevant_gaps,
                )
            selected[role] = history
        return AlignmentOutcome(
            snapshot=CausalSnapshot(self._plan, self._lineage, execute_bar, selected)
        )

    def _failure(
        self,
        code: SuppressionCode,
        detail: str,
        execute_bar: FinalBar,
        references: tuple[FinalBar, ...] | tuple[CoverageGap, ...] = (),
    ) -> AlignmentOutcome:
        assert self._lineage is not None
        return AlignmentOutcome(
            failure=AlignmentFailure(
                code=code,
                detail=detail,
                signal_type=self._plan.signal_type,
                lineage=self._lineage,
                execute_bar=execute_bar,
                references=tuple(sorted(reference.identity for reference in references)),
            )
        )

    def _trim_history(self) -> None:
        for bars in self._bars.values():
            if len(bars) > self._history_limit:
                removed = bars[: -self._history_limit]
                del bars[: -self._history_limit]
                for bar in removed:
                    del self._bar_by_interval[_bar_interval_key(bar)]
                    self._evaluated_execute_ids.discard(bar.identity)
        earliest_retained_start = {
            timeframe: min(bar.start_ns for bar in bars)
            for timeframe, bars in self._bars.items()
            if bars
        }
        self._gaps = {
            identity: gap
            for identity, gap in self._gaps.items()
            if (
                gap.timeframe not in earliest_retained_start
                or gap.end_ns > earliest_retained_start[gap.timeframe]
            )
        }


StatefulCausalAligner = CausalAligner
