"""Fail-closed validation and publication for strategy rulebooks.

This module deliberately contains no market-data, network, model, or execution
integration.  It only moves human-reviewed strategy knowledge from strict YAML
to a reproducible JSON release.
"""

from __future__ import annotations

import json
import re
from base64 import b64decode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any, Never

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SCHEMA_MAJOR = 1
COMPILER_VERSION = "1.0.0"
MAX_LOOKBACK_BARS = 1_000
EXPECTED_TIMEFRAME_MAPS: dict[str, dict[str, str]] = {
    "Scalp": {"htf": "15m", "setup": "5m", "execute": "1m", "manage": "5m"},
    "Day": {"htf": "60m", "setup": "5m", "execute": "1m", "manage": "5m"},
    "Swing": {"htf": "1d", "setup": "60m", "execute": "15m", "manage": "60m"},
    "Position": {"htf": "1w", "setup": "1d", "execute": "60m", "manage": "1d"},
}
ALLOWED_OPERATORS = frozenset(
    {
        "eq",
        "lt",
        "lte",
        "gt",
        "gte",
        "crosses_above",
        "crosses_below",
        "all",
        "any",
        "not",
        "within_bars",
        "sequence",
        "consecutive",
    }
)
COMPARISON_OPERATORS = frozenset({"eq", "lt", "lte", "gt", "gte", "crosses_above", "crosses_below"})
ALLOWED_OPERANDS = frozenset({"bar_field", "derived_feature", "constant", "prior_value"})
ALLOWED_BAR_FIELDS = frozenset({"open", "high", "low", "close", "volume"})
PRICE_BAR_FIELDS = frozenset({"open", "high", "low", "close"})
ALLOWED_SETUP_TYPES = frozenset({"break_and_retest", "swing_failure_pattern"})
ALLOWED_SOURCE_KINDS = frozenset({"media", "pdf"})
AMBIGUOUS_SCALAR_RE = re.compile(r"^(?:yes|no|on|off|true|false|null|~)$", re.IGNORECASE)
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SEMVER_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[0-9A-Za-z-]+)(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]+))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_DERIVED_FEATURES = frozenset(
    {
        "PDH",
        "PDL",
        "PDC",
        "HCOM",
        "LCOM",
        "SMA20",
        "SMA200",
        "previous_daily_high",
        "previous_daily_low",
        "previous_daily_close",
        "highest_close_of_month",
        "lowest_close_of_month",
        "sma_20",
        "sma_200",
    }
)
ALLOWED_CONFLUENCE_FEATURES = frozenset(
    {
        "higher_timeframe_alignment",
        "prior_day_level",
        "session_context",
        "setup_quality",
        "entry_model_alignment",
        "trapped_trader_context",
        "fib_geometry",
        "sma_context",
        "chop_zone",
    }
)
ALLOWED_ENTRY_MODELS = frozenset({"sbs_model_1", "sbs_model_2"})
APPROVAL_DOMAIN = "stoic-derived/rulebook-approval/v1"


class RulebookError(ValueError):
    """Raised when an authoring rulebook violates the publication contract."""


class PublicationError(RulebookError):
    """Raised when an otherwise valid candidate cannot become a live release."""


@dataclass(frozen=True, slots=True)
class Rulebook:
    """Validated authoring data and immutable identity of its YAML source."""

    path: Path
    data: dict[str, Any]
    source_yaml_sha256: str


