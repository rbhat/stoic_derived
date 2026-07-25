"""End-to-end tests for evaluate.py's --run-dir path (design doc section 4.1).

Scoring-only mode, CPU-only, no torch import anywhere in this suite: a
pre-existing manifest.json (as train.py would have written) plus an
external predictions file are scored via evaluate.main(), and we assert on
the run-dir layout (C9), the manifest `evaluation` section (C7), hypothesis
pre-registration (C8), and the runs_index.jsonl append (C12). runs_index.py
already exists in this repo (written by the parallel WP2 agent) so these
assertions run for real rather than being skipped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from stoic_training import evaluate, manifest, runs_index


def _write_corpus(tmp_path):
    path = tmp_path / "dataset.jsonl"
    records = [
        {
            "video_id": "c1_intro",
            "hms": "00:00:00",
            "narration": "Instructor explains position sizing by ATR and stop distance.",
            "why": "Position sizing controls risk per trade using ATR.",
            "category": "concept",
            "label": "risk sizing",
        }
    ]
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def _write_predictions(tmp_path):
    path = tmp_path / "predictions.jsonl"
    records = [
        {
            "task": "cited_qa",
            "meta": {"video_id": "c1_intro", "hms": "00:00:00", "category": "concept"},
            "prediction": (
                "Size positions using ATR and stop distance to control risk per trade.\n"
                "Citation: c1_intro 00:00:00"
            ),
        }
    ]
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def _write_precreated_manifest(run_dir, *, run_id, config_resolved=None):
    """Mimic the manifest train.py writes before a run starts."""
    manifest_dict = {
        "run_id": run_id,
        "created_utc": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "dataset": {"corpus_sha256": "a" * 64},
        "config_sha256": "c" * 64,
        "base_model": {"repo_id": "Qwen/Qwen3-8B", "revision": "deadbeef"},
        "code_git_rev": {"sha": "d" * 40, "dirty": False},
        "versions": {},
        "outputs": {"checkpoints": []},
    }
    if config_resolved is not None:
        manifest_dict["config_resolved"] = config_resolved
    manifest.write_manifest(manifest_dict, run_dir)
    return manifest_dict


def test_run_dir_scoring_only_writes_scores_manifest_and_index(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "fixedrunid00000a"
    _write_precreated_manifest(
        run_dir, run_id="fixedrunid00000a", config_resolved={"training": {"num_train_epochs": 2}}
    )

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
        ]
    )
    assert rc == 0

    scores_path = run_dir / "evaluation" / "scores.json"
    assert scores_path.is_file()
    report = json.loads(scores_path.read_text())
    assert report["eval"]["citation_fidelity"] == 1.0

    updated_manifest = manifest.read_manifest(run_dir)
    assert updated_manifest["run_id"] == "fixedrunid00000a"  # C7: run_id unaffected

    evaluation = updated_manifest["evaluation"]
    assert evaluation["scoring_version"] == evaluate.SCORING_VERSION
    assert evaluation["params"] == {"overlap_threshold": evaluate.DEFAULT_OVERLAP_THRESHOLD}
    assert evaluation["scores"]["path"] == str(scores_path.resolve())
    assert evaluation["scores"]["sha256"] == manifest.sha256_file(scores_path)
    assert evaluation["predictions"]["path"] == str(predictions_path.resolve())
    assert evaluation["predictions"]["sha256"] == manifest.sha256_file(predictions_path)
    assert evaluation["corpus_sha256"] == manifest.sha256_file(corpus_path)
    assert evaluation["eval_set_source"] == "predictions"
    assert evaluation["eval_set_sha256"] == manifest.sha256_file(predictions_path)
    assert evaluation["metrics"]["count"] == 1
    assert "evaluated_utc" in evaluation

    index_entries = runs_index.read_index(runs_root)
    assert len(index_entries) == 1
    assert index_entries[0]["run_id"] == "fixedrunid00000a"
    assert index_entries[0]["scoring_version"] == evaluate.SCORING_VERSION
    assert index_entries[0]["corpus_sha256"] == manifest.sha256_file(corpus_path)
    # No prior run in this runs_root to diff against.
    assert index_entries[0]["knob_diff"] == {}


def test_run_dir_second_run_diffs_config_against_previous(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"

    first_run_dir = runs_root / "run-a"
    _write_precreated_manifest(
        first_run_dir, run_id="run-a", config_resolved={"training": {"num_train_epochs": 2}}
    )
    assert (
        evaluate.main(
            [
                "--predictions", str(predictions_path),
                "--corpus", str(corpus_path),
                "--run-dir", str(first_run_dir),
            ]
        )
        == 0
    )

    second_run_dir = runs_root / "run-b"
    _write_precreated_manifest(
        second_run_dir, run_id="run-b", config_resolved={"training": {"num_train_epochs": 1}}
    )
    assert (
        evaluate.main(
            [
                "--predictions", str(predictions_path),
                "--corpus", str(corpus_path),
                "--run-dir", str(second_run_dir),
            ]
        )
        == 0
    )

    index_entries = runs_index.read_index(runs_root)
    assert len(index_entries) == 2
    assert index_entries[0]["run_id"] == "run-a"
    assert index_entries[1]["run_id"] == "run-b"
    assert index_entries[1]["knob_diff"] == {"training.num_train_epochs": {"from": 2, "to": 1}}


def test_run_dir_hypothesis_set_once_and_then_kept_on_conflict(tmp_path, capsys):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-hyp"
    _write_precreated_manifest(run_dir, run_id="run-hyp")

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
            "--hypothesis", "1 epoch cuts hallucinations",
        ]
    )
    assert rc == 0
    assert manifest.read_manifest(run_dir)["hypothesis"] == "1 epoch cuts hallucinations"

    rc2 = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
            "--hypothesis", "a different, unregistered claim",
        ]
    )
    assert rc2 == 0
    # Pre-registration is kept; the later, differing --hypothesis is ignored.
    assert manifest.read_manifest(run_dir)["hypothesis"] == "1 epoch cuts hallucinations"
    captured = capsys.readouterr()
    assert "already pre-registered" in captured.out

    index_entries = runs_index.read_index(runs_root)
    assert index_entries[-1]["hypothesis"] == "1 epoch cuts hallucinations"


def test_run_dir_hypothesis_is_set_when_absent(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-hyp2"
    built = _write_precreated_manifest(run_dir, run_id="run-hyp2")
    assert "hypothesis" not in built

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
            "--hypothesis", "first registered claim",
        ]
    )
    assert rc == 0
    assert manifest.read_manifest(run_dir)["hypothesis"] == "first registered claim"


def test_run_dir_without_hypothesis_flag_leaves_manifest_hypothesis_untouched(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-nohyp"
    _write_precreated_manifest(run_dir, run_id="run-nohyp")

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
        ]
    )
    assert rc == 0
    assert "hypothesis" not in manifest.read_manifest(run_dir)


def test_run_dir_output_flag_still_wins_over_run_dir_default(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    predictions_path = _write_predictions(tmp_path)
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run-explicit-output"
    _write_precreated_manifest(run_dir, run_id="run-explicit-output")
    explicit_output = tmp_path / "elsewhere" / "scores.json"

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
            "--output", str(explicit_output),
        ]
    )
    assert rc == 0
    assert explicit_output.is_file()
    assert not (run_dir / "evaluation" / "scores.json").is_file()

    evaluation = manifest.read_manifest(run_dir)["evaluation"]
    assert evaluation["scores"]["path"] == str(explicit_output.resolve())
