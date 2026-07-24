"""Pure, exact evaluation of the closed SP2 expression vocabulary.

This module intentionally knows nothing about release loading, alignment
buffers, or delivery.  It evaluates one already-causal role history into a
complete decision (or an auditable suppression) without binary floats.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from stoic_derived.market_data.model import FinalBar
from stoic_derived.signal_engine.compiler import (
    BarOperand,
    BooleanPredicate,
    ComparisonPredicate,
    CompiledProfile,
    ConstantOperand,
    DerivedFeatureOperand,
    NotPredicate,
    Operand,
    Predicate,
    SequencePredicate,
    WindowPredicate,
)
from stoic_derived.signal_engine.model import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    Direction,
    MarketLineage,
    RationalR,
    Role,
    SetupType,
    SignalRecord,
    SignalType,
    SignalValidationError,
    Suppression,
    SuppressionCode,
)

ENGINE_VERSION = "signal-engine/v1"
SIGNAL_SOURCE = "stoic-signal-engine/v1"


class EvaluationState(StrEnum):
    """The three meaningful outcomes of a closed predicate evaluation."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class PredicateResult:
    """A predicate result plus the exact bars it read."""

    state: EvaluationState
    references: tuple[str, ...]

    @property
    def matched(self) -> bool:
        return self.state is EvaluationState.MATCHED


@dataclass(frozen=True, slots=True)
class ProfileEvaluation:
    """The single complete decision for a profile at one execute-bar close."""

    signal: SignalRecord | None = None
    suppression: Suppression | None = None

    def __post_init__(self) -> None:
        if (self.signal is None) == (self.suppression is None):
            raise ValueError("profile evaluation must contain exactly one result")


class _UnavailableFeature(ValueError):
    """A compiled feature has no evaluator calculator in this closed runtime."""


def evaluate_predicate(
    predicate: Predicate,
    history: Mapping[Role, tuple[FinalBar, ...]],
) -> PredicateResult:
    """Evaluate ``predicate`` at the current bar of every referenced role.

    Histories are chronological and include the current role bar as their last
    item.  A missing bar is deliberately distinct from a false predicate.
    """
    return _evaluate_predicate(predicate, _normalise_history(history), 0)