@dataclass(frozen=True, slots=True)
class Readiness:
    """Publication decision with human-readable, deterministic blockers."""

    ready: bool
    blockers: tuple[str, ...]


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise RulebookError(f"duplicate YAML mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _fail(message: str) -> Never:
    raise RulebookError(message)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _expect_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail(f"{name} must be a mapping with string keys")
    return value


def _expect_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{name} must be a list")
    return value


def _expect_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be a non-empty string")
    if AMBIGUOUS_SCALAR_RE.fullmatch(value):
        _fail(f"{name} uses an ambiguous YAML scalar form")
    return value


def _reject_unknown_keys(value: Mapping[str, Any], allowed: frozenset[str], name: str) -> None:
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        _fail(f"{name} contains unsupported field(s): {', '.join(unknown)}")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulebookError(f"cannot read rulebook: {path}") from exc
    try:
        loaded = yaml.load(raw, Loader=_StrictLoader)
    except (yaml.YAMLError, RulebookError) as exc:
        if isinstance(exc, RulebookError):
            raise
        raise RulebookError(f"invalid YAML: {exc}") from exc
    return _expect_mapping(loaded, "rulebook")


def _validate_schema_version(value: Any) -> None:
    version = _expect_string(value, "schema_version")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise RulebookError("schema_version must begin with a numeric major") from exc
    if major != SCHEMA_MAJOR:
        _fail(f"unsupported schema major: {major}")


def _validate_semver(value: Any, name: str, *, allow_prerelease: bool) -> str:
    version = _expect_string(value, name)
    if not SEMVER_RE.fullmatch(version):
        _fail(f"{name} must be a valid semantic version")
    if not allow_prerelease and "-" in version.split("+", 1)[0]:
        _fail(f"{name} must not be a prerelease version")
    return version


def _validate_scope(value: Any) -> None:
    scope = _expect_mapping(value, "scope")
    _reject_unknown_keys(scope, frozenset({"instruments", "timeframe_maps"}), "scope")
    instruments = _expect_list(scope.get("instruments"), "scope.instruments")
    if instruments != ["NQ", "ES"]:
        _fail("scope.instruments must be exactly [NQ, ES]")
    timeframe_maps = _expect_mapping(scope.get("timeframe_maps"), "scope.timeframe_maps")
    if timeframe_maps != EXPECTED_TIMEFRAME_MAPS:
        _fail("scope.timeframe_maps must exactly match fixed Vision timeframe maps")


def _repository_root(rulebook_path: Path) -> Path:
    """Find the checkout root, while retaining ergonomic temporary fixtures."""
    for ancestor in (rulebook_path.parent, *rulebook_path.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return rulebook_path.parent


def _safe_local_path(rulebook_path: Path, raw_path: Any, name: str) -> Path:
    text = _expect_string(raw_path, name)
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts:
        _fail(f"{name} must be a repository-relative path")
    return _repository_root(rulebook_path) / candidate


def _validate_digest(path: Path, expected: Any, name: str) -> None:
    digest = _validate_sha256_digest(expected, name)
    try:
        actual = _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise RulebookError(f"{name} source file is missing: {path}") from exc
    if actual != digest:
        _fail(f"{name} does not match source digest")


def _validate_sha256_digest(value: Any, name: str) -> str:
    digest = _expect_string(value, name)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail(f"{name} must be a lower-case SHA-256 digest")
    return digest


def _approval_message_fields(approval: Mapping[str, Any]) -> bytes:
    return (
        APPROVAL_DOMAIN.encode("ascii")
        + b"\0"
        + _canonical_json(
            {
                "approved_at": approval["approved_at"],
                "candidate_sha256": approval["candidate_sha256"],
                "public_key_fingerprint": approval["public_key_fingerprint"],
                "reviewer_email": approval["reviewer_email"],
            }
        )
    )


def _validate_approval(
    value: Any, candidate_sha256: str | None = None, *, require_signature: bool = True
) -> dict[str, Any]:
    approval = _expect_mapping(value, "approval")
    _reject_unknown_keys(
        approval,
        frozenset(
            {
                "reviewer_email",
                "approved_at",
                "candidate_sha256",
                "public_key_fingerprint",
                "signature_base64",
            }
        ),
        "approval",
    )
    reviewer_email = _expect_string(approval.get("reviewer_email"), "approval.reviewer_email")
    if not EMAIL_RE.fullmatch(reviewer_email):
        _fail("approval.reviewer_email must be a valid email address")
    approved_at = _expect_string(approval.get("approved_at"), "approval.approved_at")
    if not RFC3339_UTC_RE.fullmatch(approved_at):
        _fail("approval.approved_at must be an RFC3339 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(approved_at)
    except ValueError as exc:
        raise RulebookError("approval.approved_at must be a valid RFC3339 UTC timestamp") from exc
    digest = _validate_sha256_digest(approval.get("candidate_sha256"), "approval.candidate_sha256")
    if candidate_sha256 is not None and digest != candidate_sha256:
        _fail("approval.candidate_sha256 does not match candidate_sha256")
    _validate_sha256_digest(
        approval.get("public_key_fingerprint"), "approval.public_key_fingerprint"
    )
    signature = approval.get("signature_base64")
    if require_signature:
        signature_text = _expect_string(signature, "approval.signature_base64")
        try:
            decoded_signature = b64decode(signature_text, validate=True)
        except ValueError as exc:
            raise RulebookError("approval.signature_base64 must be valid base64") from exc
        if len(decoded_signature) != 64:
            _fail("approval.signature_base64 must contain an Ed25519 signature")
    return approval


def _coerce_public_key(value: Ed25519PublicKey | bytes | None) -> Ed25519PublicKey:
    if value is None:
        raise PublicationError("a separately pinned Ed25519 public key is required")
    if isinstance(value, Ed25519PublicKey):
        return value
    if not isinstance(value, bytes):
        raise PublicationError("pinned public key must be Ed25519 raw bytes or Ed25519PublicKey")
    try:
        return Ed25519PublicKey.from_public_bytes(value)
    except ValueError as exc:
        raise PublicationError("pinned public key is not a valid Ed25519 raw public key") from exc


def _public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _sha256_bytes(raw)


def _verify_approval(
    approval_value: Any, candidate_sha256: str, public_key_value: Ed25519PublicKey | bytes | None
) -> None:
    approval = _validate_approval(approval_value, candidate_sha256)
    public_key = _coerce_public_key(public_key_value)
    if approval["public_key_fingerprint"] != _public_key_fingerprint(public_key):
        _fail("approval.public_key_fingerprint does not match the pinned public key")
    try:
        public_key.verify(
            b64decode(approval["signature_base64"], validate=True),
            _approval_message_fields(approval),
        )
    except InvalidSignature as exc:
        raise PublicationError("approval signature verification failed") from exc


def approval_message(
    *, reviewer_email: str, approved_at: str, candidate_sha256: str, public_key_fingerprint: str
) -> bytes:
    """Build the domain-separated bytes a human approval key must sign."""
    approval = _validate_approval(
        {
            "reviewer_email": reviewer_email,
            "approved_at": approved_at,
            "candidate_sha256": candidate_sha256,
            "public_key_fingerprint": public_key_fingerprint,
        },
        candidate_sha256,
        require_signature=False,
    )
    return _approval_message_fields(approval)


def _validate_evidence(value: Any, rulebook_path: Path, *, verify_sources: bool) -> set[str]:
    evidence = _expect_list(value, "evidence")
    ids: set[str] = set()
    for index, record_value in enumerate(evidence):
        record = _expect_mapping(record_value, f"evidence[{index}]")
        _reject_unknown_keys(
            record,
            frozenset(
                {
                    "id",
                    "source_kind",
                    "asset_path",
                    "asset_sha256",
                    "transcript_path",
                    "transcript_sha256",
                    "locator",
                    "claim",
                }
            ),
            f"evidence[{index}]",
        )
        evidence_id = _expect_string(record.get("id"), f"evidence[{index}].id")
        if evidence_id in ids:
            _fail(f"duplicate evidence id: {evidence_id}")
        ids.add(evidence_id)
        if record.get("source_kind") not in ALLOWED_SOURCE_KINDS:
            _fail(f"evidence[{index}].source_kind must be media or pdf")
        asset = _safe_local_path(
            rulebook_path, record.get("asset_path"), f"evidence[{index}].asset_path"
        )
        if verify_sources:
            _validate_digest(asset, record.get("asset_sha256"), f"evidence[{index}].asset_sha256")
        elif not re.fullmatch(
            r"[0-9a-f]{64}",
            _expect_string(record.get("asset_sha256"), f"evidence[{index}].asset_sha256"),
        ):
            _fail(f"evidence[{index}].asset_sha256 must be a lower-case SHA-256 digest")
        locator = _expect_mapping(record.get("locator"), f"evidence[{index}].locator")
        if record["source_kind"] == "media":
            _reject_unknown_keys(locator, frozenset({"start", "end"}), f"evidence[{index}].locator")
            start = _expect_string(locator.get("start"), f"evidence[{index}].locator.start")
            end = _expect_string(locator.get("end"), f"evidence[{index}].locator.end")
            if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", start) or not re.fullmatch(
                r"\d{2}:\d{2}:\d{2}", end
            ):
                _fail(f"evidence[{index}].locator media times must use HH:MM:SS")
            start_parts = tuple(int(part) for part in start.split(":"))
            end_parts = tuple(int(part) for part in end.split(":"))
            if (
                start_parts[0] > 23
                or end_parts[0] > 23
                or start_parts[1] > 59
                or end_parts[1] > 59
                or start_parts[2] > 59
                or end_parts[2] > 59
            ):
                _fail(f"evidence[{index}].locator media times must be valid HH:MM:SS values")
            if start_parts > end_parts:
                _fail(f"evidence[{index}].locator.start must be before or equal to end")
        else:
            _reject_unknown_keys(locator, frozenset({"page"}), f"evidence[{index}].locator")
            page = locator.get("page")
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                _fail(f"evidence[{index}].locator.page must be a positive integer")
        _expect_string(record.get("claim"), f"evidence[{index}].claim")
        transcript_path = record.get("transcript_path")
        transcript_digest = record.get("transcript_sha256")
        if (transcript_path is None) != (transcript_digest is None):
            _fail(f"evidence[{index}] transcript_path and transcript_sha256 must appear together")
        if record["source_kind"] == "media" and transcript_path is None:
            _fail(
                f"evidence[{index}] media evidence requires transcript_path and transcript_sha256"
            )
        if transcript_path is not None:
            transcript = _safe_local_path(
                rulebook_path, transcript_path, f"evidence[{index}].transcript_path"
            )
            if verify_sources:
                _validate_digest(
                    transcript, transcript_digest, f"evidence[{index}].transcript_sha256"
                )
            elif not re.fullmatch(
                r"[0-9a-f]{64}",
                _expect_string(transcript_digest, f"evidence[{index}].transcript_sha256"),
            ):
                _fail(f"evidence[{index}].transcript_sha256 must be a lower-case SHA-256 digest")
    return ids


def _validate_operand(value: Any, name: str) -> None:
    operand = _expect_mapping(value, name)
    kind = operand.get("kind")
    if kind not in ALLOWED_OPERANDS:
        _fail(f"{name} has unsupported operand kind")
    if kind in {"bar_field", "prior_value"}:
        _reject_unknown_keys(operand, frozenset({"kind", "field", "offset"}), name)
        field = operand.get("field")
        if field not in ALLOWED_BAR_FIELDS:
            _fail(f"{name}.field is unsupported")
        offset = operand.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool):
            _fail(f"{name}.offset must be an integer")
        if kind == "bar_field" and offset != 0:
            _fail(f"{name}.offset is a lookahead; bar fields must use closed bar offset 0")
        if kind == "prior_value" and not 1 <= offset <= MAX_LOOKBACK_BARS:
            _fail(f"{name}.offset must be a bounded prior-bar reference")
    elif kind == "derived_feature":
        _reject_unknown_keys(operand, frozenset({"kind", "name", "offset"}), name)
        feature_name = _expect_string(operand.get("name"), f"{name}.name")
        if feature_name not in ALLOWED_DERIVED_FEATURES:
            _fail(f"{name}.name is not an allowlisted deterministic derived feature")
        if operand.get("offset", 0) != 0:
            _fail(f"{name}.offset is a lookahead")
    else:
        _reject_unknown_keys(operand, frozenset({"kind", "value"}), name)
        constant = operand.get("value")
        if not isinstance(constant, str):
            _fail(f"{name}.value must be a decimal string, not binary float")
        try:
            decimal_value = Decimal(constant)
        except InvalidOperation as exc:
            raise RulebookError(f"{name}.value must be a decimal string") from exc
        if not decimal_value.is_finite():
            _fail(f"{name}.value must be a finite decimal")


def _validate_predicate(value: Any, name: str) -> None:
    predicate = _expect_mapping(value, name)
    op = predicate.get("op")
    if op not in ALLOWED_OPERATORS:
        _fail(f"{name} has unsupported operator: {op!r}")
    if op in COMPARISON_OPERATORS:
        _reject_unknown_keys(predicate, frozenset({"op", "left", "right"}), name)
        _validate_operand(predicate.get("left"), f"{name}.left")
        _validate_operand(predicate.get("right"), f"{name}.right")
    elif op in {"all", "any"}:
        _reject_unknown_keys(predicate, frozenset({"op", "items"}), name)
        items = _expect_list(predicate.get("items"), f"{name}.items")
        if not items:
            _fail(f"{name}.items must not be empty")
        for index, item in enumerate(items):
            _validate_predicate(item, f"{name}.items[{index}]")
    elif op == "not":
        _reject_unknown_keys(predicate, frozenset({"op", "item"}), name)
        _validate_predicate(predicate.get("item"), f"{name}.item")
    elif op in {"within_bars", "consecutive"}:
        _reject_unknown_keys(predicate, frozenset({"op", "bars", "item"}), name)
        bars = predicate.get("bars")
        if (
            not isinstance(bars, int)
            or isinstance(bars, bool)
            or not 1 <= bars <= MAX_LOOKBACK_BARS
        ):
            _fail(f"{name}.bars must be a positive bounded integer")
        _validate_predicate(predicate.get("item"), f"{name}.item")
    else:
        _reject_unknown_keys(predicate, frozenset({"op", "bars", "items"}), name)
        bars = predicate.get("bars")
        if (
            not isinstance(bars, int)
            or isinstance(bars, bool)
            or not 1 <= bars <= MAX_LOOKBACK_BARS
        ):
            _fail(f"{name}.bars must be a positive bounded integer")
        items = _expect_list(predicate.get("items"), f"{name}.items")
        if not items:
            _fail(f"{name}.items must not be empty")
        for index, item in enumerate(items):
            _validate_predicate(item, f"{name}.items[{index}]")


def _constant_operand_value(value: Any) -> Decimal | None:
    if isinstance(value, dict) and value.get("kind") == "constant":
        return Decimal(value["value"])
    return None


def _validate_price_operand(value: Any, name: str) -> None:
    """Validate price expressions without rounding constants; SP1 supplies tick-aligned bars."""
    _validate_operand(value, name)
    operand = _expect_mapping(value, name)
    kind = operand["kind"]
    if kind in {"bar_field", "prior_value"} and operand["field"] not in PRICE_BAR_FIELDS:
        _fail(f"{name}.field must be an OHLC price field; volume is not a price operand")
    constant = _constant_operand_value(operand)
    if constant is not None:
        if constant <= 0:
            _fail(f"{name} constant must be a positive NQ/ES price")
        if constant % Decimal("0.25") != 0:
            _fail(
                f"{name} constant must align exactly to the 0.25 NQ/ES tick; no rounding is applied"
            )


def _validate_confidence(value: Any, name: str) -> None:
    confidence = _expect_mapping(value, name)
    _reject_unknown_keys(confidence, frozenset({"op", "features", "range"}), name)
    if confidence.get("op") != "weighted_sum":
        _fail(f"{name}.op must be weighted_sum")
    features = _expect_list(confidence.get("features"), f"{name}.features")
    if not features:
        _fail(f"{name}.features must not be empty")
    feature_ids: set[str] = set()
    for index, feature_value in enumerate(features):
        feature = _expect_mapping(feature_value, f"{name}.features[{index}]")
        _reject_unknown_keys(feature, frozenset({"id", "weight"}), f"{name}.features[{index}]")
        feature_id = _expect_string(feature.get("id"), f"{name}.features[{index}].id")
        if feature_id not in ALLOWED_CONFLUENCE_FEATURES:
            _fail(f"{name}.features[{index}].id is not an allowlisted confluence feature")
        if feature_id in feature_ids:
            _fail(f"{name}.features contains duplicate feature id: {feature_id}")
        feature_ids.add(feature_id)
        weight = feature.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or not -100 <= weight <= 100:
            _fail(f"{name}.features[{index}].weight must be an integer from -100 to 100")
    score_range = _expect_mapping(confidence.get("range"), f"{name}.range")
    _reject_unknown_keys(score_range, frozenset({"min", "max"}), f"{name}.range")
    minimum, maximum = score_range.get("min"), score_range.get("max")
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or not -10_000 <= minimum < maximum <= 10_000
    ):
        _fail(f"{name}.range must contain bounded integer min and max")


