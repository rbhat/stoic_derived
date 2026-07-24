"""SP3 immutable research-artifact tests."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

import stoic_derived.backtest.artifact as artifact_module
from stoic_derived.backtest.artifact import (
    ARTIFACT_FILENAMES,
    RESEARCH_OBSERVATION_DISCLAIMER,
    ArtifactError,
    inspect_artifact,
    write_artifact,
)
from stoic_derived.backtest.model import BacktestResult, EvidenceClass, RunWarning, WarningCode


def _result() -> BacktestResult:
    return BacktestResult.blocked(
        evidence_class=EvidenceClass.RETROSPECTIVE_REPLAY,
        plan_id="f" * 64,
        readiness_blockers=("signed_release_unavailable",),
    )


def _write(target: Path, *, maximum: int = 10_000) -> None:
    write_artifact(_result(), target, max_artifact_bytes=maximum)


def _rewrite_manifest_hash(target: Path, name: str) -> None:
    manifest_path = target / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][name]["sha256"] = sha256((target / name).read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )


def test_independent_targets_are_byte_identical_and_manifest_reconciles(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first)
    _write(second)

    assert tuple(sorted(path.name for path in first.iterdir())) == tuple(sorted(ARTIFACT_FILENAMES))
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }
    summary = inspect_artifact(first)
    assert summary.run_id == _result().run_id
    assert summary.manifest_id == _result().manifest_id
    assert summary.execution is False
    assert summary.orders_placed == 0
    assert summary.artifact_bytes == sum(path.stat().st_size for path in first.iterdir())


def test_manifest_contains_the_research_only_disclaimer(tmp_path: Path) -> None:
    target = tmp_path / "artifact"
    _write(target)

    manifest = json.loads((target / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution"] is False
    assert manifest["orders_placed"] == 0
    assert manifest["research_observation_disclaimer"] == RESEARCH_OBSERVATION_DISCLAIMER


@pytest.mark.parametrize("name", ["signals.jsonl", "run_manifest.json"])
def test_inspection_rejects_tampered_or_missing_members(tmp_path: Path, name: str) -> None:
    target = tmp_path / "artifact"
    _write(target)
    path = target / name
    if name == "signals.jsonl":
        path.write_bytes(b"{}\n")
    else:
        path.unlink()

    with pytest.raises(ArtifactError):
        inspect_artifact(target)


def test_inspection_rejects_noncanonical_jsonl(tmp_path: Path) -> None:
    target = tmp_path / "artifact"
    _write(target)
    (target / "warnings.jsonl").write_bytes(b"{ }\n")

    with pytest.raises(ArtifactError):
        inspect_artifact(target)


def test_inspection_rejects_reordered_rows_and_wrong_record_identity(tmp_path: Path) -> None:
    warnings = tuple(
        sorted(
            (
                RunWarning(WarningCode.END_OF_DATA, "alpha"),
                RunWarning(WarningCode.FOLD_END, "beta"),
            ),
            key=lambda warning: warning.warning_id,
        )
    )
    result = BacktestResult(
        evidence_class=EvidenceClass.RETROSPECTIVE_REPLAY,
        status=_result().status,
        plan_id="f" * 64,
        readiness_blockers=("signed_release_unavailable",),
        warnings=warnings,
    )
    reordered = tmp_path / "reordered"
    write_artifact(result, reordered, max_artifact_bytes=10_000)
    warning_path = reordered / "warnings.jsonl"
    warning_path.write_bytes(b"\n".join(reversed(warning_path.read_bytes().splitlines())) + b"\n")
    _rewrite_manifest_hash(reordered, "warnings.jsonl")
    with pytest.raises(ArtifactError, match="canonically ordered"):
        inspect_artifact(reordered)

    wrong_id = tmp_path / "wrong-id"
    write_artifact(result, wrong_id, max_artifact_bytes=10_000)
    warning_path = wrong_id / "warnings.jsonl"
    rows = [json.loads(line) for line in warning_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["warning_id"] = "0" * 64
    warning_path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":"), sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _rewrite_manifest_hash(wrong_id, "warnings.jsonl")
    with pytest.raises(ArtifactError, match="identity mismatch"):
        inspect_artifact(wrong_id)


def test_existing_target_and_bound_failure_leave_no_published_target(tmp_path: Path) -> None:
    target = tmp_path / "artifact"
    target.mkdir()
    with pytest.raises(ArtifactError, match="must not already exist"):
        _write(target)

    too_small = tmp_path / "too-small"
    with pytest.raises(ArtifactError, match="byte bound"):
        _write(too_small, maximum=1)
    assert not too_small.exists()
    assert not list(tmp_path.glob(".too-small.artifact-*"))


def test_target_appearing_during_publication_is_never_replaced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "artifact"
    rename_noreplace = artifact_module._atomic_rename_noreplace

    def create_racing_target(source: Path, destination: Path) -> None:
        destination.mkdir()
        rename_noreplace(source, destination)

    monkeypatch.setattr(
        artifact_module,
        "_atomic_rename_noreplace",
        create_racing_target,
    )

    with pytest.raises(ArtifactError, match="appeared during publication"):
        _write(target)

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".artifact.artifact-*"))


def test_exact_artifact_bound_is_accepted(tmp_path: Path) -> None:
    first = tmp_path / "first"
    _write(first, maximum=9_999)
    exact = sum(path.stat().st_size for path in first.iterdir())
    second = tmp_path / "second"
    _write(second, maximum=exact)
    assert inspect_artifact(second).artifact_bytes == exact
