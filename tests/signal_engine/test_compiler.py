from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from stoic_derived.signal_engine import compiler
from stoic_derived.signal_engine.compiler import (
    BarOperand,
    BlockerCode,
    ComparisonPredicate,
    CompiledRuleSet,
    ConstantOperand,
    WindowPredicate,
    compile_production_release,
    production_readiness,
)


def test_no_release_is_a_typed_zero_program_state() -> None:
    result = compile_production_release(None, None)

    assert result.program is None
    assert result.readiness.ready is False
    assert result.readiness.blockers == (
        compiler.CompilationBlocker(
            BlockerCode.RELEASE_UNAVAILABLE,
            "a pinned signed published release is required",
        ),
    )
    assert production_readiness().blockers == result.readiness.blockers


def test_production_boundary_rejects_non_published_and_unpinned_paths(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text("schema_version: '1.0'\n", encoding="utf-8")

    result = compile_production_release(candidate, "0" * 64)

    assert result.program is None
    assert result.readiness.blockers[0].code is BlockerCode.RELEASE_UNAVAILABLE
    assert "published JSON release" in result.readiness.blockers[0].message


def test_current_candidate_cannot_bypass_published_release_boundary() -> None:
    result = compile_production_release(Path("strategy/rulebook.yaml"), "0" * 64)

    assert result.program is None
    assert result.readiness.blockers[0].code is BlockerCode.RELEASE_UNAVAILABLE


def test_semantic_readiness_reports_every_missing_live_contract_deterministically() -> None:
    release = _release_with_executable_rules([_base_rule("one")])

    result = compiler._compile_loaded_release(release, "1" * 64)

    assert result.program is None
    assert [blocker.code for blocker in result.readiness.blockers] == [
        BlockerCode.MISSING_CONFIDENCE_OUTPUT_BINDING,
        BlockerCode.MISSING_CONFIDENCE_THRESHOLD,
        BlockerCode.MISSING_FEATURE_IMPLEMENTATION,
        BlockerCode.MISSING_MARKET_DATA_BINDING,
        BlockerCode.MISSING_OPERAND_UNIT,
        BlockerCode.MISSING_REARM_POLICY,
        BlockerCode.MISSING_ROLE_BOUND_OPERAND,
        BlockerCode.MISSING_TRADE_TYPE,
    ]


def test_duplicate_setup_direction_profiles_are_rejected() -> None:
    first = _complete_rule("first")
    second = _complete_rule("second")
    result = compiler._compile_loaded_release(
        _release_with_executable_rules([first, second]), "2" * 64
    )

    assert result.program is None
    duplicate = next(
        blocker
        for blocker in result.readiness.blockers
        if blocker.code is BlockerCode.DUPLICATE_PROFILE
    )
    assert duplicate.rule_id == "second"
    assert any(
        blocker.code is BlockerCode.MISSING_PROFILE_COVERAGE
        for blocker in result.readiness.blockers
    )


def test_complete_private_mapping_becomes_a_closed_typed_program() -> None:
    result = compiler._compile_loaded_release(
        _release_with_executable_rules(_complete_profile_matrix()), "3" * 64
    )

    assert result.readiness.ready is True
    assert result.program is not None
    assert result.program.lookback_by_role == (("htf", 0), ("setup", 0), ("execute", 0))
    assert result.program.profiles[0].formula.entry == ConstantOperand(Decimal("8"))
    component = result.program.profiles[0].formula.confidence.components[0]
    assert component.feature_id == "test_feature"
    assert component.predicate == compiler.ComparisonPredicate(
        "gt",
        compiler.BarOperand("execute", "close", 0),
        compiler.ConstantOperand(Decimal("0")),
    )


def test_private_strategy_neutral_fixture_has_both_orientations_and_exact_constants() -> None:
    program = compiler._strategy_neutral_test_program()

    assert isinstance(program, CompiledRuleSet)
    assert [
        (profile.direction, profile.formula.orientation_guard) for profile in program.profiles
    ] == [
        ("long", "target_gt_entry_gt_stop"),
        ("short", "stop_gt_entry_gt_target"),
    ]
    assert program.profiles[0].formula.entry.value == Decimal("2")
    assert program.profiles[0].formula.confidence.threshold == 50
    assert "_strategy_neutral_test_program" not in compiler.__all__


def test_program_lookback_includes_temporal_windows_crossings_and_operand_offsets() -> None:
    program = compiler._strategy_neutral_test_program()
    predicate = WindowPredicate(
        "within_bars",
        5,
        ComparisonPredicate(
            "crosses_above",
            BarOperand("htf", "close", 2),
            ConstantOperand(Decimal("0")),
        ),
    )
    profile = replace(program.profiles[0], predicate=predicate)

    assert dict(compiler._lookback_by_role((profile,))) == {
        "htf": 7,
        "setup": 0,
        "execute": 0,
    }


def test_unimplemented_derived_feature_cannot_enter_a_ready_program() -> None:
    rules = _complete_profile_matrix()
    rules[0]["predicate"]["left"] = {
        "kind": "derived_feature",
        "role": "execute",
        "feature": "test_feature",
        "offset": 0,
    }

    result = compiler._compile_loaded_release(
        _release_with_executable_rules(rules),
        "4" * 64,
    )

    assert result.program is None
    assert any(
        blocker.code is BlockerCode.MISSING_FEATURE_IMPLEMENTATION
        for blocker in result.readiness.blockers
    )


@pytest.mark.parametrize(
    (("mutation", "expected_code")),
    (
        ("quantity_entry", BlockerCode.UNSUPPORTED_SHAPE),
        ("mixed_predicate_dimensions", BlockerCode.UNSUPPORTED_SHAPE),
        ("unsupported_rearm", BlockerCode.UNSUPPORTED_REARM_POLICY),
        ("negative_confidence_weight", BlockerCode.UNSUPPORTED_SHAPE),
        ("confidence_weight_over_100", BlockerCode.UNSUPPORTED_SHAPE),
        ("confidence_sum_over_100", BlockerCode.UNSUPPORTED_SHAPE),
        ("unreachable_confidence_threshold", BlockerCode.UNSUPPORTED_SHAPE),
    ),
)
def test_semantically_unsupported_contracts_cannot_enter_a_ready_program(
    mutation: str,
    expected_code: BlockerCode,
) -> None:
    rules = _complete_profile_matrix()
    first = rules[0]
    confidence = first["signal"]["confidence"]

    if mutation == "quantity_entry":
        first["signal"]["entry"]["unit"] = "quantity"
    elif mutation == "mixed_predicate_dimensions":
        first["predicate"]["left"]["field"] = "volume"
    elif mutation == "unsupported_rearm":
        first["rearm"]["policy"] = "after_flat"
    elif mutation == "negative_confidence_weight":
        confidence["features"][0]["weight"] = -1
    elif mutation == "confidence_weight_over_100":
        confidence["features"][0]["weight"] = 101
    elif mutation == "confidence_sum_over_100":
        second = dict(confidence["features"][0])
        second["id"] = "second_test_feature"
        second["weight"] = 60
        confidence["features"][0]["weight"] = 60
        confidence["features"].append(second)
    elif mutation == "unreachable_confidence_threshold":
        confidence["threshold"] = 51
    else:
        raise AssertionError("unhandled test mutation")

    result = compiler._compile_loaded_release(
        _release_with_executable_rules(rules),
        "5" * 64,
    )

    assert result.program is None
    assert any(blocker.code is expected_code for blocker in result.readiness.blockers)


def test_nested_temporal_lookback_cannot_exceed_the_compiled_bound() -> None:
    program = compiler._strategy_neutral_test_program()
    leaf = ComparisonPredicate(
        "gt",
        BarOperand("execute", "close", 0),
        ConstantOperand(Decimal("0")),
    )
    profile = replace(
        program.profiles[0],
        predicate=WindowPredicate(
            "within_bars",
            1_000,
            WindowPredicate("within_bars", 1_000, leaf),
        ),
    )

    with pytest.raises(ValueError, match="combined temporal lookback"):
        compiler._lookback_by_role((profile,))


def _release_with_executable_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "1.0", "rulebook_version": "1.0.0", "rules": rules}