def _validate_signal(value: Any, name: str, direction: str) -> None:
    signal = _expect_mapping(value, name)
    _reject_unknown_keys(
        signal,
        frozenset({"entry", "stop", "target", "orientation_guard", "r_multiple", "confidence"}),
        name,
    )
    operands = {field: signal.get(field) for field in ("entry", "stop", "target")}
    for field, operand in operands.items():
        _validate_price_operand(operand, f"{name}.{field}")
    orientation_guard = _expect_mapping(
        signal.get("orientation_guard"), f"{name}.orientation_guard"
    )
    _reject_unknown_keys(orientation_guard, frozenset({"op"}), f"{name}.orientation_guard")
    expected_guard = "target_gt_entry_gt_stop" if direction == "long" else "stop_gt_entry_gt_target"
    if orientation_guard.get("op") != expected_guard:
        _fail(f"{name}.orientation_guard must be {expected_guard}")
    r_multiple = _expect_mapping(signal.get("r_multiple"), f"{name}.r_multiple")
    _reject_unknown_keys(r_multiple, frozenset({"op"}), f"{name}.r_multiple")
    if r_multiple.get("op") != "reward_over_risk":
        _fail(f"{name}.r_multiple.op must be reward_over_risk")
    _validate_confidence(signal.get("confidence"), f"{name}.confidence")
    entry, stop, target = (
        _constant_operand_value(operands[field]) for field in ("entry", "stop", "target")
    )
    if entry is not None and stop is not None and target is not None:
        if direction == "long" and not target > entry > stop:
            _fail(f"{name} long profile must satisfy target > entry > stop")
        if direction == "short" and not stop > entry > target:
            _fail(f"{name} short profile must satisfy stop > entry > target")


