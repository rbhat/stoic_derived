"""Fail-closed compilation of pinned published strategy releases.

This module deliberately has no authoring-YAML, market-data, or execution
dependency.  The public boundary loads a pinned SP0 JSON release itself, then
either returns a closed program or a deterministic set of readiness blockers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from stoic_derived.strategy.rulebook import PublicationError, load_published_release

type Role = Literal["htf", "setup", "execute"]
type Direction = Literal["long", "short"]
type ConstantUnit = Literal["ticks", "price_points", "quantity", "scalar"]
type ValueDimension = Literal["ticks", "quantity", "scalar"]
MAX_COMPILED_LOOKBACK_OFFSET = 1_000
NANOS_PER_TICK = 250_000_000


class BlockerCode(StrEnum):
    """Closed reasons why a production program cannot be created."""

    RELEASE_UNAVAILABLE = "release_unavailable"
    MISSING_TRADE_TYPE = "missing_trade_type"
    MISSING_ROLE_BOUND_OPERAND = "missing_role_bound_operand"
    MISSING_OPERAND_UNIT = "missing_operand_unit"
    MISSING_FEATURE_IMPLEMENTATION = "missing_feature_implementation"
    MISSING_CONFIDENCE_THRESHOLD = "missing_confidence_threshold"
    MISSING_CONFIDENCE_OUTPUT_BINDING = "missing_confidence_output_binding"
    MISSING_REARM_POLICY = "missing_rearm_policy"
    UNSUPPORTED_REARM_POLICY = "unsupported_rearm_policy"
    MISSING_MARKET_DATA_BINDING = "missing_market_data_binding"
    MISSING_PROFILE_COVERAGE = "missing_profile_coverage"
    DUPLICATE_PROFILE = "duplicate_profile"
    UNSUPPORTED_SHAPE = "unsupported_shape"


@dataclass(frozen=True, slots=True, order=True)
class CompilationBlocker:
    """A stable, machine-readable reason production evaluation is disabled."""

    code: BlockerCode
    message: str
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompilationReadiness:
    """The complete deterministic result of attempting production compilation."""

    ready: bool
    blockers: tuple[CompilationBlocker, ...]


@dataclass(frozen=True, slots=True)
class ConstantOperand:
    """A compiler-normalized value; price constants are converted to ticks."""

    value: Decimal
    unit: ConstantUnit = "ticks"


@dataclass(frozen=True, slots=True)
class MarketDataBinding:
    """Signed market-data semantics that a profile is allowed to evaluate."""

    profile: str
    source: str
    schema_version: str
    calendar_fingerprint: str
    aggregation_fingerprint: str
    tick_nanos: int


@dataclass(frozen=True, slots=True)
class BarOperand:
    role: Role
    field: Literal["open", "high", "low", "close", "volume"]
    offset: int


@dataclass(frozen=True, slots=True)
class DerivedFeatureOperand:
    role: Role
    feature: str
    offset: int


type Operand = ConstantOperand | BarOperand | DerivedFeatureOperand


@dataclass(frozen=True, slots=True)
class ComparisonPredicate:
    operator: Literal["eq", "lt", "lte", "gt", "gte", "crosses_above", "crosses_below"]
    left: Operand
    right: Operand


@dataclass(frozen=True, slots=True)
class BooleanPredicate:
    operator: Literal["all", "any"]
    items: tuple[Predicate, ...]


@dataclass(frozen=True, slots=True)
class NotPredicate:
    item: Predicate


@dataclass(frozen=True, slots=True)
class WindowPredicate:
    operator: Literal["within_bars", "consecutive"]
    bars: int
    item: Predicate


@dataclass(frozen=True, slots=True)
class SequencePredicate:
    bars: int
    items: tuple[Predicate, ...]


type Predicate = (
    ComparisonPredicate | BooleanPredicate | NotPredicate | WindowPredicate | SequencePredicate
)


@dataclass(frozen=True, slots=True)
class SignalFormula:
    """Closed value and confidence operations used by a compiled profile."""

    entry: Operand
    stop: Operand
    target: Operand
    orientation_guard: Literal["target_gt_entry_gt_stop", "stop_gt_entry_gt_target"]
    risk_reward_operation: Literal["reward_over_risk"]
    confidence: CompiledConfidenceFormula


@dataclass(frozen=True, slots=True)
class CompiledConfidenceComponent:
    """A bounded, deterministic contribution to an emission confidence score."""

    feature_id: str
    weight: int
    predicate: Predicate


@dataclass(frozen=True, slots=True)
class CompiledConfidenceFormula:
    """Closed confidence calculation metadata; it never calls a learned system."""

    components: tuple[CompiledConfidenceComponent, ...]
    minimum: int
    maximum: int
    threshold: int


@dataclass(frozen=True, slots=True)
class CompiledProfile:
    """One unique type/setup/direction profile in a closed program."""

    rule_id: str
    trade_type: Literal["Scalp", "Day", "Swing", "Position"]
    setup_type: str
    direction: Direction
    entry_model: str
    predicate: Predicate
    formula: SignalFormula
    emission_policy: str
    rearm_policy: str
    market_data_binding: MarketDataBinding


@dataclass(frozen=True, slots=True)
class StrategyProgram:
    """Immutable program identity and its unique, deterministic profiles."""

    release_sha256: str
    rulebook_version: str
    schema_version: str
    profiles: tuple[CompiledProfile, ...]
    lookback_by_role: tuple[tuple[Role, int], ...]


# Compatibility spelling for callers that adopted the design document's
# earlier name; this remains the same concrete frozen type at runtime.
CompiledRuleSet = StrategyProgram


@dataclass(frozen=True, slots=True)
class ProductionCompilation:
    """Public production result; a blocked release has no executable program."""

    program: StrategyProgram | None
    readiness: CompilationReadiness


def production_readiness(
    release_path: Path | str | None = None,
    expected_sha256: str | None = None,
    public_key: Ed25519PublicKey | bytes | None = None,
) -> CompilationReadiness:
    """Check a pinned signed release without ever accepting authoring data.

    Omitting any release identity is an intentional and deterministic blocked
    state, useful for the repository candidate before it becomes publishable.
    """
    return compile_production_release(release_path, expected_sha256, public_key).readiness


def compile_production_release(
    release_path: Path | str | None,
    expected_sha256: str | None,
    public_key: Ed25519PublicKey | bytes | None = None,
) -> ProductionCompilation:
    """Load one SP0-published, pinned release and compile it fail-closed.

    There is deliberately no public ``Mapping`` input and no switch for test
    fixtures.  Thus an unsigned mapping or a private fixture can never reach
    this production boundary.
    """
    if release_path is None or expected_sha256 is None:
        return _blocked(
            CompilationBlocker(
                BlockerCode.RELEASE_UNAVAILABLE,
                "a pinned signed published release is required",
            )
        )
    try:
        release = load_published_release(release_path, expected_sha256, public_key)
    except (PublicationError, TypeError) as exc:
        return _blocked(
            CompilationBlocker(
                BlockerCode.RELEASE_UNAVAILABLE,
                f"published release is unavailable: {exc}",
            )
        )
    return _compile_loaded_release(release, expected_sha256)


def _blocked(*blockers: CompilationBlocker) -> ProductionCompilation:
    ordered = tuple(sorted(set(blockers)))
    return ProductionCompilation(None, CompilationReadiness(False, ordered))


def _compile_loaded_release(
    release: Mapping[str, Any], release_sha256: str
) -> ProductionCompilation:
    """Compile loader-validated data; retained private for focused unit tests."""
    blockers = _semantic_blockers(release)
    if blockers:
        return _blocked(*blockers)
    try:
        profiles = tuple(_compile_profile(rule) for rule in _executable_rules(release))
        program = StrategyProgram(
            release_sha256=release_sha256,
            rulebook_version=_required_string(release.get("rulebook_version"), "rulebook_version"),
            schema_version=_required_string(release.get("schema_version"), "schema_version"),
            profiles=tuple(sorted(profiles, key=_profile_sort_key)),
            lookback_by_role=_lookback_by_role(profiles),
        )
    except _UnsupportedShape as exc:
        return _blocked(CompilationBlocker(BlockerCode.UNSUPPORTED_SHAPE, str(exc)))
    return ProductionCompilation(program, CompilationReadiness(True, ()))


def _semantic_blockers(release: Mapping[str, Any]) -> tuple[CompilationBlocker, ...]:
    blockers: list[CompilationBlocker] = []
    executable_rules = _executable_rules(release)
    profiles: set[tuple[str, str, str]] = set()
    all_rules_have_type = True
    for rule in executable_rules:
        rule_id = _optional_string(rule.get("id"))
        trade_type = _optional_string(rule.get("trade_type"))
        if trade_type not in {"Scalp", "Day", "Swing", "Position"}:
            all_rules_have_type = False
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_TRADE_TYPE,
                    "rule has no explicit valid Trade Type binding",
                    rule_id,
                )
            )
        setup_type = _optional_string(rule.get("setup_type"))
        direction = _optional_string(rule.get("direction"))
        if trade_type is not None and setup_type is not None and direction is not None:
            profile = (trade_type, setup_type, direction)
            if profile in profiles:
                blockers.append(
                    CompilationBlocker(
                        BlockerCode.DUPLICATE_PROFILE,
                        "duplicate Trade Type/setup/direction profile",
                        rule_id,
                    )
                )
            profiles.add(profile)
        if not _operands_are_role_bound(rule.get("predicate")):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_ROLE_BOUND_OPERAND,
                    "predicate operands must bind every bar or feature to htf, setup, or execute",
                    rule_id,
                )
            )
        if not _constants_have_explicit_units(rule):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_OPERAND_UNIT,
                    "every constant requires an explicit signed unit",
                    rule_id,
                )
            )
        if not _has_feature_implementations(rule):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_FEATURE_IMPLEMENTATION,
                    "rule has no signed deterministic feature implementation bindings",
                    rule_id,
                )
            )
        signal = rule.get("signal")
        confidence = signal.get("confidence") if isinstance(signal, Mapping) else None
        if not isinstance(confidence, Mapping) or not isinstance(confidence.get("threshold"), int):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_CONFIDENCE_THRESHOLD,
                    "confidence requires an explicit integer emission threshold",
                    rule_id,
                )
            )
        confidence_range = confidence.get("range") if isinstance(confidence, Mapping) else None
        if confidence_range != {"min": 0, "max": 100}:
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_CONFIDENCE_OUTPUT_BINDING,
                    "confidence output range must be explicitly signed as 0 through 100",
                    rule_id,
                )
            )
        rearm = rule.get("rearm")
        if not isinstance(rearm, Mapping):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_REARM_POLICY,
                    "rule requires a signed repeated-setup emission and rearm policy",
                    rule_id,
                )
            )
        elif rearm.get("policy") != "once_per_execute_bar":
            blockers.append(
                CompilationBlocker(
                    BlockerCode.UNSUPPORTED_REARM_POLICY,
                    "rearm policy is not implemented by this engine version",
                    rule_id,
                )
            )
        if not _market_data_binding_is_complete(rule.get("market_data")):
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_MARKET_DATA_BINDING,
                    "rule requires a complete signed market-data semantics binding",
                    rule_id,
                )
            )
    if executable_rules and all_rules_have_type:
        required_profiles = {
            (trade_type, setup_type, direction)
            for trade_type in ("Scalp", "Day", "Swing", "Position")
            for setup_type in ("break_and_retest", "swing_failure_pattern")
            for direction in ("long", "short")
        }
        missing = sorted(required_profiles.difference(profiles))
        if missing:
            rendered = ", ".join("/".join(profile) for profile in missing)
            blockers.append(
                CompilationBlocker(
                    BlockerCode.MISSING_PROFILE_COVERAGE,
                    f"missing Trade Type/setup/direction profiles: {rendered}",
                )
            )
    if not executable_rules:
        blockers.append(
            CompilationBlocker(
                BlockerCode.UNSUPPORTED_SHAPE,
                "release contains no executable profiles",
            )
        )
    return tuple(sorted(set(blockers)))


def _executable_rules(release: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rules = release.get("rules")
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        return ()
    return tuple(
        rule
        for rule in rules
        if isinstance(rule, Mapping) and rule.get("kind") == "executable_rule"
    )


def _operands_are_role_bound(predicate: Any) -> bool:
    if not isinstance(predicate, Mapping):
        return False
    operator = predicate.get("op")
    if operator in {"all", "any", "sequence"}:
        items = predicate.get("items")
        return (
            isinstance(items, Sequence)
            and not isinstance(items, (str, bytes))
            and all(_operands_are_role_bound(item) for item in items)
        )
    if operator in {"not", "within_bars", "consecutive"}:
        return _operands_are_role_bound(predicate.get("item"))
    if operator in {"eq", "lt", "lte", "gt", "gte", "crosses_above", "crosses_below"}:
        return _operand_is_role_bound(predicate.get("left")) and _operand_is_role_bound(
            predicate.get("right")
        )
    return False


def _operand_is_role_bound(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    kind = value.get("kind")
    if kind == "constant":
        return True
    return kind in {"bar_field", "prior_value", "derived_feature"} and value.get("role") in {
        "htf",
        "setup",
        "execute",
    }


def _has_feature_implementations(rule: Mapping[str, Any]) -> bool:
    signal = rule.get("signal")
    confidence = signal.get("confidence") if isinstance(signal, Mapping) else None
    features = confidence.get("features") if isinstance(confidence, Mapping) else None
    if not isinstance(features, Sequence) or isinstance(features, (str, bytes)) or not features:
        return False
    for component in features:
        if (
            not isinstance(component, Mapping)
            or not isinstance(component.get("id"), str)
            or not _operands_are_role_bound(component.get("when"))
        ):
            return False
    return not _contains_derived_feature(rule)


def _contains_derived_feature(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("kind") == "derived_feature":
            return True
        return any(_contains_derived_feature(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_derived_feature(item) for item in value)
    return False


def _constants_have_explicit_units(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("kind") == "constant":
            return value.get("unit") in {"ticks", "price_points", "quantity", "scalar"}
        return all(_constants_have_explicit_units(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return all(_constants_have_explicit_units(item) for item in value)
    return True


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _market_data_binding_is_complete(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        isinstance(value.get("profile"), str)
        and bool(value["profile"])
        and isinstance(value.get("source"), str)
        and bool(value["source"])
        and value.get("schema_version") == "market-data/v1"
        and _is_sha256(value.get("calendar_fingerprint"))
        and _is_sha256(value.get("aggregation_fingerprint"))
        and value.get("tick_nanos") == NANOS_PER_TICK
    )


def _compile_profile(rule: Mapping[str, Any]) -> CompiledProfile:
    signal = _mapping(rule.get("signal"), "rule.signal")
    confidence = _mapping(signal.get("confidence"), "rule.signal.confidence")
    trade_type = _required_string(rule.get("trade_type"), "rule.trade_type")
    if trade_type not in {"Scalp", "Day", "Swing", "Position"}:
        raise _UnsupportedShape("rule.trade_type is unsupported")
    typed_trade_type = cast(Literal["Scalp", "Day", "Swing", "Position"], trade_type)
    direction = _required_string(rule.get("direction"), "rule.direction")
    if direction not in {"long", "short"}:
        raise _UnsupportedShape("rule.direction is unsupported")
    typed_direction = cast(Direction, direction)
    orientation = _mapping(signal.get("orientation_guard"), "rule.signal.orientation_guard").get(
        "op"
    )
    if orientation not in {"target_gt_entry_gt_stop", "stop_gt_entry_gt_target"}:
        raise _UnsupportedShape("rule.signal.orientation_guard is unsupported")
    expected_orientation = (
        "target_gt_entry_gt_stop" if typed_direction == "long" else "stop_gt_entry_gt_target"
    )
    if orientation != expected_orientation:
        raise _UnsupportedShape("rule.signal.orientation_guard does not match direction")
    if _mapping(signal.get("r_multiple"), "rule.signal.r_multiple").get("op") != "reward_over_risk":
        raise _UnsupportedShape("rule.signal.r_multiple is unsupported")
    threshold = confidence.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 100:
        raise _UnsupportedShape("rule.signal.confidence.threshold must be an integer from 0 to 100")
    confidence_range = _mapping(confidence.get("range"), "rule.signal.confidence.range")
    confidence_components = _compile_confidence_components(confidence.get("features"))
    if threshold > sum(component.weight for component in confidence_components):
        raise _UnsupportedShape("confidence threshold is unreachable from declared weights")
    rearm_policy = _required_string(
        _mapping(rule.get("rearm"), "rule.rearm").get("policy"), "rearm.policy"
    )
    if rearm_policy != "once_per_execute_bar":
        raise _UnsupportedShape("rearm policy is unsupported by this engine version")
    predicate = _compile_predicate(rule.get("predicate"))
    entry = _compile_operand(signal.get("entry"))
    stop = _compile_operand(signal.get("stop"))
    target = _compile_operand(signal.get("target"))
    _validate_predicate_dimensions(predicate)
    for component in confidence_components:
        _validate_predicate_dimensions(component.predicate)
    for name, operand in (("entry", entry), ("stop", stop), ("target", target)):
        if _operand_dimension(operand) != "ticks":
            raise _UnsupportedShape(f"signal {name} expression must resolve to price ticks")
    return CompiledProfile(
        rule_id=_required_string(rule.get("id"), "rule.id"),
        trade_type=typed_trade_type,
        setup_type=_required_string(rule.get("setup_type"), "rule.setup_type"),
        direction=typed_direction,
        entry_model=_required_string(rule.get("entry_model"), "rule.entry_model"),
        predicate=predicate,
        formula=SignalFormula(
            entry=entry,
            stop=stop,
            target=target,
            orientation_guard=orientation,
            risk_reward_operation="reward_over_risk",
            confidence=CompiledConfidenceFormula(
                confidence_components,
                _bounded_confidence(
                    confidence_range.get("min"), "rule.signal.confidence.range.min"
                ),
                _bounded_confidence(
                    confidence_range.get("max"), "rule.signal.confidence.range.max"
                ),
                threshold,
            ),
        ),
        emission_policy=rearm_policy,
        rearm_policy=rearm_policy,
        market_data_binding=_compile_market_data_binding(rule.get("market_data")),
    )


def _compile_predicate(value: Any) -> Predicate:
    predicate = _mapping(value, "predicate")
    operator = predicate.get("op")
    if operator in {"eq", "lt", "lte", "gt", "gte", "crosses_above", "crosses_below"}:
        return ComparisonPredicate(
            operator,
            _compile_operand(predicate.get("left")),
            _compile_operand(predicate.get("right")),
        )
    if operator in {"all", "any"}:
        return BooleanPredicate(operator, _compile_predicate_items(predicate.get("items")))
    if operator == "not":
        return NotPredicate(_compile_predicate(predicate.get("item")))
    if operator in {"within_bars", "consecutive"}:
        return WindowPredicate(
            operator,
            _bounded_bars(predicate.get("bars")),
            _compile_predicate(predicate.get("item")),
        )
    if operator == "sequence":
        return SequencePredicate(
            _bounded_bars(predicate.get("bars")), _compile_predicate_items(predicate.get("items"))
        )
    raise _UnsupportedShape("predicate operator is unsupported")


def _compile_predicate_items(value: Any) -> tuple[Predicate, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise _UnsupportedShape("predicate items must be a non-empty list")
    return tuple(_compile_predicate(item) for item in value)


def _operand_dimension(operand: Operand) -> ValueDimension:
    if isinstance(operand, ConstantOperand):
        if operand.unit == "price_points":
            raise _UnsupportedShape("price_points must be normalized during compilation")
        return operand.unit
    if isinstance(operand, BarOperand):
        return "quantity" if operand.field == "volume" else "ticks"
    raise _UnsupportedShape("derived feature dimensions are unavailable in this engine version")


def _validate_predicate_dimensions(predicate: Predicate) -> None:
    if isinstance(predicate, ComparisonPredicate):
        left = _operand_dimension(predicate.left)
        right = _operand_dimension(predicate.right)
        if left != right:
            raise _UnsupportedShape(
                f"predicate compares incompatible dimensions: {left} and {right}"
            )
        return
    if isinstance(predicate, BooleanPredicate | SequencePredicate):
        for item in predicate.items:
            _validate_predicate_dimensions(item)
        return
    if isinstance(predicate, NotPredicate | WindowPredicate):
        _validate_predicate_dimensions(predicate.item)
        return
    raise AssertionError("unreachable closed predicate")


def _bounded_bars(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000:
        raise _UnsupportedShape("predicate bars must be an integer from 1 to 1000")
    return value


def _compile_operand(value: Any) -> Operand:
    operand = _mapping(value, "operand")
    kind = operand.get("kind")
    if kind == "constant":
        raw_value = operand.get("value")
        if not isinstance(raw_value, str):
            raise _UnsupportedShape("constant operand value must be a decimal string")
        unit = operand.get("unit")
        if unit not in {"ticks", "price_points", "quantity", "scalar"}:
            raise _UnsupportedShape("constant operand requires an explicit supported unit")
        typed_unit = cast(ConstantUnit, unit)
        try:
            parsed = Decimal(raw_value)
        except InvalidOperation as exc:
            raise _UnsupportedShape("constant operand value must be a decimal string") from exc
        if not parsed.is_finite():
            raise _UnsupportedShape("constant operand value must be finite")
        if typed_unit == "price_points":
            ticks = parsed / Decimal("0.25")
            if ticks != ticks.to_integral_value():
                raise _UnsupportedShape("price_points constant must align to the 0.25-point tick")
            return ConstantOperand(ticks, "ticks")
        if typed_unit in {"ticks", "quantity"} and parsed != parsed.to_integral_value():
            raise _UnsupportedShape(f"{typed_unit} constant must be an integer")
        return ConstantOperand(parsed, typed_unit)
    role = operand.get("role")
    if role not in {"htf", "setup", "execute"}:
        raise _UnsupportedShape("bar and feature operands require an explicit timeframe role")
    offset = operand.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 1_000:
        raise _UnsupportedShape("operand offset must be an integer from 0 to 1000")
    if kind in {"bar_field", "prior_value"}:
        field = operand.get("field")
        if field not in {"open", "high", "low", "close", "volume"}:
            raise _UnsupportedShape("bar operand field is unsupported")
        return BarOperand(role, field, offset)
    if kind == "derived_feature":
        return DerivedFeatureOperand(
            role, _required_string(operand.get("feature"), "operand.feature"), offset
        )
    raise _UnsupportedShape("operand kind is unsupported")


def _compile_market_data_binding(value: Any) -> MarketDataBinding:
    binding = _mapping(value, "rule.market_data")
    if not _market_data_binding_is_complete(binding):
        raise _UnsupportedShape("rule.market_data binding is incomplete")
    return MarketDataBinding(
        profile=_required_string(binding.get("profile"), "market_data.profile"),
        source=_required_string(binding.get("source"), "market_data.source"),
        schema_version=_required_string(
            binding.get("schema_version"), "market_data.schema_version"
        ),
        calendar_fingerprint=cast(str, binding["calendar_fingerprint"]),
        aggregation_fingerprint=cast(str, binding["aggregation_fingerprint"]),
        tick_nanos=cast(int, binding["tick_nanos"]),
    )


def _compile_confidence_components(value: Any) -> tuple[CompiledConfidenceComponent, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise _UnsupportedShape("confidence features must be a non-empty list")
    components: list[CompiledConfidenceComponent] = []
    feature_ids: set[str] = set()
    total_weight = 0
    for component in value:
        mapping = _mapping(component, "confidence feature")
        weight = mapping.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, int) or not 0 <= weight <= 100:
            raise _UnsupportedShape("confidence feature weight must be an integer from 0 to 100")
        feature_id = _required_string(mapping.get("id"), "confidence feature id")
        if feature_id in feature_ids:
            raise _UnsupportedShape("confidence feature ids must be unique")
        feature_ids.add(feature_id)
        total_weight += weight
        if total_weight > 100:
            raise _UnsupportedShape("confidence feature weights must sum to at most 100")
        components.append(
            CompiledConfidenceComponent(
                feature_id,
                weight,
                _compile_predicate(mapping.get("when")),
            )
        )
    return tuple(components)


def _bounded_confidence(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise _UnsupportedShape(f"{name} must be an integer from 0 to 100")
    return value


def _lookback_by_role(profiles: Sequence[CompiledProfile]) -> tuple[tuple[Role, int], ...]:
    lookbacks: dict[Role, int] = {"htf": 0, "setup": 0, "execute": 0}
    for profile in profiles:
        _merge_lookbacks(lookbacks, _predicate_lookbacks(profile.predicate))
        for operand in (profile.formula.entry, profile.formula.stop, profile.formula.target):
            _merge_lookbacks(lookbacks, _operand_lookbacks(operand))
        for component in profile.formula.confidence.components:
            _merge_lookbacks(lookbacks, _predicate_lookbacks(component.predicate))
    if any(offset > MAX_COMPILED_LOOKBACK_OFFSET for offset in lookbacks.values()):
        raise _UnsupportedShape(
            f"combined temporal lookback exceeds {MAX_COMPILED_LOOKBACK_OFFSET} bars"
        )
    return tuple((role, lookbacks[role]) for role in ("htf", "setup", "execute"))


def _merge_lookbacks(target: dict[Role, int], source: Mapping[Role, int]) -> None:
    for role, offset in source.items():
        target[role] = max(target.get(role, 0), offset)


def _operand_lookbacks(operand: Operand, relative_offset: int = 0) -> dict[Role, int]:
    if isinstance(operand, (BarOperand, DerivedFeatureOperand)):
        return {operand.role: operand.offset + relative_offset}
    return {}


def _predicate_lookbacks(predicate: Predicate, relative_offset: int = 0) -> dict[Role, int]:
    lookbacks: dict[Role, int] = {}
    if isinstance(predicate, ComparisonPredicate):
        crossing_offset = 1 if predicate.operator in {"crosses_above", "crosses_below"} else 0
        for operand in (predicate.left, predicate.right):
            _merge_lookbacks(
                lookbacks,
                _operand_lookbacks(operand, relative_offset + crossing_offset),
            )
        return lookbacks
    if isinstance(predicate, BooleanPredicate | SequencePredicate):
        window_offset = predicate.bars - 1 if isinstance(predicate, SequencePredicate) else 0
        for item in predicate.items:
            _merge_lookbacks(
                lookbacks,
                _predicate_lookbacks(item, relative_offset + window_offset),
            )
        return lookbacks
    if isinstance(predicate, NotPredicate):
        return _predicate_lookbacks(predicate.item, relative_offset)
    if isinstance(predicate, WindowPredicate):
        return _predicate_lookbacks(
            predicate.item,
            relative_offset + predicate.bars - 1,
        )
    raise AssertionError("unreachable closed predicate")


def _profile_sort_key(profile: CompiledProfile) -> tuple[str, str, str, str]:
    return (profile.trade_type, profile.setup_type, profile.direction, profile.rule_id)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _UnsupportedShape(f"{name} must be a mapping")
    return value


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise _UnsupportedShape(f"{name} must be a non-empty string")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


class _UnsupportedShape(ValueError):
    pass


def _strategy_neutral_test_program() -> StrategyProgram:
    """Return a private mechanical fixture, never a production strategy rule."""
    market_data = MarketDataBinding(
        profile="test_market_data",
        source="market-test",
        schema_version="market-data/v1",
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="a" * 64,
        tick_nanos=NANOS_PER_TICK,
    )
    long_formula = SignalFormula(
        ConstantOperand(Decimal("2")),
        ConstantOperand(Decimal("1")),
        ConstantOperand(Decimal("3")),
        "target_gt_entry_gt_stop",
        "reward_over_risk",
        CompiledConfidenceFormula(
            (
                CompiledConfidenceComponent(
                    "test_signal_quality",
                    50,
                    ComparisonPredicate(
                        "gt",
                        BarOperand("execute", "close", 0),
                        ConstantOperand(Decimal("0")),
                    ),
                ),
            ),
            0,
            100,
            50,
        ),
    )
    short_formula = SignalFormula(
        ConstantOperand(Decimal("2")),
        ConstantOperand(Decimal("3")),
        ConstantOperand(Decimal("1")),
        "stop_gt_entry_gt_target",
        "reward_over_risk",
        CompiledConfidenceFormula(
            (
                CompiledConfidenceComponent(
                    "test_signal_quality",
                    50,
                    ComparisonPredicate(
                        "gt",
                        BarOperand("execute", "close", 0),
                        ConstantOperand(Decimal("0")),
                    ),
                ),
            ),
            0,
            100,
            50,
        ),
    )
    predicate = ComparisonPredicate(
        "gt",
        BarOperand("execute", "close", 0),
        ConstantOperand(Decimal("0")),
    )
    profiles = (
        CompiledProfile(
            "test-long",
            "Scalp",
            "test_setup",
            "long",
            "test_entry",
            predicate,
            long_formula,
            "once_per_execute_bar",
            "once_per_execute_bar",
            market_data,
        ),
        CompiledProfile(
            "test-short",
            "Scalp",
            "test_setup",
            "short",
            "test_entry",
            predicate,
            short_formula,
            "once_per_execute_bar",
            "once_per_execute_bar",
            market_data,
        ),
    )
    return StrategyProgram("0" * 64, "test", "test", profiles, _lookback_by_role(profiles))


__all__ = [
    "BarOperand",
    "BlockerCode",
    "BooleanPredicate",
    "ComparisonPredicate",
    "CompilationBlocker",
    "CompilationReadiness",
    "CompiledConfidenceComponent",
    "CompiledConfidenceFormula",
    "CompiledProfile",
    "CompiledRuleSet",
    "ConstantOperand",
    "DerivedFeatureOperand",
    "MarketDataBinding",
    "NotPredicate",
    "ProductionCompilation",
    "SequencePredicate",
    "SignalFormula",
    "StrategyProgram",
    "WindowPredicate",
    "compile_production_release",
    "production_readiness",
]
