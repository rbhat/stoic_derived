"""Atomic, content-addressed research artifacts for SP3.

Artifacts are deliberately observations, never broker instructions.  This
module only serializes immutable :class:`BacktestResult` values and verifies
their evidence on disk; it has no engine, strategy, or execution dependency.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn, cast

from stoic_derived.backtest.model import (
    SIMULATOR_ALGORITHM_VERSION,
    BacktestResult,
    BacktestStatus,
    EvidenceClass,
    canonical_json_bytes,
)

ARTIFACT_FILENAMES = (
    "run_manifest.json",
    "signals.jsonl",
    "suppressions.jsonl",
    "fills.jsonl",
    "trades.jsonl",
    "equity.jsonl",
    "metrics.json",
    "warnings.jsonl",
)
_CONTENT_FILENAMES = ARTIFACT_FILENAMES[1:]
RESEARCH_OBSERVATION_DISCLAIMER = (
    "Simulated fills are research observations only; no broker execution or orders occur."
)


class ArtifactError(ValueError):
    """Raised when an artifact cannot be safely published or verified."""


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    """One immutable artifact member pinned by the run manifest."""

    name: str
    row_count: int
    sha256: str

    def canonical_dict(self) -> dict[str, object]:
        return {"row_count": self.row_count, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    """Deterministic inspection result with no host or path-derived values."""

    plan_id: str
    run_id: str
    manifest_id: str
    status: str
    evidence_class: str
    schema_version: str
    artifact_algorithm_version: str
    execution: bool
    orders_placed: int
    artifact_bytes: int
    files: tuple[ArtifactFile, ...]

    def canonical_dict(self) -> dict[str, object]:
        return {
            "artifact_algorithm_version": self.artifact_algorithm_version,
            "artifact_bytes": self.artifact_bytes,
            "evidence_class": self.evidence_class,
            "execution": self.execution,
            "files": [member.canonical_dict() | {"name": member.name} for member in self.files],
            "manifest_id": self.manifest_id,
            "orders_placed": self.orders_placed,
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "status": self.status,
        }


def write_artifact(
    result: BacktestResult,
    target: Path,
    *,
    max_artifact_bytes: int,
) -> ArtifactSummary:
    """Publish ``result`` once, atomically, after enforcing the exact byte bound.

    The caller supplies the policy-owned bound because a ``BacktestResult`` is
    intentionally independent of simulation policy.  An existing target is
    always refused, including an empty directory.
    """
    if not isinstance(result, BacktestResult):
        raise ArtifactError("result must be a BacktestResult")
    if not isinstance(target, Path):
        raise ArtifactError("target must be a pathlib.Path")
    _require_positive_int(max_artifact_bytes, "max_artifact_bytes")
    if target.exists() or target.is_symlink():
        raise ArtifactError("artifact target must not already exist")
    if not target.parent.is_dir():
        raise ArtifactError("artifact target parent must exist and be a directory")

    payloads, row_counts = _result_payloads(result)
    manifest_payload = _manifest_payload(result, payloads, row_counts, max_artifact_bytes)
    payloads = {"run_manifest.json": manifest_payload, **payloads}
    total_bytes = sum(len(payload) for payload in payloads.values())
    if total_bytes > max_artifact_bytes:
        raise ArtifactError("artifact byte bound exceeded")

    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.artifact-", dir=target.parent))
    try:
        for name in _CONTENT_FILENAMES:
            _write_synced(temporary / name, payloads[name])
        # The manifest is the commit marker inside the temporary directory.
        _write_synced(temporary / "run_manifest.json", payloads["run_manifest.json"])
        _fsync_directory(temporary)
        if target.exists() or target.is_symlink():
            raise ArtifactError("artifact target appeared during publication")
        try:
            _atomic_rename_noreplace(temporary, target)
        except FileExistsError as exc:
            raise ArtifactError("artifact target appeared during publication") from exc
        _fsync_directory(target.parent)
    except BaseException:
        if temporary.exists() or temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return _summary_from_manifest(_load_canonical_json(payloads["run_manifest.json"], "manifest"))


def inspect_artifact(target: Path) -> ArtifactSummary:
    """Fail closed unless ``target`` is one exact, untampered SP3 artifact."""
    if not isinstance(target, Path):
        raise ArtifactError("target must be a pathlib.Path")
    if not target.is_dir() or target.is_symlink():
        raise ArtifactError("artifact target must be a real directory")
    names = tuple(sorted(path.name for path in target.iterdir()))
    if names != tuple(sorted(ARTIFACT_FILENAMES)):
        raise ArtifactError("artifact directory must contain exactly the required files")

    raw_files: dict[str, bytes] = {}
    for name in ARTIFACT_FILENAMES:
        path = target / name
        if not path.is_file() or path.is_symlink():
            raise ArtifactError(f"artifact member is not a regular file: {name}")
        try:
            raw_files[name] = path.read_bytes()
        except OSError as exc:
            raise ArtifactError(f"cannot read artifact member: {name}") from exc

    manifest = _load_canonical_json(raw_files["run_manifest.json"], "manifest")
    _validate_manifest_shape(manifest)
    for name in _CONTENT_FILENAMES:
        member = _require_mapping(_require_mapping(manifest["files"], "manifest.files")[name], name)
        if set(member) != {"row_count", "sha256"}:
            raise ArtifactError(f"manifest file entry must have exact fields: {name}")
        expected_hash = _require_sha256(member.get("sha256"), f"{name}.sha256")
        expected_count = _require_nonnegative_int(member.get("row_count"), f"{name}.row_count")
        if sha256(raw_files[name]).hexdigest() != expected_hash:
            raise ArtifactError(f"artifact hash mismatch: {name}")
        if _row_count_and_validate(name, raw_files[name]) != expected_count:
            raise ArtifactError(f"artifact row count mismatch: {name}")

    _validate_result_identity(manifest, raw_files)
    total_bytes = sum(len(value) for value in raw_files.values())
    max_bytes = _require_positive_int(manifest["max_artifact_bytes"], "max_artifact_bytes")
    if total_bytes != _require_nonnegative_int(manifest["artifact_bytes"], "artifact_bytes"):
        raise ArtifactError("manifest artifact_bytes does not reconcile")
    if total_bytes > max_bytes:
        raise ArtifactError("artifact exceeds manifest byte bound")
    return _summary_from_manifest(manifest)


def _result_payloads(result: BacktestResult) -> tuple[dict[str, bytes], dict[str, int]]:
    rows: dict[str, tuple[dict[str, object], ...]] = {
        "signals.jsonl": tuple(signal.canonical_dict() for signal in result.signals),
        "suppressions.jsonl": tuple(
            suppression.canonical_dict() for suppression in result.suppressions
        ),
        "fills.jsonl": tuple(fill.canonical_dict() for fill in result.fills),
        "trades.jsonl": tuple(trade.canonical_dict() for trade in result.trades),
        "equity.jsonl": tuple(point.canonical_dict() for point in result.equity),
        "warnings.jsonl": tuple(warning.canonical_dict() for warning in result.warnings),
    }
    metrics_document = {
        "exclusions": [exclusion.canonical_dict() for exclusion in result.exclusions],
        "metrics": [metric.canonical_dict() for metric in result.metrics],
        "schema_version": result.schema_version,
    }
    payloads = {name: _encode_jsonl(values) for name, values in rows.items()}
    payloads["metrics.json"] = canonical_json_bytes(metrics_document)
    row_counts = {name: len(values) for name, values in rows.items()}
    row_counts["metrics.json"] = len(result.metrics) + len(result.exclusions)
    return payloads, row_counts


def _manifest_payload(
    result: BacktestResult,
    payloads: Mapping[str, bytes],
    row_counts: Mapping[str, int],
    max_artifact_bytes: int,
) -> bytes:
    files = {
        name: {
            "row_count": row_counts[name],
            "sha256": sha256(payloads[name]).hexdigest(),
        }
        for name in _CONTENT_FILENAMES
    }
    metric_versions = sorted({metric.metrics_algorithm_version for metric in result.metrics})
    # ``artifact_bytes`` includes this canonical manifest.  Its value changes
    # only in digit width, so solve the tiny fixed-point deterministically.
    base = {
        "algorithm_versions": {
            "artifact": result.artifact_algorithm_version,
            "metrics": metric_versions,
            "simulator": SIMULATOR_ALGORITHM_VERSION,
        },
        "artifact_bytes": 0,
        "evidence_class": result.evidence_class.value,
        "execution": False,
        "files": files,
        "manifest_id": result.manifest_id,
        "max_artifact_bytes": max_artifact_bytes,
        "orders_placed": 0,
        "plan_id": result.plan_id,
        "readiness_blockers": list(result.readiness_blockers),
        "research_observation_disclaimer": RESEARCH_OBSERVATION_DISCLAIMER,
        "run_id": result.run_id,
        "schema_version": result.schema_version,
        "status": result.status.value,
    }
    content_bytes = sum(len(payload) for payload in payloads.values())
    total = content_bytes
    while True:
        candidate = {**base, "artifact_bytes": total}
        encoded = canonical_json_bytes(candidate)
        resolved = content_bytes + len(encoded)
        if resolved == total:
            return encoded
        total = resolved


def _encode_jsonl(rows: tuple[dict[str, object], ...]) -> bytes:
    if not rows:
        return b""
    return b"\n".join(canonical_json_bytes(row) for row in rows) + b"\n"


def _write_synced(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_rename_noreplace(source: Path, target: Path) -> None:
    """Atomically publish one directory while refusing every existing target."""
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = library.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        ctypes.set_errno(0)
        result = renameat2(
            -100,
            os.fsencode(source),
            -100,
            os.fsencode(target),
            1,
        )
    elif sys.platform == "darwin":
        library = ctypes.CDLL(None, use_errno=True)
        renamex_np = library.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        ctypes.set_errno(0)
        result = renamex_np(os.fsencode(source), os.fsencode(target), 0x00000004)
    elif os.name == "nt":
        # Windows rename already refuses to replace an existing destination.
        os.rename(source, target)
        return
    else:
        raise ArtifactError("atomic no-replace directory publication is unsupported")

    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), target)
    raise OSError(error, os.strerror(error), target)


def _row_count_and_validate(name: str, payload: bytes) -> int:
    if name == "metrics.json":
        document = _load_canonical_json(payload, name)
        _validate_metrics_document(document)
        metrics = cast(list[dict[str, object]], document["metrics"])
        exclusions = cast(list[dict[str, object]], document["exclusions"])
        _validate_sorted_records(metrics, "metric_id", name)
        _validate_sorted_records(exclusions, "exclusion_id", name)
        return len(metrics) + len(exclusions)
    rows = _load_canonical_jsonl(payload, name)
    if name == "signals.jsonl":
        _validate_sorted_records(rows, "signal_id", name)
    elif name == "suppressions.jsonl":
        _validate_sorted_records(rows, None, name)
    elif name == "fills.jsonl":
        _validate_sorted_records(rows, "fill_id", name)
    elif name == "trades.jsonl":
        _validate_sorted_records(rows, "trade_id", name)
    elif name == "equity.jsonl":
        _validate_equity(rows)
    elif name == "warnings.jsonl":
        _validate_sorted_records(rows, "warning_id", name)
    else:  # pragma: no cover - internal constant protects this branch
        raise ArtifactError(f"unsupported artifact member: {name}")
    return len(rows)


def _validate_metrics_document(document: dict[str, object]) -> None:
    if set(document) != {"exclusions", "metrics", "schema_version"}:
        raise ArtifactError("metrics.json must have the exact canonical fields")
    if not isinstance(document["metrics"], list) or not isinstance(document["exclusions"], list):
        raise ArtifactError("metrics.json records must be arrays")
    if not isinstance(document["schema_version"], str) or not document["schema_version"]:
        raise ArtifactError("metrics.json schema_version must be a non-empty string")


def _validate_sorted_records(
    rows: list[dict[str, object]], identity_key: str | None, name: str
) -> None:
    if identity_key is None:
        keys = tuple(sha256(canonical_json_bytes(row)).hexdigest() for row in rows)
    else:
        keys = tuple(_validate_record_identity(row, identity_key, name) for row in rows)
    if tuple(sorted(keys)) != keys or len(set(keys)) != len(keys):
        raise ArtifactError(f"artifact records are not canonically ordered: {name}")


def _validate_record_identity(row: dict[str, object], identity_key: str, name: str) -> str:
    observed = _require_sha256(row.get(identity_key), f"{name}.{identity_key}")
    without_id = {key: value for key, value in row.items() if key != identity_key}
    expected = sha256(canonical_json_bytes(without_id)).hexdigest()
    if observed != expected:
        raise ArtifactError(f"artifact record identity mismatch: {name}.{identity_key}")
    return observed


def _validate_equity(rows: list[dict[str, object]]) -> None:
    keys: list[tuple[int, str]] = []
    for row in rows:
        exit_ts = _require_nonnegative_int(row.get("exit_ts_ns"), "equity.exit_ts_ns")
        trade_id = _require_sha256(row.get("trade_id"), "equity.trade_id")
        keys.append((exit_ts, trade_id))
    if tuple(sorted(keys)) != tuple(keys) or len(set(keys)) != len(keys):
        raise ArtifactError("equity records are not canonically ordered")


def _validate_manifest_shape(manifest: dict[str, object]) -> None:
    required = {
        "algorithm_versions",
        "artifact_bytes",
        "evidence_class",
        "execution",
        "files",
        "manifest_id",
        "max_artifact_bytes",
        "orders_placed",
        "plan_id",
        "readiness_blockers",
        "research_observation_disclaimer",
        "run_id",
        "schema_version",
        "status",
    }
    if set(manifest) != required:
        raise ArtifactError("manifest must have the exact canonical fields")
    if manifest["execution"] is not False or manifest["orders_placed"] != 0:
        raise ArtifactError("manifest must declare no execution and zero orders")
    if manifest["research_observation_disclaimer"] != RESEARCH_OBSERVATION_DISCLAIMER:
        raise ArtifactError("manifest research-observation disclaimer is invalid")
    for name in ("plan_id", "run_id", "manifest_id"):
        _require_sha256(manifest[name], f"manifest.{name}")
    if not isinstance(manifest["status"], str) or not isinstance(manifest["evidence_class"], str):
        raise ArtifactError("manifest status and evidence_class must be strings")
    if manifest["status"] not in {status.value for status in BacktestStatus}:
        raise ArtifactError("manifest status is unsupported")
    if manifest["evidence_class"] not in {evidence.value for evidence in EvidenceClass}:
        raise ArtifactError("manifest evidence_class is unsupported")
    if not isinstance(manifest["schema_version"], str) or not manifest["schema_version"]:
        raise ArtifactError("manifest schema_version must be a non-empty string")
    blockers = manifest["readiness_blockers"]
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item for item in blockers
    ):
        raise ArtifactError("manifest readiness_blockers must be strings")
    if blockers != sorted(blockers) or len(set(blockers)) != len(blockers):
        raise ArtifactError("manifest readiness_blockers must be sorted and unique")
    files = _require_mapping(manifest["files"], "manifest.files")
    if set(files) != set(_CONTENT_FILENAMES):
        raise ArtifactError("manifest must pin exactly every non-manifest artifact")
    versions = _require_mapping(manifest["algorithm_versions"], "manifest.algorithm_versions")
    if set(versions) != {"artifact", "metrics", "simulator"}:
        raise ArtifactError("manifest must pin every algorithm version")
    if not isinstance(versions["artifact"], str) or not versions["artifact"]:
        raise ArtifactError("artifact algorithm version must be non-empty")
    if not isinstance(versions["simulator"], str) or not versions["simulator"]:
        raise ArtifactError("simulator algorithm version must be non-empty")
    if versions["simulator"] != SIMULATOR_ALGORITHM_VERSION:
        raise ArtifactError("simulator algorithm version is unsupported")
    if not isinstance(versions["metrics"], list) or any(
        not isinstance(version, str) or not version for version in versions["metrics"]
    ):
        raise ArtifactError("metrics algorithm versions must be strings")
    if versions["metrics"] != sorted(versions["metrics"]) or len(set(versions["metrics"])) != len(
        versions["metrics"]
    ):
        raise ArtifactError("metrics algorithm versions must be sorted and unique")


def _validate_result_identity(manifest: dict[str, object], raw_files: Mapping[str, bytes]) -> None:
    rows = {
        "signals": _load_canonical_jsonl(raw_files["signals.jsonl"], "signals.jsonl"),
        "suppressions": _load_canonical_jsonl(
            raw_files["suppressions.jsonl"], "suppressions.jsonl"
        ),
        "fills": _load_canonical_jsonl(raw_files["fills.jsonl"], "fills.jsonl"),
        "trades": _load_canonical_jsonl(raw_files["trades.jsonl"], "trades.jsonl"),
        "equity": _load_canonical_jsonl(raw_files["equity.jsonl"], "equity.jsonl"),
        "warnings": _load_canonical_jsonl(raw_files["warnings.jsonl"], "warnings.jsonl"),
    }
    metrics_document = _load_canonical_json(raw_files["metrics.json"], "metrics.json")
    if metrics_document["schema_version"] != manifest["schema_version"]:
        raise ArtifactError("metrics schema_version does not match manifest")
    metric_versions = sorted(
        {
            _require_string(metric.get("metrics_algorithm_version"), "metric version")
            for metric in _require_list_of_objects(metrics_document["metrics"], "metrics.metrics")
        }
    )
    manifest_versions = _require_mapping(
        manifest["algorithm_versions"], "manifest.algorithm_versions"
    )
    if manifest_versions["metrics"] != metric_versions:
        raise ArtifactError("metrics algorithm versions do not reconcile")
    content = {
        "artifact_algorithm_version": _require_mapping(
            manifest["algorithm_versions"], "manifest.algorithm_versions"
        )["artifact"],
        "equity": rows["equity"],
        "evidence_class": manifest["evidence_class"],
        "execution": False,
        "exclusions": _require_list_of_objects(
            metrics_document["exclusions"], "metrics.exclusions"
        ),
        "fills": rows["fills"],
        "metrics": _require_list_of_objects(metrics_document["metrics"], "metrics.metrics"),
        "orders_placed": 0,
        "plan_id": manifest["plan_id"],
        "readiness_blockers": manifest["readiness_blockers"],
        "schema_version": manifest["schema_version"],
        "signals": rows["signals"],
        "status": manifest["status"],
        "suppressions": rows["suppressions"],
        "trades": rows["trades"],
        "warnings": rows["warnings"],
    }
    expected_run_id = sha256(canonical_json_bytes(content)).hexdigest()
    if manifest["run_id"] != expected_run_id:
        raise ArtifactError("manifest run_id does not reconcile to artifact content")
    expected_manifest_id = sha256(
        canonical_json_bytes({**content, "run_id": expected_run_id})
    ).hexdigest()
    if manifest["manifest_id"] != expected_manifest_id:
        raise ArtifactError("manifest_id does not reconcile to artifact content")
    if manifest["status"] == "blocked":
        if not manifest["readiness_blockers"]:
            raise ArtifactError("blocked artifact must retain readiness blockers")
        if any(rows[name] for name in ("signals", "fills", "trades", "equity")) or (
            metrics_document["metrics"] or metrics_document["exclusions"]
        ):
            raise ArtifactError("blocked artifact must have a zero trade population")
    elif manifest["readiness_blockers"]:
        raise ArtifactError("complete artifact cannot retain readiness blockers")


def _summary_from_manifest(manifest: dict[str, object]) -> ArtifactSummary:
    files = _require_mapping(manifest["files"], "manifest.files")
    members = tuple(
        ArtifactFile(
            name=name,
            row_count=_require_nonnegative_int(
                _require_mapping(files[name], name)["row_count"], f"{name}.row_count"
            ),
            sha256=_require_sha256(_require_mapping(files[name], name)["sha256"], f"{name}.sha256"),
        )
        for name in _CONTENT_FILENAMES
    )
    versions = _require_mapping(manifest["algorithm_versions"], "manifest.algorithm_versions")
    return ArtifactSummary(
        plan_id=cast(str, manifest["plan_id"]),
        run_id=cast(str, manifest["run_id"]),
        manifest_id=cast(str, manifest["manifest_id"]),
        status=cast(str, manifest["status"]),
        evidence_class=cast(str, manifest["evidence_class"]),
        schema_version=cast(str, manifest["schema_version"]),
        artifact_algorithm_version=cast(str, versions["artifact"]),
        execution=False,
        orders_placed=0,
        artifact_bytes=_require_nonnegative_int(manifest["artifact_bytes"], "artifact_bytes"),
        files=members,
    )


def _load_canonical_json(payload: bytes, name: str) -> dict[str, object]:
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, ArtifactError):
            raise
        raise ArtifactError(f"artifact JSON is invalid: {name}") from exc
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        raise ArtifactError(f"artifact JSON must be an object: {name}")
    result = cast(dict[str, object], decoded)
    if canonical_json_bytes(result) != payload:
        raise ArtifactError(f"artifact JSON is not canonical: {name}")
    return result


def _load_canonical_jsonl(payload: bytes, name: str) -> list[dict[str, object]]:
    if not payload:
        return []
    if not payload.endswith(b"\n"):
        raise ArtifactError(f"artifact JSONL must end with a newline: {name}")
    lines = payload.split(b"\n")[:-1]
    if any(not line for line in lines):
        raise ArtifactError(f"artifact JSONL cannot contain blank lines: {name}")
    return [_load_canonical_json(line, name) for line in lines]


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ArtifactError(f"non-finite JSON number is forbidden: {value}")


def _require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ArtifactError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _require_list_of_objects(value: object, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ArtifactError(f"{name} must be an array")
    return [_require_mapping(item, name) for item in value]


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactError(f"{name} must be a non-empty string")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ArtifactError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ArtifactError(f"{name} must be a positive integer")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ArtifactError(f"{name} must be a non-negative integer")
    return value