def _validate_rules(value: Any, evidence_ids: set[str]) -> list[dict[str, Any]]:
    rules = _expect_list(value, "rules")
    rule_ids: set[str] = set()
    validated_rules: list[dict[str, Any]] = []
    for index, rule_value in enumerate(rules):
        rule = _expect_mapping(rule_value, f"rules[{index}]")
        _reject_unknown_keys(
            rule,
            frozenset(
                {
                    "id",
                    "kind",
                    "capability",
                    "status",
                    "claim",
                    "evidence_ids",
                    "setup_type",
                    "direction",
                    "entry_model",
                    "predicate",
                    "signal",
                }
            ),
            f"rules[{index}]",
        )
        rule_id = _expect_string(rule.get("id"), f"rules[{index}].id")
        if rule_id in rule_ids:
            _fail(f"duplicate rule id: {rule_id}")
        rule_ids.add(rule_id)
        kind = rule.get("kind")
        if kind not in {"qualitative_claim", "executable_rule"}:
            _fail(f"rules[{index}].kind must be qualitative_claim or executable_rule")
        _expect_string(rule.get("capability"), f"rules[{index}].capability")
        if rule.get("status") not in {"candidate", "unknown", "validated"}:
            _fail(f"rules[{index}].status must be candidate, unknown, or validated")
        _expect_string(rule.get("claim"), f"rules[{index}].claim")
        references = _expect_list(rule.get("evidence_ids"), f"rules[{index}].evidence_ids")
        if not references:
            _fail(f"rules[{index}] must cite primary evidence")
        if any(
            not isinstance(reference, str) or reference not in evidence_ids
            for reference in references
        ):
            _fail(f"rules[{index}] references unknown evidence")
        setup_type = rule.get("setup_type")
        if setup_type is not None and setup_type not in ALLOWED_SETUP_TYPES:
            _fail(f"rules[{index}].setup_type must be break_and_retest or swing_failure_pattern")
        direction = rule.get("direction")
        if direction is not None and direction not in {"long", "short"}:
            _fail(f"rules[{index}].direction must be long or short")
        entry_model = rule.get("entry_model")
        if entry_model is not None and (
            not isinstance(entry_model, str) or entry_model not in ALLOWED_ENTRY_MODELS
        ):
            _fail(f"rules[{index}].entry_model must be sbs_model_1 or sbs_model_2")
        if "predicate" in rule:
            _validate_predicate(rule["predicate"], f"rules[{index}].predicate")
        if kind == "qualitative_claim" and ("predicate" in rule or "signal" in rule):
            _fail(f"rules[{index}] qualitative claim cannot contain live executable fields")
        if (
            kind == "executable_rule"
            and rule["status"] == "validated"
            and (
                "predicate" not in rule
                or "signal" not in rule
                or setup_type is None
                or direction is None
                or entry_model is None
            )
        ):
            _fail(
                f"rules[{index}] validated rule needs setup, direction, entry_model, "
                "predicate, and signal"
            )
        if kind == "executable_rule" and rule["status"] == "validated":
            _validate_signal(
                rule["signal"],
                f"rules[{index}].signal",
                _expect_string(direction, f"rules[{index}].direction"),
            )
        validated_rules.append(rule)
    return validated_rules


