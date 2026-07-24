"""Tests for content-addressed run manifests.

Pure stdlib + a real throwaway git repo under tmp_path (no network). CPU-only.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stoic_training import manifest


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("placeholder\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def write_dataset_dir(tmp_path: Path, *, corpus_sha256: str = "a" * 64) -> Path:
    dataset_dir = tmp_path / "datasets" / "v1"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps({"corpus_sha256": corpus_sha256, "split_version": "v1", "counts": {}}),
        encoding="utf-8",
    )
    (dataset_dir / "train.jsonl").write_text('{"task": "cited_qa"}\n', encoding="utf-8")
    (dataset_dir / "eval.jsonl").write_text('{"task": "cited_qa"}\n', encoding="utf-8")
    return dataset_dir


BASE_MODEL = {"repo_id": "Qwen/Qwen3-8B", "revision": "deadbeef"}
VERSIONS = {"torch": "2.11.0", "transformers": "5.14.1", "peft": "0.19.1", "trl": "1.9.0", "bitsandbytes": "0.49.2"}
CONFIG_RESOLVED = {"model": {"repo_id": "Qwen/Qwen3-8B"}, "training": {"seed": 1}}


def test_canonical_json_bytes_ignores_key_order():
    a = manifest.canonical_json_bytes({"b": 1, "a": 2})
    b = manifest.canonical_json_bytes({"a": 2, "b": 1})
    assert a == b
    assert b" " not in a  # no whitespace variance


def test_sha256_file_is_stable_for_same_content(tmp_path):
    path1 = tmp_path / "one.txt"
    path2 = tmp_path / "two.txt"
    path1.write_text("identical content\n", encoding="utf-8")
    path2.write_text("identical content\n", encoding="utf-8")
    assert manifest.sha256_file(path1) == manifest.sha256_file(path2)


def test_sha256_dir_is_stable_and_order_independent(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "x.txt").write_text("x", encoding="utf-8")
    (dir_a / "y.txt").write_text("y", encoding="utf-8")
    (dir_b / "y.txt").write_text("y", encoding="utf-8")
    (dir_b / "x.txt").write_text("x", encoding="utf-8")
    assert manifest.sha256_dir(dir_a) == manifest.sha256_dir(dir_b)


def test_load_dataset_ref_reads_manifest_and_hashes_files(tmp_path):
    dataset_dir = write_dataset_dir(tmp_path)
    ref = manifest.load_dataset_ref(dataset_dir)
    assert ref.corpus_sha256 == "a" * 64
    assert len(ref.dataset_manifest_sha256) == 64
    assert len(ref.train_sha256) == 64
    assert len(ref.eval_sha256) == 64


def test_load_dataset_ref_missing_file_raises(tmp_path):
    dataset_dir = tmp_path / "datasets" / "v1"
    dataset_dir.mkdir(parents=True)
    with pytest.raises(manifest.ManifestError):
        manifest.load_dataset_ref(dataset_dir)


def test_git_rev_reads_clean_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    init_git_repo(repo_dir)
    rev = manifest.git_rev(repo_dir)
    assert len(rev.sha) == 40
    assert rev.dirty is False


def test_git_rev_detects_dirty_worktree(tmp_path):
    repo_dir = tmp_path / "repo"
    init_git_repo(repo_dir)
    (repo_dir / "README.md").write_text("changed\n", encoding="utf-8")
    rev = manifest.git_rev(repo_dir)
    assert rev.dirty is True


def test_git_rev_raises_outside_a_repo(tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(manifest.ManifestError):
        manifest.git_rev(not_a_repo)


def _build(tmp_path, *, config_resolved=None, corpus_sha256="a" * 64, now=None):
    call_dir = Path(tempfile.mkdtemp(dir=tmp_path))
    dataset_dir = write_dataset_dir(call_dir, corpus_sha256=corpus_sha256)
    repo_dir = tmp_path / "repo"
    if not repo_dir.exists():
        init_git_repo(repo_dir)
    dataset_ref = manifest.load_dataset_ref(dataset_dir)
    code_rev = manifest.git_rev(repo_dir)
    return manifest.build_run_manifest(
        dataset_ref=dataset_ref,
        config_resolved=config_resolved if config_resolved is not None else CONFIG_RESOLVED,
        code_rev=code_rev,
        base_model=BASE_MODEL,
        versions=VERSIONS,
        now=now,
    )


def test_same_inputs_produce_same_run_id(tmp_path):
    first = _build(tmp_path, now=datetime(2026, 1, 1, tzinfo=UTC))
    second = _build(tmp_path, now=datetime(2026, 6, 1, tzinfo=UTC))

    assert first["run_id"] == second["run_id"]
    assert first["created_utc"] != second["created_utc"]


def test_different_config_produces_different_run_id(tmp_path):
    baseline = _build(tmp_path)
    changed = _build(tmp_path, config_resolved={**CONFIG_RESOLVED, "training": {"seed": 2}})

    assert baseline["run_id"] != changed["run_id"]
    assert baseline["config_sha256"] != changed["config_sha256"]


def test_different_dataset_produces_different_run_id(tmp_path):
    baseline = _build(tmp_path, corpus_sha256="a" * 64)
    changed = _build(tmp_path, corpus_sha256="b" * 64)

    assert baseline["run_id"] != changed["run_id"]


def test_run_id_excludes_outputs_and_created_utc():
    dataset_ref = manifest.DatasetRef(
        corpus_sha256="a" * 64,
        dataset_manifest_sha256="b" * 64,
        train_sha256="c" * 64,
        eval_sha256="d" * 64,
    )
    code_rev = manifest.CodeRev(sha="e" * 40, dirty=False)
    built = manifest.build_run_manifest(
        dataset_ref=dataset_ref,
        config_resolved=CONFIG_RESOLVED,
        code_rev=code_rev,
        base_model=BASE_MODEL,
        versions=VERSIONS,
    )
    assert built["outputs"] == {"checkpoints": []}
    assert "run_id" in built
    assert "created_utc" in built


def test_write_read_and_update_manifest_outputs_preserves_run_id(tmp_path):
    dataset_ref = manifest.DatasetRef(
        corpus_sha256="a" * 64,
        dataset_manifest_sha256="b" * 64,
        train_sha256="c" * 64,
        eval_sha256="d" * 64,
    )
    code_rev = manifest.CodeRev(sha="e" * 40, dirty=False)
    built = manifest.build_run_manifest(
        dataset_ref=dataset_ref,
        config_resolved=CONFIG_RESOLVED,
        code_rev=code_rev,
        base_model=BASE_MODEL,
        versions=VERSIONS,
    )
    run_dir = tmp_path / "runs" / built["run_id"]
    manifest.write_manifest(built, run_dir)

    on_disk = manifest.read_manifest(run_dir)
    assert on_disk["run_id"] == built["run_id"]
    assert on_disk["outputs"] == {"checkpoints": []}

    updated = manifest.update_manifest_outputs(
        run_dir, [{"path": str(run_dir / "checkpoint"), "sha256": "f" * 64}]
    )
    assert updated["run_id"] == built["run_id"]
    assert updated["outputs"]["checkpoints"] == [
        {"path": str(run_dir / "checkpoint"), "sha256": "f" * 64}
    ]
    reread = manifest.read_manifest(run_dir)
    assert reread["outputs"]["checkpoints"][0]["sha256"] == "f" * 64


def test_library_versions_returns_known_libraries():
    versions = manifest.library_versions()
    assert set(versions) == {"torch", "transformers", "peft", "trl", "bitsandbytes"}
    assert all(isinstance(value, str) and value for value in versions.values())