def evaluate_profile(
    profile: CompiledProfile,
    *,
    history: Mapping[Role, tuple[FinalBar, ...]],
    lineage: MarketLineage,
    execute_bar: FinalBar,
    release_file_sha256: str,
    rulebook_version: str,
    source: str = SIGNAL_SOURCE,
    engine_version: str = ENGINE_VERSION,
) -> ProfileEvaluation:
    """Turn one compiled profile and causal snapshot into one complete result."""
    histories = _normalise_history(history)
    signal_type = SignalType(profile.trade_type)
    common = _SuppressionContext(
        source=source,
        release_file_sha256=release_file_sha256,
        rulebook_version=rulebook_version,
        engine_version=engine_version,
        signal_type=signal_type,
        signal_ts_ns=execute_bar.end_ns,
        lineage=lineage,
        rule_id=profile.rule_id,
    )

    predicate = _evaluate_predicate(profile.predicate, histories, 0)
    if predicate.state is EvaluationState.INSUFFICIENT_HISTORY:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.INSUFFICIENT_LOOKBACK,
                "predicate requires unavailable closed-bar history",
                predicate.references,
            )
        )
    if predicate.state is EvaluationState.UNAVAILABLE:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.SEMANTIC_UNSUPPORTED,
                "predicate requires an unavailable derived feature",
                predicate.references,
            )
        )
    if not predicate.matched:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.PREDICATE_NOT_MATCHED,
                "profile predicate did not match",
                predicate.references,
            )
        )

    references = set(predicate.references)
    if any(
        _operand_dimension(operand) != "ticks"
        for operand in (profile.formula.entry, profile.formula.stop, profile.formula.target)
    ):
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.SEMANTIC_UNSUPPORTED,
                "signal price expression has an incompatible unit",
                tuple(sorted(references)),
            )
        )
    try:
        entry, entry_references = _evaluate_operand(profile.formula.entry, histories, 0)
        stop, stop_references = _evaluate_operand(profile.formula.stop, histories, 0)
        target, target_references = _evaluate_operand(profile.formula.target, histories, 0)
    except _UnavailableFeature:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.SEMANTIC_UNSUPPORTED,
                "signal value requires an unavailable derived feature",
                tuple(sorted(references)),
            )
        )
    except _InsufficientHistory as exc:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.INSUFFICIENT_LOOKBACK,
                "signal value requires unavailable closed-bar history",
                tuple(sorted(references | set(exc.references))),
            )
        )
    references.update(entry_references)
    references.update(stop_references)
    references.update(target_references)

    prices = (entry, stop, target)
    if any(not value.is_finite() or value != value.to_integral_value() for value in prices):
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.OFF_TICK_PRICE,
                "entry, stop, and target must resolve to integral ticks",
                tuple(sorted(references)),
            )
        )
    entry_ticks, stop_ticks, target_ticks = (int(value) for value in prices)
    if any(value <= 0 for value in (entry_ticks, stop_ticks, target_ticks)):
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.UNFILLABLE_PRICE,
                "entry, stop, and target must resolve to positive ticks",
                tuple(sorted(references)),
            )
        )

    direction = Direction(profile.direction)
    try:
        risk_reward = RationalR.from_prices(direction, entry_ticks, stop_ticks, target_ticks)
    except SignalValidationError:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.INVALID_ORIENTATION,
                "entry, stop, and target violate the profile direction",
                tuple(sorted(references)),
            )
        )

    confidence = 0
    for component in profile.formula.confidence.components:
        result = _evaluate_predicate(component.predicate, histories, 0)
        references.update(result.references)
        if result.state is EvaluationState.INSUFFICIENT_HISTORY:
            return ProfileEvaluation(
                suppression=common.make(
                    SuppressionCode.INSUFFICIENT_LOOKBACK,
                    f"confidence component {component.feature_id!r} requires unavailable history",
                    tuple(sorted(references)),
                )
            )
        if result.state is EvaluationState.UNAVAILABLE:
            return ProfileEvaluation(
                suppression=common.make(
                    SuppressionCode.SEMANTIC_UNSUPPORTED,
                    f"confidence component {component.feature_id!r} is unavailable",
                    tuple(sorted(references)),
                )
            )
        if result.matched:
            confidence += component.weight

    formula = profile.formula.confidence
    if not (
        formula.minimum <= confidence <= formula.maximum
        and CONFIDENCE_MIN <= confidence <= CONFIDENCE_MAX
    ):
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.INVALID_CONFIDENCE,
                "confidence score is outside its declared bounded range",
                tuple(sorted(references)),
            )
        )
    if confidence < formula.threshold:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.PREDICATE_NOT_MATCHED,
                "confidence score is below the emission threshold",
                tuple(sorted(references)),
            )
        )

    try:
        setup_type = SetupType(profile.setup_type)
    except ValueError:
        return ProfileEvaluation(
            suppression=common.make(
                SuppressionCode.SEMANTIC_UNSUPPORTED,
                "profile setup type is outside the closed signal vocabulary",
                tuple(sorted(references)),
            )
        )
    return ProfileEvaluation(
        signal=SignalRecord(
            signal_type=signal_type,
            direction=direction,
            entry_ticks=entry_ticks,
            stop_ticks=stop_ticks,
            target_ticks=target_ticks,
            risk_reward=risk_reward,
            setup_type=setup_type,
            entry_model=profile.entry_model,
            confidence=confidence,
            signal_ts_ns=execute_bar.end_ns,
            source=source,
            release_file_sha256=release_file_sha256,
            rulebook_version=rulebook_version,
            rule_id=profile.rule_id,
            engine_version=engine_version,
            lineage=lineage,
            causal_bar_ids=tuple(sorted(references)),
        )
    )