def _validate_examples(value: Any, rulebook_path: Path, *, verify_sources: bool) -> None:
    examples = _expect_list(value, "examples")
    ids: set[str] = set()
    for index, example_value in enumerate(examples):
        example = _expect_mapping(example_value, f"examples[{index}]")
        _reject_unknown_keys(
            example,
            frozenset(
                {
                    "id",
                    "evidence_role",
                    "asset_path",
                    "page",
                    "asset_sha256",
                    "label",
                    "claim",
                    "non_executable_statement",
                }
            ),
            f"examples[{index}]",
        )
        example_id = _expect_string(example.get("id"), f"examples[{index}].id")
        if example_id in ids:
            _fail(f"duplicate example id: {example_id}")
        ids.add(example_id)
        if example.get("evidence_role") != "illustrative_only":
            _fail(f"examples[{index}].evidence_role must be illustrative_only")
        asset = _safe_local_path(
            rulebook_path, example.get("asset_path"), f"examples[{index}].asset_path"
        )
        if verify_sources:
            _validate_digest(asset, example.get("asset_sha256"), f"examples[{index}].asset_sha256")
        elif not re.fullmatch(
            r"[0-9a-f]{64}",
            _expect_string(example.get("asset_sha256"), f"examples[{index}].asset_sha256"),
        ):
            _fail(f"examples[{index}].asset_sha256 must be a lower-case SHA-256 digest")
        page = example.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            _fail(f"examples[{index}].page must be a positive integer")
        for field in ("label", "claim", "non_executable_statement"):
            _expect_string(example.get(field), f"examples[{index}].{field}")


def _validate_glossary(value: Any, evidence_ids: set[str]) -> None:
    glossary = _expect_list(value, "glossary")
    terms: set[str] = set()
    for index, entry_value in enumerate(glossary):
        entry = _expect_mapping(entry_value, f"glossary[{index}]")
        _reject_unknown_keys(
            entry, frozenset({"term", "meaning", "evidence_ids"}), f"glossary[{index}]"
        )
        term = _expect_string(entry.get("term"), f"glossary[{index}].term")
        if term in terms:
            _fail(f"duplicate glossary term: {term}")
        terms.add(term)
        _expect_string(entry.get("meaning"), f"glossary[{index}].meaning")
        references = _expect_list(entry.get("evidence_ids"), f"glossary[{index}].evidence_ids")
        if not references or any(
            not isinstance(reference, str) or reference not in evidence_ids
            for reference in references
        ):
            _fail(f"glossary[{index}] references unknown evidence")


