from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from stoic_derived.market_data.model import FinalBar, InstrumentSpec, Timeframe
from stoic_derived.signal_engine.compiler import (
    BarOperand,
    BooleanPredicate,
    ComparisonPredicate,
    ConstantOperand,
    DerivedFeatureOperand,
    NotPredicate,
    SequencePredicate,
    WindowPredicate,
    _strategy_neutral_test_program,
)
from stoic_derived.signal_engine.evaluator import (
    EvaluationState,
    evaluate_predicate,
    evaluate_profile_for_program,
)
from stoic_derived.signal_engine.model import (
    Direction,
    MarketLineage,
    Role,
    SetupType,
    SuppressionCode,
)

FINGERPRINT = "a" * 64


def _bar(timeframe: Timeframe, end_ns: int, close: int) -> FinalBar:
    start_ns = end_ns - (timeframe.duration_ns or 100)
    return FinalBar(
        source="market-test",
        instrument=InstrumentSpec("NQ", "NQ.c.0"),
        instrument_id=101,
        timeframe=timeframe,
        calendar_fingerprint=FINGERPRINT,
        aggregation_fingerprint=FINGERPRINT,
        start_ns=start_ns,
        end_ns=end_ns,
        trading_date=date(2026, 1, 2) if timeframe.is_session_based else None,
        open_ticks=close,
        high_ticks=close,
        low_ticks=close,
        close_ticks=close,
        volume=10,
        trade_count=1,
        first_event_ns=start_ns,
        last_event_ns=end_ns - 1,
    )


def _history(values: tuple[int, ...] = (1, 2, 3)) -> dict[Role, tuple[FinalBar, ...]]:
    end_base = 10_000_000_000_000
    return {
        Role.HTF: tuple(
            _bar(Timeframe.FIFTEEN_MINUTES, end_base + index, value)
            for index, value in enumerate(values)
        ),
        Role.SETUP: tuple(
            _bar(Timeframe.FIVE_MINUTES, end_base + index, value)
            for index, value in enumerate(values)
        ),
        Role.EXECUTE: tuple(
            _bar(Timeframe.ONE_MINUTE, end_base + index, value)
            for index, value in enumerate(values)
        ),
        Role.MANAGE: tuple(
            _bar(Timeframe.FIVE_MINUTES, end_base + index, value)
            for index, value in enumerate(values)
        ),
    }


@pytest.mark.parametrize(
    ("operator", "constant", "state"),
    [
        ("eq", "3", EvaluationState.MATCHED),
        ("lt", "4", EvaluationState.MATCHED),
        ("lte", "3", EvaluationState.MATCHED),
        ("gt", "2", EvaluationState.MATCHED),
        ("gte", "3", EvaluationState.MATCHED),
    ],
)
def test_exact_comparisons_use_tick_values(
    operator: str, constant: str, state: EvaluationState
) -> None:
    predicate = ComparisonPredicate(
        operator,  # type: ignore[arg-type]
        BarOperand("execute", "close", 0),
        ConstantOperand(Decimal(constant)),
    )

    assert evaluate_predicate(predicate, _history()).state is state


def test_crossings_boolean_windows_and_sequence_are_current_inclusive() -> None:
    history = _history((1, 1, 3))
    above = ComparisonPredicate(
        "crosses_above", BarOperand("execute", "close", 0), ConstantOperand(Decimal("2"))
    )
    below = ComparisonPredicate(
        "crosses_below", BarOperand("execute", "close", 0), ConstantOperand(Decimal("4"))
    )
    current_positive = ComparisonPredicate(
        "gt", BarOperand("execute", "close", 0), ConstantOperand(Decimal("0"))
    )
    current_one = ComparisonPredicate(
        "eq", BarOperand("execute", "close", 0), ConstantOperand(Decimal("1"))
    )

    assert evaluate_predicate(above, history).state is EvaluationState.MATCHED
    assert evaluate_predicate(below, history).state is EvaluationState.NOT_MATCHED
    assert evaluate_predicate(BooleanPredicate("all", (above, current_positive)), history).matched
    assert evaluate_predicate(BooleanPredicate("any", (below, above)), history).matched
    assert evaluate_predicate(NotPredicate(current_one), history).matched
    assert evaluate_predicate(WindowPredicate("within_bars", 3, current_one), history).matched
    assert not evaluate_predicate(WindowPredicate("consecutive", 3, current_one), history).matched
    assert evaluate_predicate(
        SequencePredicate(3, (current_one, current_positive)), history
    ).matched