def evaluate_profile_for_program(
    profile: CompiledProfile,
    *,
    release_file_sha256: str,
    rulebook_version: str,
    history: Mapping[Role, tuple[FinalBar, ...]],
    lineage: MarketLineage,
    execute_bar: FinalBar,
    causal_bar_ids: tuple[str, ...] = (),
    source: str = SIGNAL_SOURCE,
    engine_version: str = ENGINE_VERSION,
) -> ProfileEvaluation:
    """Evaluate a profile with the program identity needed for a SignalRecord."""
    result = evaluate_profile(
        profile,
        history=history,
        lineage=lineage,
        execute_bar=execute_bar,
        release_file_sha256=release_file_sha256,
        rulebook_version=rulebook_version,
        source=source,
        engine_version=engine_version,
    )
    if result.signal is None:
        return result
    signal = result.signal
    # Add every alignment input, including bars that supplied complete causal
    # context but were not read by a particular leaf operand.
    return ProfileEvaluation(
        signal=SignalRecord(
            signal.signal_type,
            signal.direction,
            signal.entry_ticks,
            signal.stop_ticks,
            signal.target_ticks,
            signal.risk_reward,
            signal.setup_type,
            signal.entry_model,
            signal.confidence,
            signal.signal_ts_ns,
            signal.source,
            signal.release_file_sha256,
            signal.rulebook_version,
            signal.rule_id,
            signal.engine_version,
            signal.lineage,
            tuple(sorted(set(signal.causal_bar_ids) | set(causal_bar_ids))),
        )
    )


@dataclass(frozen=True, slots=True)
class _SuppressionContext:
    source: str
    release_file_sha256: str
    rulebook_version: str
    engine_version: str
    signal_type: SignalType
    signal_ts_ns: int
    lineage: MarketLineage
    rule_id: str

    def make(self, code: SuppressionCode, detail: str, references: tuple[str, ...]) -> Suppression:
        return Suppression(
            code=code,
            detail=detail,
            source=self.source,
            release_file_sha256=self.release_file_sha256,
            rulebook_version=self.rulebook_version,
            engine_version=self.engine_version,
            signal_type=self.signal_type,
            signal_ts_ns=self.signal_ts_ns,
            lineage=self.lineage,
            rule_id=self.rule_id,
            references=tuple(sorted(set(references))),
        )


@dataclass(frozen=True, slots=True)
class _InsufficientHistory(ValueError):
    references: tuple[str, ...]


def _normalise_history(
    history: Mapping[Role, tuple[FinalBar, ...]],
) -> Mapping[str, tuple[FinalBar, ...]]:
    return {role.value: bars for role, bars in history.items()}


def _evaluate_predicate(
    predicate: Predicate,
    histories: Mapping[str, tuple[FinalBar, ...]],
    relative_offset: int,
) -> PredicateResult:
    if isinstance(predicate, ComparisonPredicate):
        return _evaluate_comparison(predicate, histories, relative_offset)
    if isinstance(predicate, BooleanPredicate):
        results = tuple(
            _evaluate_predicate(item, histories, relative_offset) for item in predicate.items
        )
        references = _references(*results)
        if any(result.state is EvaluationState.UNAVAILABLE for result in results):
            return PredicateResult(EvaluationState.UNAVAILABLE, references)
        if any(result.state is EvaluationState.INSUFFICIENT_HISTORY for result in results):
            return PredicateResult(EvaluationState.INSUFFICIENT_HISTORY, references)
        matches = tuple(result.matched for result in results)
        return PredicateResult(
            EvaluationState.MATCHED
            if (all(matches) if predicate.operator == "all" else any(matches))
            else EvaluationState.NOT_MATCHED,
            references,
        )
    if isinstance(predicate, NotPredicate):
        result = _evaluate_predicate(predicate.item, histories, relative_offset)
        if (
            result.state is not EvaluationState.MATCHED
            and result.state is not EvaluationState.NOT_MATCHED
        ):
            return result
        return PredicateResult(
            EvaluationState.NOT_MATCHED if result.matched else EvaluationState.MATCHED,
            result.references,
        )
    if isinstance(predicate, WindowPredicate):
        return _evaluate_window(predicate, histories, relative_offset)
    if isinstance(predicate, SequencePredicate):
        return _evaluate_sequence(predicate, histories, relative_offset)
    raise TypeError("unsupported closed predicate")


