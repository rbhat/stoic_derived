"""Tests for the append-only run-history index.

Pure Python, CPU-only, no GPU, no network: everything is built from
synthetic run dirs under tmp_path. No torch import anywhere in this suite.
"""

from __future__ import annotations

import json

from stoic_training import runs_index


def _entry(run_id: str, **overrides) -> dict:
    base = dict(
        run_id=run_id,
        date="2026-07-25T00:00:00+00:00",
        config_sha256="config-sha",
        knob_diff={},
        hypothesis=None,
        metrics={"count": 1, "citation_fidelity": 1.0},
        scoring_version="1",
        eval_set_sha256="eval-sha",
        corpus_sha256="corpus-sha",
    )
    base.update(overrides)
    return runs_index.build_entry(**base)


def test_append_entry_is_append_only(tmp_path):
    runs_root = tmp_path / "runs"

    path = runs_index.append_entry(runs_root, _entry("r1"))
    first_write = path.read_text(encoding="utf-8")
    assert first_write.count("\n") == 1

    runs_index.append_entry(
        runs_root, _entry("r2", knob_diff={"training.num_train_epochs": {"from": 2, "to": 1}})
    )
    second_write = path.read_text(encoding="utf-8")

    # The first line must be byte-identical after the second append -- the
    # writer must never read-modify-write existing lines.
    assert second_write.startswith(first_write)

    lines = second_write.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == "r1"
    assert json.loads(lines[1])["run_id"] == "r2"


def test_read_index_missing_file_returns_empty_list(tmp_path):
    assert runs_index.read_index(tmp_path / "runs") == []


def test_last_entry_missing_file_returns_none(tmp_path):
    assert runs_index.last_entry(tmp_path / "runs") is None


def test_last_entry_returns_most_recent_line(tmp_path):
    runs_root = tmp_path / "runs"
    runs_index.append_entry(runs_root, _entry("r1"))
    runs_index.append_entry(runs_root, _entry("r2"))
    assert runs_index.last_entry(runs_root)["run_id"] == "r2"


def test_flatten_config_dotted_keys_and_whole_lists():
    config = {
        "training": {"num_train_epochs": 2, "lr": 0.0002},
        "model": {"repo_id": "some/repo"},
        "tags": ["a", "b"],
    }
    flat = runs_index.flatten_config(config)
    assert flat == {
        "training.num_train_epochs": 2,
        "training.lr": 0.0002,
        "model.repo_id": "some/repo",
        "tags": ["a", "b"],
    }


def test_flatten_config_deep_nesting():
    config = {"a": {"b": {"c": 1}}}
    assert runs_index.flatten_config(config) == {"a.b.c": 1}


def test_diff_configs_none_side_returns_empty_dict():
    assert runs_index.diff_configs(None, {"a": 1}) == {}
    assert runs_index.diff_configs({"a": 1}, None) == {}
    assert runs_index.diff_configs(None, None) == {}


def test_diff_configs_added_removed_and_changed():
    previous = {"training": {"num_train_epochs": 2, "old_only": 1}}
    current = {"training": {"num_train_epochs": 1, "new_only": 2}}

    diff = runs_index.diff_configs(previous, current)

    assert diff == {
        "training.num_train_epochs": {"from": 2, "to": 1},
        "training.old_only": {"from": 1, "to": None},
        "training.new_only": {"from": None, "to": 2},
    }


def test_diff_configs_unchanged_keys_are_omitted():
    previous = {"training": {"num_train_epochs": 2}}
    current = {"training": {"num_train_epochs": 2}}
    assert runs_index.diff_configs(previous, current) == {}


def test_previous_config_resolved_happy_path(tmp_path):
    runs_root = tmp_path / "runs"
    runs_index.append_entry(runs_root, _entry("r1"))
    run_dir = runs_root / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "r1", "config_resolved": {"training": {"lr": 1}}}),
        encoding="utf-8",
    )

    assert runs_index.previous_config_resolved(runs_root) == {"training": {"lr": 1}}


def test_previous_config_resolved_missing_index_returns_none(tmp_path):
    assert runs_index.previous_config_resolved(tmp_path / "runs") is None


def test_previous_config_resolved_missing_manifest_returns_none(tmp_path):
    runs_root = tmp_path / "runs"
    runs_index.append_entry(runs_root, _entry("r1"))
    # Deliberately no runs_root/r1 directory at all.
    assert runs_index.previous_config_resolved(runs_root) is None


def test_previous_config_resolved_malformed_manifest_json_returns_none(tmp_path):
    runs_root = tmp_path / "runs"
    runs_index.append_entry(runs_root, _entry("r1"))
    run_dir = runs_root / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")

    assert runs_index.previous_config_resolved(runs_root) is None


def test_previous_config_resolved_absent_config_resolved_returns_none(tmp_path):
    runs_root = tmp_path / "runs"
    runs_index.append_entry(runs_root, _entry("r1"))
    run_dir = runs_root / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")

    assert runs_index.previous_config_resolved(runs_root) is None


def test_build_entry_key_set():
    entry = _entry("r1", knob_diff={"a": {"from": 1, "to": 2}}, hypothesis="try 1 epoch")
    assert set(entry) == {
        "run_id",
        "date",
        "config_sha256",
        "knob_diff",
        "hypothesis",
        "metrics",
        "scoring_version",
        "eval_set_sha256",
        "corpus_sha256",
    }
    assert entry["hypothesis"] == "try 1 epoch"
    assert entry["knob_diff"] == {"a": {"from": 1, "to": 2}}
