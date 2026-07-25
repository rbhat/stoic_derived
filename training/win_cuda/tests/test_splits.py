"""Tests for splits.py: dev/holdout partitioning, sealing, quarantine, ledger.

Pure stdlib, CPU-only, no torch import anywhere in this suite. Synthetic
split files are built under tmp_path so the tests never depend on (or
mutate) the committed training/win_cuda/splits/ directory -- except for one
read-only reproducibility check against the committed split-v2.json, which
never writes to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from stoic_training import splits

# --------------------------------------------------------------------------
# partition_eval_videos
# --------------------------------------------------------------------------


def test_partition_eval_videos_is_deterministic_across_calls():
    videos = ["vid_a", "vid_b", "vid_c"]
    dev1, holdout1 = splits.partition_eval_videos(videos)
    dev2, holdout2 = splits.partition_eval_videos(videos)
    assert (dev1, holdout1) == (dev2, holdout2)


def test_partition_eval_videos_three_videos_is_two_dev_one_holdout():
    videos = ["vid_a", "vid_b", "vid_c"]
    dev, holdout = splits.partition_eval_videos(videos)
    assert len(dev) == 2
    assert len(holdout) == 1


def test_partition_eval_videos_dev_plus_holdout_equals_input():
    videos = ["vid_a", "vid_b", "vid_c", "vid_d", "vid_e"]
    dev, holdout = splits.partition_eval_videos(videos)
    assert sorted(dev) + sorted(holdout) != []  # sanity: non-trivial
    assert set(dev) | set(holdout) == set(videos)
    assert set(dev) & set(holdout) == set()


def test_partition_eval_videos_input_order_does_not_matter():
    videos = ["vid_a", "vid_b", "vid_c", "vid_d"]
    dev_fwd, holdout_fwd = splits.partition_eval_videos(videos)
    dev_rev, holdout_rev = splits.partition_eval_videos(list(reversed(videos)))
    assert dev_fwd == dev_rev
    assert holdout_fwd == holdout_rev


def test_partition_eval_videos_dev_never_empty_for_two_videos():
    dev, holdout = splits.partition_eval_videos(["vid_a", "vid_b"])
    assert len(dev) == 1
    assert len(holdout) == 1


def test_partition_eval_videos_explicit_holdout_target_respected():
    videos = ["vid_a", "vid_b", "vid_c", "vid_d", "vid_e"]
    dev, holdout = splits.partition_eval_videos(videos, holdout_target=2)
    assert len(holdout) == 2
    assert len(dev) == 3


def test_partition_eval_videos_explicit_holdout_target_capped_at_n_minus_1():
    videos = ["vid_a", "vid_b", "vid_c"]
    dev, holdout = splits.partition_eval_videos(videos, holdout_target=10)
    assert len(holdout) == len(videos) - 1
    assert len(dev) == 1


# --------------------------------------------------------------------------
# committed split-v2.json reproducibility (read-only)
# --------------------------------------------------------------------------


def test_committed_split_v2_is_reproducible_from_committed_split_v1():
    v1 = json.loads(splits.DEFAULT_SPLIT_V1_PATH.read_text(encoding="utf-8"))
    committed_v2 = json.loads(splits.DEFAULT_SPLIT_V2_PATH.read_text(encoding="utf-8"))

    payload = splits.build_split_v2_payload(parent=v1, parent_file="split-v1.json")

    for key, value in payload.items():
        assert committed_v2[key] == value, f"committed split-v2.json disagrees on {key!r}"


def test_committed_split_v2_load_yields_expected_dev_and_holdout():
    loaded = splits.load_split_v2(splits.DEFAULT_SPLIT_V2_PATH)
    assert loaded.dev_videos == ("cs_vol3_gold_futures_study", "live_4_14r_on_nq")
    assert loaded.holdout_videos == ("concept_simple_stoic_setups_sss",)


def test_committed_split_v2_train_videos_match_v1_exactly():
    v1 = json.loads(splits.DEFAULT_SPLIT_V1_PATH.read_text(encoding="utf-8"))
    loaded = splits.load_split_v2(splits.DEFAULT_SPLIT_V2_PATH)
    assert list(loaded.train_videos) == sorted(v1["train_videos"])
    assert set(loaded.train_videos) == set(v1["train_videos"])


# --------------------------------------------------------------------------
# load_split_v2 validation failures
# --------------------------------------------------------------------------


def _write_parent(tmp_path: Path, **overrides) -> Path:
    parent = {
        "version": "v1",
        "seed": 1,
        "corpus_sha256": "a" * 64,
        "train_videos": ["t1", "t2"],
        "eval_videos": ["e1", "e2", "e3"],
    }
    parent.update(overrides)
    path = tmp_path / "split-v1.json"
    path.write_text(json.dumps(parent), encoding="utf-8")
    return path


def _write_child(tmp_path: Path, name: str = "split-v2.json", **overrides) -> Path:
    child = {
        "version": "v2",
        "parent_split": "v1",
        "parent_split_file": "split-v1.json",
        "seed": 2,
        "corpus_sha256": "a" * 64,
        "dev_videos": ["e1", "e2"],
        "holdout_videos": ["e3"],
    }
    child.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(child), encoding="utf-8")
    return path


def test_load_split_v2_missing_parent_split_file_key_raises(tmp_path):
    _write_parent(tmp_path)
    child = _write_child(tmp_path)
    payload = json.loads(child.read_text(encoding="utf-8"))
    del payload["parent_split_file"]
    child.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(splits.SplitError):
        splits.load_split_v2(child)


def test_load_split_v2_absent_parent_file_raises(tmp_path):
    # No split-v1.json written at all.
    child = _write_child(tmp_path, parent_split_file="does-not-exist.json")

    with pytest.raises(splits.SplitError):
        splits.load_split_v2(child)


def test_load_split_v2_dev_holdout_overlap_raises(tmp_path):
    _write_parent(tmp_path)
    child = _write_child(tmp_path, dev_videos=["e1", "e2"], holdout_videos=["e2", "e3"])

    with pytest.raises(splits.SplitError):
        splits.load_split_v2(child)


def test_load_split_v2_dev_plus_holdout_not_equal_parent_eval_raises(tmp_path):
    _write_parent(tmp_path)
    # Drop e3, add an unrelated video not in the parent's eval_videos at all.
    child = _write_child(tmp_path, dev_videos=["e1"], holdout_videos=["e2", "not_an_eval_video"])

    with pytest.raises(splits.SplitError):
        splits.load_split_v2(child)


def test_load_split_v2_corpus_sha256_mismatch_raises(tmp_path):
    _write_parent(tmp_path, corpus_sha256="a" * 64)
    child = _write_child(tmp_path, corpus_sha256="b" * 64)

    with pytest.raises(splits.SplitError):
        splits.load_split_v2(child)


# --------------------------------------------------------------------------
# quarantine_new_videos
# --------------------------------------------------------------------------


def _synthetic_split() -> splits.SplitV2:
    return splits.SplitV2(
        version="v2",
        parent_version="v1",
        parent_path=Path("/nonexistent/split-v1.json"),
        seed=1,
        corpus_sha256="a" * 64,
        train_videos=("t1", "t2"),
        dev_videos=("d1",),
        holdout_videos=("h1",),
    )


def test_quarantine_new_videos_returns_sorted_unknown_videos():
    split = _synthetic_split()
    quarantined = splits.quarantine_new_videos(
        ["t1", "t2", "d1", "h1", "new_z", "new_a"], split
    )
    assert quarantined == ["new_a", "new_z"]


def test_quarantine_new_videos_empty_when_all_known():
    split = _synthetic_split()
    quarantined = splits.quarantine_new_videos(["t1", "t2", "d1", "h1"], split)
    assert quarantined == []


# --------------------------------------------------------------------------
# detect_holdout
# --------------------------------------------------------------------------


def test_detect_holdout_detects_via_manifest_content_sha256(tmp_path):
    eval_path = tmp_path / "somefile.jsonl"
    eval_path.write_text('{"a": 1}\n', encoding="utf-8")
    digest = splits.sha256_file(eval_path)
    manifest_path = tmp_path / splits.DATASET_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"files": {"somefile.jsonl": {"role": "holdout", "sha256": digest}}}),
        encoding="utf-8",
    )

    detection = splits.detect_holdout(eval_path)
    assert detection is not None
    assert detection.sha256 == digest


def test_detect_holdout_still_detects_after_rename_content_based(tmp_path):
    eval_path = tmp_path / "somefile.jsonl"
    eval_path.write_text('{"a": 1}\n', encoding="utf-8")
    digest = splits.sha256_file(eval_path)
    manifest_path = tmp_path / splits.DATASET_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"files": {"somefile.jsonl": {"role": "holdout", "sha256": digest}}}),
        encoding="utf-8",
    )

    renamed_path = tmp_path / "renamed_notes.jsonl"
    eval_path.rename(renamed_path)

    detection = splits.detect_holdout(renamed_path)
    assert detection is not None
    assert detection.sha256 == digest


def test_detect_holdout_filename_backstop_with_no_manifest(tmp_path):
    away = tmp_path / "away"
    away.mkdir()
    eval_holdout = away / "eval_holdout.jsonl"
    eval_holdout.write_text('{"a": 1}\n', encoding="utf-8")
    # Deliberately no dataset_manifest.json beside it.

    detection = splits.detect_holdout(eval_holdout)
    assert detection is not None
    assert detection.manifest_path is None


def test_detect_holdout_none_for_dev_file_with_dev_role_manifest(tmp_path):
    eval_path = tmp_path / "eval_dev.jsonl"
    eval_path.write_text('{"a": 1}\n', encoding="utf-8")
    digest = splits.sha256_file(eval_path)
    manifest_path = tmp_path / splits.DATASET_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"files": {"eval_dev.jsonl": {"role": "dev", "sha256": digest}}}),
        encoding="utf-8",
    )

    assert splits.detect_holdout(eval_path) is None


def test_detect_holdout_none_for_nonexistent_path_and_for_none(tmp_path):
    assert splits.detect_holdout(tmp_path / "does-not-exist.jsonl") is None
    assert splits.detect_holdout(None) is None


def test_detect_holdout_tolerates_malformed_manifest_without_raising(tmp_path):
    eval_path = tmp_path / "somefile.jsonl"
    eval_path.write_text('{"a": 1}\n', encoding="utf-8")
    manifest_path = tmp_path / splits.DATASET_MANIFEST_NAME
    manifest_path.write_text("not valid json {{{", encoding="utf-8")

    # No exception, and no holdout name either -> None.
    assert splits.detect_holdout(eval_path) is None


# --------------------------------------------------------------------------
# unseal ledger
# --------------------------------------------------------------------------


def test_ensure_unseal_ledger_creates_header_when_absent(tmp_path):
    ledger_path = tmp_path / "unseal-ledger.md"
    assert not ledger_path.exists()

    returned = splits.ensure_unseal_ledger(ledger_path)

    assert returned == ledger_path
    assert ledger_path.is_file()
    assert ledger_path.read_text(encoding="utf-8").startswith("# Unseal ledger")


def test_ensure_unseal_ledger_does_not_rewrite_existing_file(tmp_path):
    ledger_path = tmp_path / "unseal-ledger.md"
    ledger_path.write_text("pre-existing content, not the header\n", encoding="utf-8")

    splits.ensure_unseal_ledger(ledger_path)

    assert ledger_path.read_text(encoding="utf-8") == "pre-existing content, not the header\n"


def test_count_unseal_entries_zero_for_fresh_header_only_ledger(tmp_path):
    ledger_path = tmp_path / "unseal-ledger.md"
    splits.ensure_unseal_ledger(ledger_path)
    assert splits.count_unseal_entries(ledger_path) == 0


def test_append_unseal_entry_appends_rows_and_count_matches(tmp_path):
    ledger_path = tmp_path / "unseal-ledger.md"
    splits.append_unseal_entry(
        run_id="run-1",
        reason="promoting release candidate",
        eval_set="/path/to/eval_holdout.jsonl",
        date="2026-07-25T00:00:00+00:00",
        ledger_path=ledger_path,
    )
    assert splits.count_unseal_entries(ledger_path) == 1

    splits.append_unseal_entry(
        run_id="run-2",
        reason="second look",
        eval_set="/path/to/eval_holdout.jsonl",
        date="2026-07-25T01:00:00+00:00",
        ledger_path=ledger_path,
    )
    assert splits.count_unseal_entries(ledger_path) == 2


def test_append_unseal_entry_escapes_pipes_and_newlines_in_reason(tmp_path):
    ledger_path = tmp_path / "unseal-ledger.md"
    reason = "multi\nline reason | with a pipe"
    splits.append_unseal_entry(
        run_id="run-1",
        reason=reason,
        eval_set="/path/to/eval_holdout.jsonl",
        ledger_path=ledger_path,
    )

    # Exactly one data row despite the embedded newline and pipe.
    assert splits.count_unseal_entries(ledger_path) == 1
    text = ledger_path.read_text(encoding="utf-8")
    assert "\\|" in text
    assert "multi line reason" in text