def _evaluate_comparison(
    predicate: ComparisonPredicate,
    histories: Mapping[str, tuple[FinalBar, ...]],
    relative_offset: int,
) -> PredicateResult:
    left_dimension = _operand_dimension(predicate.left)
    right_dimension = _operand_dimension(predicate.right)
    if left_dimension is None or right_dimension is None or left_dimension != right_dimension:
        return PredicateResult(EvaluationState.UNAVAILABLE, ())
    try:
        left, left_references = _evaluate_operand(predicate.left, histories, relative_offset)
        right, right_references = _evaluate_operand(predicate.right, histories, relative_offset)
        references = tuple(sorted(set(left_references) | set(right_references)))
        if predicate.operator == "crosses_above":
            prior_left, prior_left_references = _evaluate_operand(
                predicate.left, histories, relative_offset + 1
            )
            prior_right, prior_right_references = _evaluate_operand(
                predicate.right, histories, relative_offset + 1
            )
            return PredicateResult(
                EvaluationState.MATCHED
                if left > right and prior_left <= prior_right
                else EvaluationState.NOT_MATCHED,
                tuple(
                    sorted(
                        set(references) | set(prior_left_references) | set(prior_right_references)
                    )
                ),
            )
        if predicate.operator == "crosses_below":
            prior_left, prior_left_references = _evaluate_operand(
                predicate.left, histories, relative_offset + 1
            )
            prior_right, prior_right_references = _evaluate_operand(
                predicate.right, histories, relative_offset + 1
            )
            return PredicateResult(
                EvaluationState.MATCHED
                if left < right and prior_left >= prior_right
                else EvaluationState.NOT_MATCHED,
                tuple(
                    sorted(
                        set(references) | set(prior_left_references) | set(prior_right_references)
                    )
                ),
            )
    except _InsufficientHistory as exc:
        return PredicateResult(EvaluationState.INSUFFICIENT_HISTORY, exc.references)
    except _UnavailableFeature:
        return PredicateResult(EvaluationState.UNAVAILABLE, ())
    except InvalidOperation:
        return PredicateResult(EvaluationState.UNAVAILABLE, ())
    try:
        comparisons = {
            "eq": left == right,
            "lt": left < right,
            "lte": left <= right,
            "gt": left > right,
            "gte": left >= right,
        }
    except InvalidOperation:
        return PredicateResult(EvaluationState.UNAVAILABLE, references)
    return PredicateResult(
        EvaluationState.MATCHED if comparisons[predicate.operator] else EvaluationState.NOT_MATCHED,
        references,
    )


def _evaluate_window(
    predicate: WindowPredicate,
    histories: Mapping[str, tuple[FinalBar, ...]],
    relative_offset: int,
) -> PredicateResult:
    results = tuple(
        _evaluate_predicate(predicate.item, histories, relative_offset + offset)
        for offset in range(predicate.bars)
    )
    references = _references(*results)
    if any(result.state is EvaluationState.UNAVAILABLE for result in results):
        return PredicateResult(EvaluationState.UNAVAILABLE, references)
    if any(result.state is EvaluationState.INSUFFICIENT_HISTORY for result in results):
        return PredicateResult(EvaluationState.INSUFFICIENT_HISTORY, references)
    matched = (
        any(result.matched for result in results)
        if predicate.operator == "within_bars"
        else all(result.matched for result in results)
    )
    return PredicateResult(
        EvaluationState.MATCHED if matched else EvaluationState.NOT_MATCHED, references
    )