def test_temporal_predicates_report_insufficient_history_not_false() -> None:
    predicate = WindowPredicate(
        "within_bars",
        4,
        ComparisonPredicate("gt", BarOperand("execute", "close", 0), ConstantOperand(Decimal("0"))),
    )

    assert evaluate_predicate(predicate, _history()).state is EvaluationState.INSUFFICIENT_HISTORY


def test_mixed_dimensions_and_nonprice_signal_units_are_unavailable() -> None:
    history = _history()
    mixed = ComparisonPredicate(
        "gt",
        BarOperand("execute", "volume", 0),
        ConstantOperand(Decimal("1"), "ticks"),
    )

    assert evaluate_predicate(mixed, history).state is EvaluationState.UNAVAILABLE

    base = _strategy_neutral_test_program().profiles[0]
    profile = replace(
        base,
        setup_type=SetupType.BREAK_AND_RETEST.value,
        formula=replace(
            base.formula,
            entry=ConstantOperand(Decimal("2"), "quantity"),
        ),
    )
    execute = history[Role.EXECUTE][-1]
    result = evaluate_profile_for_program(
        profile,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=MarketLineage.from_final_bar(execute),
        execute_bar=execute,
    )

    assert result.suppression is not None
    assert result.suppression.code is SuppressionCode.SEMANTIC_UNSUPPORTED


def test_profile_constructs_exact_signal_and_invalid_prices_suppress() -> None:
    base = _strategy_neutral_test_program().profiles[0]
    profile = replace(base, setup_type=SetupType.BREAK_AND_RETEST.value)
    history = _history()
    execute = history[Role.EXECUTE][-1]
    lineage = MarketLineage.from_final_bar(execute)
    result = evaluate_profile_for_program(
        profile,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
        causal_bar_ids=tuple(bar.identity for bars in history.values() for bar in bars),
    )

    assert result.signal is not None
    assert result.signal.direction is Direction.LONG
    assert result.signal.risk_reward.numerator == 1
    assert result.signal.risk_reward.denominator == 1
    assert result.signal.confidence == 50
    assert result.signal.causal_bar_ids == tuple(sorted(set(result.signal.causal_bar_ids)))

    off_tick = replace(
        profile,
        formula=replace(profile.formula, entry=ConstantOperand(Decimal("1.5"))),
    )
    invalid = evaluate_profile_for_program(
        off_tick,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
    )
    assert invalid.suppression is not None
    assert invalid.suppression.code is SuppressionCode.OFF_TICK_PRICE

    invalid_orientation = replace(
        profile,
        formula=replace(profile.formula, target=ConstantOperand(Decimal("1"))),
    )
    orientation_result = evaluate_profile_for_program(
        invalid_orientation,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
    )
    assert orientation_result.suppression is not None
    assert orientation_result.suppression.code is SuppressionCode.INVALID_ORIENTATION


def test_profile_supports_short_and_suppresses_threshold_or_unavailable_components() -> None:
    program = _strategy_neutral_test_program()
    profile = replace(program.profiles[1], setup_type=SetupType.BREAK_AND_RETEST.value)
    history = _history()
    execute = history[Role.EXECUTE][-1]
    lineage = MarketLineage.from_final_bar(execute)
    short = evaluate_profile_for_program(
        profile,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
    )
    assert short.signal is not None
    assert short.signal.direction is Direction.SHORT

    below_threshold = replace(
        profile,
        formula=replace(
            profile.formula, confidence=replace(profile.formula.confidence, threshold=51)
        ),
    )
    threshold_result = evaluate_profile_for_program(
        below_threshold,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
    )
    assert threshold_result.suppression is not None
    assert threshold_result.suppression.code is SuppressionCode.PREDICATE_NOT_MATCHED

    component = profile.formula.confidence.components[0]
    unavailable = replace(
        profile,
        formula=replace(
            profile.formula,
            confidence=replace(
                profile.formula.confidence,
                components=(
                    replace(
                        component,
                        predicate=ComparisonPredicate(
                            "gt",
                            DerivedFeatureOperand("execute", "not_implemented", 0),
                            ConstantOperand(Decimal("0")),
                        ),
                    ),
                ),
            ),
        ),
    )
    unavailable_result = evaluate_profile_for_program(
        unavailable,
        release_file_sha256="b" * 64,
        rulebook_version="test",
        history=history,
        lineage=lineage,
        execute_bar=execute,
    )
    assert unavailable_result.suppression is not None
    assert unavailable_result.suppression.code is SuppressionCode.SEMANTIC_UNSUPPORTED