def _base_rule(rule_id: str) -> dict[str, Any]:
    return {
        "id": rule_id,
        "kind": "executable_rule",
        "setup_type": "test_setup",
        "direction": "long",
        "entry_model": "test_entry",
        "predicate": {
            "op": "gt",
            "left": {"kind": "bar_field", "field": "close", "offset": 0},
            "right": {"kind": "constant", "value": "0"},
        },
        "signal": {
            "entry": {"kind": "constant", "value": "2"},
            "stop": {"kind": "constant", "value": "1"},
            "target": {"kind": "constant", "value": "3"},
            "orientation_guard": {"op": "target_gt_entry_gt_stop"},
            "r_multiple": {"op": "reward_over_risk"},
            "confidence": {"op": "weighted_sum"},
        },
    }


def _complete_rule(rule_id: str) -> dict[str, Any]:
    rule = _base_rule(rule_id)
    rule["trade_type"] = "Scalp"
    rule["predicate"]["left"]["role"] = "execute"
    rule["predicate"]["right"]["unit"] = "ticks"
    for field in ("entry", "stop", "target"):
        rule["signal"][field]["unit"] = "price_points"
    rule["feature_bindings"] = {"test_feature": {"calculator": "test_only"}}
    rule["signal"]["confidence"].update(
        {
            "features": [
                {
                    "id": "test_feature",
                    "weight": 50,
                    "when": {
                        "op": "gt",
                        "left": {
                            "kind": "bar_field",
                            "role": "execute",
                            "field": "close",
                            "offset": 0,
                        },
                        "right": {"kind": "constant", "value": "0", "unit": "ticks"},
                    },
                }
            ],
            "range": {"min": 0, "max": 100},
        }
    )
    rule["signal"]["confidence"]["threshold"] = 50
    rule["rearm"] = {"policy": "once_per_execute_bar"}
    rule["market_data"] = {
        "profile": "test_market_data",
        "source": "market-test",
        "schema_version": "market-data/v1",
        "calendar_fingerprint": "a" * 64,
        "aggregation_fingerprint": "a" * 64,
        "tick_nanos": 250_000_000,
    }
    return rule


def _complete_profile_matrix() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for trade_type in ("Scalp", "Day", "Swing", "Position"):
        for setup_type in ("break_and_retest", "swing_failure_pattern"):
            for direction in ("long", "short"):
                rule = _complete_rule(f"{trade_type.lower()}-{setup_type}-{direction}")
                rule["trade_type"] = trade_type
                rule["setup_type"] = setup_type
                rule["direction"] = direction
                guard = (
                    "target_gt_entry_gt_stop" if direction == "long" else "stop_gt_entry_gt_target"
                )
                rule["signal"]["orientation_guard"] = {"op": guard}
                if direction == "short":
                    rule["signal"]["stop"] = {
                        "kind": "constant",
                        "value": "3",
                        "unit": "price_points",
                    }
                    rule["signal"]["target"] = {
                        "kind": "constant",
                        "value": "1",
                        "unit": "price_points",
                    }
                rules.append(rule)
    return rules