def _evaluate_sequence(
    predicate: SequencePredicate,
    histories: Mapping[str, tuple[FinalBar, ...]],
    relative_offset: int,
) -> PredicateResult:
    # The last item is pinned to the current bar.  Earlier items may occur in
    # chronological order anywhere in the previous ``bars - 1`` positions.
    all_results = tuple(
        tuple(
            _evaluate_predicate(item, histories, relative_offset + offset)
            for offset in range(predicate.bars)
        )
        for item in predicate.items
    )
    references = tuple(
        sorted({ref for row in all_results for result in row for ref in result.references})
    )
    states = tuple(result.state for row in all_results for result in row)
    if EvaluationState.UNAVAILABLE in states:
        return PredicateResult(EvaluationState.UNAVAILABLE, references)
    if EvaluationState.INSUFFICIENT_HISTORY in states:
        return PredicateResult(EvaluationState.INSUFFICIENT_HISTORY, references)
    if not all_results[-1][0].matched:
        return PredicateResult(EvaluationState.NOT_MATCHED, references)

    # Offsets grow into the past.  Select the preceding items from oldest to
    # newest, so their offsets are strictly descending.
    candidate_offsets = tuple(range(predicate.bars - 1, 0, -1))
    matched = _sequence_matches(all_results[:-1], candidate_offsets, 0, predicate.bars)
    return PredicateResult(
        EvaluationState.MATCHED if matched else EvaluationState.NOT_MATCHED, references
    )


def _sequence_matches(
    rows: tuple[tuple[PredicateResult, ...], ...],
    candidate_offsets: tuple[int, ...],
    item_index: int,
    maximum_offset: int,
) -> bool:
    if item_index == len(rows):
        return True
    for offset in candidate_offsets:
        if offset >= maximum_offset or not rows[item_index][offset].matched:
            continue
        if _sequence_matches(rows, candidate_offsets, item_index + 1, offset):
            return True
    return False


def _evaluate_operand(
    operand: Operand,
    histories: Mapping[str, tuple[FinalBar, ...]],
    relative_offset: int,
) -> tuple[Decimal, tuple[str, ...]]:
    if isinstance(operand, ConstantOperand):
        return operand.value, ()
    if isinstance(operand, DerivedFeatureOperand):
        raise _UnavailableFeature(operand.feature)
    if not isinstance(operand, BarOperand):
        raise TypeError("unsupported closed operand")
    bars = histories.get(operand.role)
    index = len(bars) - 1 - relative_offset - operand.offset if bars is not None else -1
    if bars is None or index < 0:
        raise _InsufficientHistory(())
    bar = bars[index]
    values = {
        "open": bar.open_ticks,
        "high": bar.high_ticks,
        "low": bar.low_ticks,
        "close": bar.close_ticks,
        "volume": bar.volume,
    }
    return Decimal(values[operand.field]), (bar.identity,)


def _operand_dimension(operand: Operand) -> str | None:
    if isinstance(operand, ConstantOperand):
        return operand.unit if operand.unit in {"ticks", "quantity", "scalar"} else None
    if isinstance(operand, BarOperand):
        return "quantity" if operand.field == "volume" else "ticks"
    return None


def _references(*results: PredicateResult) -> tuple[str, ...]:
    return tuple(sorted({reference for result in results for reference in result.references}))


__all__ = [
    "ENGINE_VERSION",
    "SIGNAL_SOURCE",
    "EvaluationState",
    "PredicateResult",
    "ProfileEvaluation",
    "evaluate_predicate",
    "evaluate_profile",
    "evaluate_profile_for_program",
]