def _validate_research_items(
    value: Any, name: str, description_key: str, evidence_ids: set[str]
) -> None:
    items = _expect_list(value, name)
    ids: set[str] = set()
    for index, item_value in enumerate(items):
        item = _expect_mapping(item_value, f"{name}[{index}]")
        allowed = frozenset({"id", description_key, "evidence_ids", "resolution"})
        _reject_unknown_keys(item, allowed, f"{name}[{index}]")
        item_id = _expect_string(item.get("id"), f"{name}[{index}].id")
        if item_id in ids:
            _fail(f"duplicate {name} id: {item_id}")
        ids.add(item_id)
        _expect_string(item.get(description_key), f"{name}[{index}].{description_key}")
        references = _expect_list(item.get("evidence_ids", []), f"{name}[{index}].evidence_ids")
        if not references or any(
            not isinstance(reference, str) or reference not in evidence_ids
            for reference in references
        ):
            _fail(f"{name}[{index}] references unknown evidence")


def _validate_no_forbidden_dependencies(value: Mapping[str, Any]) -> None:
    forbidden = {
        "backtest",
        "backtesting",
        "walk_forward",
        "model_dependency",
        "model",
        "llm",
        "slm",
        "vlm",
        "prompt",
        "action",
        "broker",
        "execution",
    }

    def walk(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key.lower() in forbidden:
                    _fail(f"{path}.{key} is forbidden in a live rulebook")
                walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")

    walk(value, "rulebook")


def _validate_rulebook(data: dict[str, Any], path: Path, *, verify_sources: bool) -> None:
    _reject_unknown_keys(
        data,
        frozenset(
            {
                "schema_version",
                "rulebook_version",
                "scope",
                "evidence",
                "glossary",
                "examples",
                "rules",
                "unresolved_decisions",
                "conflicts",
                "approval",
            }
        ),
        "rulebook",
    )
    _validate_schema_version(data.get("schema_version"))
    _validate_semver(data.get("rulebook_version"), "rulebook_version", allow_prerelease=True)
    _validate_scope(data.get("scope"))
    evidence_ids = _validate_evidence(data.get("evidence"), path, verify_sources=verify_sources)
    _validate_glossary(data.get("glossary", []), evidence_ids)
    _validate_examples(data.get("examples", []), path, verify_sources=verify_sources)
    _validate_rules(data.get("rules"), evidence_ids)
    _validate_research_items(
        data.get("unresolved_decisions", []), "unresolved_decisions", "question", evidence_ids
    )
    _validate_research_items(data.get("conflicts", []), "conflicts", "description", evidence_ids)
    approval = data.get("approval")
    if approval is not None:
        _validate_approval(approval)
    _validate_no_forbidden_dependencies(data)


def load_rulebook(path: Path | str, *, verify_sources: bool = False) -> Rulebook:
    """Load strict YAML; source verification stays opt-in for Drive-backed media."""
    rulebook_path = Path(path)
    data = _load_yaml(rulebook_path)
    _validate_rulebook(data, rulebook_path, verify_sources=verify_sources)
    return Rulebook(
        path=rulebook_path,
        data=data,
        source_yaml_sha256=_sha256_bytes(rulebook_path.read_bytes()),
    )


def candidate_digest(rulebook: Rulebook) -> str:
    """Content address of semantic authoring data, excluding human approval."""
    payload = {key: value for key, value in rulebook.data.items() if key != "approval"}
    return _sha256_bytes(_canonical_json(payload))


def readiness(rulebook: Rulebook, *, check_approval: bool = True) -> Readiness:
    """Report whether the candidate meets every deterministic publication gate."""
    blockers: list[str] = []
    rules = rulebook.data["rules"]
    executable_rules = [rule for rule in rules if rule["kind"] == "executable_rule"]
    required_profiles = {
        (setup_type, direction)
        for setup_type in ALLOWED_SETUP_TYPES
        for direction in ("long", "short")
    }
    validated_profiles = {
        (rule.get("setup_type"), rule.get("direction"))
        for rule in executable_rules
        if rule["status"] == "validated"
    }
    for setup_type, direction in sorted(required_profiles.difference(validated_profiles)):
        blockers.append(f"live-required profile is not validated: {setup_type}/{direction}")
    for rule in executable_rules:
        if rule["status"] != "validated":
            blockers.append(f"rule {rule['id']} is {rule['status']}")
    for decision in rulebook.data.get("unresolved_decisions", []):
        blockers.append(f"unresolved decision: {decision['id']}")
    for conflict in rulebook.data.get("conflicts", []):
        blockers.append(f"unresolved source conflict: {conflict['id']}")
    if check_approval:
        approval = rulebook.data.get("approval")
        if approval is None:
            blockers.append("human approval envelope is missing")
        elif approval.get("candidate_sha256") != candidate_digest(rulebook):
            blockers.append("human approval envelope has a stale candidate digest")
    return Readiness(ready=not blockers, blockers=tuple(sorted(blockers)))


def _markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_dossier(rulebook: Rulebook) -> str:
    """Generate a stable review-only Markdown projection from authoring YAML."""
    state = readiness(rulebook)
    readiness_headline = "PENDING PINNED-KEY VERIFICATION" if state.ready else "BLOCKED"
    scope = rulebook.data["scope"]
    lines = [
        "# Strategy Rulebook Review Dossier",
        "",
        f"- Rulebook version: `{rulebook.data['rulebook_version']}`",
        f"- Candidate digest: `{candidate_digest(rulebook)}`",
        f"- **Publication readiness: {readiness_headline}**",
        "",
        "## Fixed Scope and Guardrails",
        "",
        f"- Runtime instruments: `{', '.join(scope['instruments'])}`",
        "- Signals only; no broker or execution actions.",
        "- No model, prompt, network, or backtest dependency can enter a release.",
        "",
        "## Timeframe Maps",
        "",
        "| Type | HTF | Setup | Execute | Manage |",
        "|---|---|---|---|---|",
    ]
    for trade_type, mapping in EXPECTED_TIMEFRAME_MAPS.items():
        timeframe_cells = (
            trade_type,
            mapping["htf"],
            mapping["setup"],
            mapping["execute"],
            mapping["manage"],
        )
        lines.append("| " + " | ".join(timeframe_cells) + " |")
    lines.extend(
        [
            "",
            "## Evidence Matrix",
            "",
            "| ID | Kind | Asset | Asset SHA-256 | Transcript | Transcript SHA-256 | "
            "Locator | Claim |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for evidence in sorted(rulebook.data["evidence"], key=lambda item: item["id"]):
        locator = ", ".join(f"{key}={value}" for key, value in sorted(evidence["locator"].items()))
        evidence_cells = (
            evidence["id"],
            evidence["source_kind"],
            evidence["asset_path"],
            evidence["asset_sha256"],
            evidence.get("transcript_path", "—"),
            evidence.get("transcript_sha256", "—"),
            locator,
            _markdown_escape(evidence["claim"]),
        )
        lines.append("| " + " | ".join(str(cell) for cell in evidence_cells) + " |")
    glossary = rulebook.data.get("glossary", [])
    if glossary:
        lines.extend(["", "## Glossary", "", "| Term | Meaning | Evidence |", "|---|---|---|"])
        for entry in sorted(glossary, key=lambda item: item["term"]):
            cells = (
                entry["term"],
                _markdown_escape(entry["meaning"]),
                ", ".join(sorted(entry["evidence_ids"])),
            )
            lines.append("| " + " | ".join(cells) + " |")
    examples = rulebook.data.get("examples", [])
    if examples:
        lines.extend(
            [
                "",
                "## Illustrative Examples (Non-Normative)",
                "",
                "| ID | Label | Claim |",
                "|---|---|---|",
            ]
        )
        for example in sorted(examples, key=lambda item: item["id"]):
            example_cells = (
                example["id"],
                _markdown_escape(example["label"]),
                _markdown_escape(example["claim"]),
            )
            lines.append("| " + " | ".join(str(cell) for cell in example_cells) + " |")
    lines.extend(
        [
            "",
            "## Candidate Strategy Claims",
            "",
            "| ID | Status | Capability | Claim | Evidence |",
            "|---|---|---|---|---|",
        ]
    )
    for rule in sorted(rulebook.data["rules"], key=lambda item: item["id"]):
        rule_cells = (
            rule["id"],
            rule["status"],
            rule["capability"],
            _markdown_escape(rule["claim"]),
            ", ".join(sorted(rule["evidence_ids"])),
        )
        lines.append("| " + " | ".join(str(cell) for cell in rule_cells) + " |")
    lines.extend(["", "## Unresolved Decisions", ""])
    decisions = rulebook.data.get("unresolved_decisions", [])
    if decisions:
        for decision in sorted(decisions, key=lambda item: item["id"]):
            lines.append(f"- `{decision['id']}`: {decision['question']}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Source Conflicts", ""])
    conflicts = rulebook.data.get("conflicts", [])
    if conflicts:
        for conflict in sorted(conflicts, key=lambda item: item["id"]):
            lines.append(f"- `{conflict['id']}`: {conflict['description']}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Publication Blockers", ""])
    if state.blockers:
        lines.extend(f"- {blocker}" for blocker in state.blockers)
    else:
        lines.append(
            "- None. Ed25519 signature verification occurs at publish and published-release load."
        )
    lines.extend(
        [
            "",
            "## Approval Instructions",
            "",
            "1. Keep the Ed25519 private key outside this repository.",
            "2. Compute `public_key_fingerprint` as SHA-256 of the raw 32-byte public key.",
            "3. Run `stoic-rulebook approval-message` with the reviewer email, UTC `Z` "
            "timestamp, and fingerprint; redirect its exact binary stdout with no added newline.",
            "4. Sign those exact bytes and base64-encode the raw 64-byte Ed25519 signature.",
            "5. Add `reviewer_email`, `approved_at`, `candidate_sha256`, "
            "`public_key_fingerprint`, and `signature_base64` to the approval envelope.",
            "6. Publish with `--public-key-hex`; publication and SP2 verify the signature "
            "against that separately pinned raw public key.",
            "Any semantic YAML edit changes the candidate digest and requires a new approval.",
            "",
        ]
    )
    return "\n".join(lines)


def _release_payload(rulebook: Rulebook) -> dict[str, Any]:
    return {
        "schema_version": rulebook.data["schema_version"],
        "rulebook_version": rulebook.data["rulebook_version"],
        "source_yaml_sha256": rulebook.source_yaml_sha256,
        "candidate_sha256": candidate_digest(rulebook),
        "scope": rulebook.data["scope"],
        "glossary": rulebook.data.get("glossary", []),
        "rules": rulebook.data["rules"],
        "source_snapshot_digests": {
            evidence["id"]: {
                "asset_sha256": evidence["asset_sha256"],
                **(
                    {"transcript_sha256": evidence["transcript_sha256"]}
                    if "transcript_sha256" in evidence
                    else {}
                ),
            }
            for evidence in sorted(rulebook.data["evidence"], key=lambda item: item["id"])
        },
        "approval": rulebook.data["approval"],
        "compiler_version": COMPILER_VERSION,
    }


def publish(
    path: Path | str,
    releases_dir: Path | str,
    public_key: Ed25519PublicKey | bytes | None = None,
) -> Path:
    """Compile an approved, fully-ready candidate to canonical immutable JSON."""
    rulebook = load_rulebook(path, verify_sources=True)
    approval = rulebook.data.get("approval")
    if approval is None:
        raise PublicationError("approval is missing or does not match the candidate digest")
    try:
        _verify_approval(approval, candidate_digest(rulebook), public_key)
    except RulebookError as exc:
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError(str(exc)) from exc
    state = readiness(rulebook)
    if not state.ready:
        raise PublicationError("rulebook is not live-ready: " + "; ".join(state.blockers))
    try:
        _validate_semver(
            rulebook.data["rulebook_version"], "rulebook_version", allow_prerelease=False
        )
    except RulebookError as exc:
        raise PublicationError(str(exc)) from exc
    release = _release_payload(rulebook)
    release["payload_sha256"] = _sha256_bytes(_canonical_json(release))
    serialized = _canonical_json(release)
    output_dir = Path(releases_dir)
    output = output_dir / f"{rulebook.data['rulebook_version']}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != serialized:
        raise PublicationError(f"refusing to overwrite a different immutable release: {output}")
    output.write_bytes(serialized)
    return output


def _validate_source_snapshot_digests(value: Any) -> set[str]:
    snapshots = _expect_mapping(value, "source_snapshot_digests")
    if not snapshots:
        _fail("source_snapshot_digests must contain nonempty provenance snapshots")
    evidence_ids: set[str] = set()
    for evidence_id, snapshot_value in snapshots.items():
        _expect_string(evidence_id, "source_snapshot_digests key")
        snapshot = _expect_mapping(snapshot_value, f"source_snapshot_digests.{evidence_id}")
        _reject_unknown_keys(
            snapshot,
            frozenset({"asset_sha256", "transcript_sha256"}),
            f"source_snapshot_digests.{evidence_id}",
        )
        _validate_sha256_digest(
            snapshot.get("asset_sha256"), f"source_snapshot_digests.{evidence_id}.asset_sha256"
        )
        if "transcript_sha256" in snapshot:
            _validate_sha256_digest(
                snapshot["transcript_sha256"],
                f"source_snapshot_digests.{evidence_id}.transcript_sha256",
            )
        evidence_ids.add(evidence_id)
    return evidence_ids


def _validate_published_release(
    release: dict[str, Any], raw: bytes, public_key: Ed25519PublicKey | bytes | None
) -> None:
    _reject_unknown_keys(
        release,
        frozenset(
            {
                "schema_version",
                "rulebook_version",
                "source_yaml_sha256",
                "candidate_sha256",
                "scope",
                "glossary",
                "rules",
                "source_snapshot_digests",
                "approval",
                "compiler_version",
                "payload_sha256",
            }
        ),
        "release",
    )
    if raw != _canonical_json(release):
        raise PublicationError("published release bytes are not canonical JSON")
    _validate_schema_version(release.get("schema_version"))
    _validate_semver(
        release.get("rulebook_version"), "release.rulebook_version", allow_prerelease=False
    )
    if release.get("compiler_version") != COMPILER_VERSION:
        _fail(f"unsupported compiler version: {release.get('compiler_version')!r}")
    _validate_sha256_digest(release.get("source_yaml_sha256"), "release.source_yaml_sha256")
    candidate_sha256 = _validate_sha256_digest(
        release.get("candidate_sha256"), "release.candidate_sha256"
    )
    _validate_scope(release.get("scope"))
    evidence_ids = _validate_source_snapshot_digests(release.get("source_snapshot_digests"))
    _validate_glossary(release.get("glossary", []), evidence_ids)
    _verify_approval(release.get("approval"), candidate_sha256, public_key)
    rules = _validate_rules(release.get("rules"), evidence_ids)
    release_rulebook = Rulebook(
        path=Path("<published-release>"),
        data={
            "rules": rules,
            "unresolved_decisions": [],
            "conflicts": [],
            "approval": release["approval"],
        },
        source_yaml_sha256=release["source_yaml_sha256"],
    )
    if not readiness(release_rulebook, check_approval=False).ready:
        _fail("published release is not live-ready")
    _validate_no_forbidden_dependencies(release)
    unsigned_release = dict(release)
    supplied_content_digest = unsigned_release.pop("payload_sha256", None)
    if not isinstance(supplied_content_digest, str) or supplied_content_digest != _sha256_bytes(
        _canonical_json(unsigned_release)
    ):
        raise PublicationError("published release content hash mismatch")


def load_published_release(
    path: Path | str,
    expected_sha256: str,
    public_key: Ed25519PublicKey | bytes | None = None,
) -> dict[str, Any]:
    """SP2-facing fail-closed loader: accepts canonical published JSON only."""
    release_path = Path(path)
    if release_path.suffix != ".json" or "releases" not in release_path.parts:
        raise PublicationError("SP2 may load only a published JSON release")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PublicationError("published release requires a pinned lower-case SHA-256 hash")
    try:
        raw = release_path.read_bytes()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"cannot load published release: {release_path}") from exc
    release = _expect_mapping(data, "release")
    try:
        _validate_published_release(release, raw, public_key)
    except RulebookError as exc:
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError(str(exc)) from exc
    if _sha256_bytes(raw) != expected_sha256:
        raise PublicationError("published release file hash mismatch")
    return release
