"""Tests for kfold.py: fold assignment, plan emission, fold-run aggregation.

Pure stdlib, CPU-only, no GPU, no network: every artifact (corpus, split
files, fold plans, synthetic run dirs) is built under tmp_path. No torch
import anywhere in this suite. The GPU-launching half of kfold.py
(commands.sh) is asserted to be inert -- written, never executed.
"""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from stoic_training import kfold, splits
from stoic_training.config import load_config

# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------

BASE_CONFIG_TEXT = """\
# Test QLoRA config fixture (mirrors config/qlora.yaml's schema).
model:
  repo_id: "Qwen/Qwen3-8B"
  revision: null

quantization:
  load_in_4bit: true
  bnb_4bit_quant_type: "nf4"
  bnb_4bit_compute_dtype: "bfloat16"
  bnb_4bit_use_double_quant: true

lora:
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj

training:
  max_seq_len: 1024
  per_device_train_batch_size: 1
  per_device_eval_batch_size: 2
  gradient_accumulation_steps: 16
  gradient_checkpointing: true
  optim: "paged_adamw_8bit"
  learning_rate: 0.0002
  lr_scheduler_type: "cosine"
  warmup_ratio: 0.03
  num_train_epochs: 2
  seed: 20260724
  logging_steps: 10
  save_steps: 50
  save_total_limit: 2
  eval_steps: 200
  attn_implementation: "sdpa"
  bf16: true

paths:
  # This comment must survive the dataset_dir rewrite.
  dataset_dir: "${STOIC_TRAIN_HOME}/datasets/v1"
  run_dir: "${STOIC_TRAIN_HOME}/runs"

smoke:
  max_steps: 10
  max_seq_len: 512

resources:
  min_free_vram_gib: 10.0
  export_gpu_cap_gib: 12.0
  export_vram_headroom_gib: 2.0
  export_cpu_reserve_gib: 4.0
  dataloader_num_workers: 0
  dataloader_pin_memory: false
"""


def _cpu_only_env() -> dict:
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def _write_corpus(
    tmp_path: Path, videos: list[tuple[str, str]], *, name: str = "corpus.jsonl"
) -> Path:
    """One minimal record per (video_id, category); enough for video_inventory."""
    path = tmp_path / name
    lines = [json.dumps({"video_id": vid, "category": cat}) for vid, cat in videos]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_config(tmp_path: Path, *, name: str = "qlora.yaml") -> Path:
    path = tmp_path / name
    path.write_text(BASE_CONFIG_TEXT, encoding="utf-8")
    return path


def _write_split_v1(
    tmp_path: Path, *, train_videos: list[str], eval_videos: list[str], corpus_sha256: str
) -> Path:
    path = tmp_path / "split-v1.json"
    path.write_text(
        json.dumps(
            {
                "version": "v1",
                "seed": 1,
                "corpus_sha256": corpus_sha256,
                "train_videos": train_videos,
                "eval_videos": eval_videos,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_split_v2(
    tmp_path: Path, *, dev_videos: list[str], holdout_videos: list[str], corpus_sha256: str
) -> Path:
    path = tmp_path / "split-v2.json"
    path.write_text(
        json.dumps(
            {
                "version": "v2",
                "parent_split": "v1",
                "parent_split_file": "split-v1.json",
                "seed": 2,
                "corpus_sha256": corpus_sha256,
                "dev_videos": dev_videos,
                "holdout_videos": holdout_videos,
            }
        ),
        encoding="utf-8",
    )
    return path


def _balanced_inventory(n_categories: int = 4, per_category: int = 6) -> dict[str, str]:
    inventory = {}
    for c in range(n_categories):
        for i in range(per_category):
            inventory[f"cat{c}_vid{i}"] = f"category{c}"
    return inventory


# --------------------------------------------------------------------------
# 1. determinism
# --------------------------------------------------------------------------


def test_assign_folds_deterministic_same_seed_same_k():
    inventory = _balanced_inventory()
    a = kfold.assign_folds(inventory, k=5, seed=42)
    b = kfold.assign_folds(inventory, k=5, seed=42)
    assert a == b


def test_assign_folds_different_seed_gives_different_assignment():
    inventory = _balanced_inventory()
    a = kfold.assign_folds(inventory, k=5, seed=42)
    b = kfold.assign_folds(inventory, k=5, seed=43)
    assert a != b


# --------------------------------------------------------------------------
# 2. partition property
# --------------------------------------------------------------------------


def test_assign_folds_is_a_partition_with_balanced_sizes():
    inventory = _balanced_inventory(n_categories=3, per_category=7)  # 21 videos
    folds = kfold.assign_folds(inventory, k=5, seed=7)

    assert len(folds) == 5
    union: set[str] = set()
    for fold in folds:
        assert fold, "no fold may be empty"
        union.update(fold)
    assert union == set(inventory)
    assert sum(len(fold) for fold in folds) == len(inventory)

    sizes = sorted(len(fold) for fold in folds)
    assert sizes[-1] - sizes[0] <= 1


# --------------------------------------------------------------------------
# 3. no leakage (via build_plan, which computes train_videos = inventory - fold)
# --------------------------------------------------------------------------


def test_build_plan_folds_have_no_train_eval_leakage(tmp_path):
    videos = [(f"v{i}", "concept" if i % 2 == 0 else "case_study") for i in range(12)]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = _write_config(tmp_path)
    missing_split_v2 = tmp_path / "no-split-v2.json"

    plan = kfold.build_plan(
        corpus_path=corpus_path,
        k=4,
        seed=99,
        base_config_path=config_path,
        split_v2_path=missing_split_v2,
        out_dir=tmp_path / "plan-out",
    )

    all_video_ids = {vid for vid, _ in videos}
    for fold in plan["folds"]:
        eval_set = set(fold["eval_videos"])
        train_set = set(fold["train_videos"])
        assert eval_set & train_set == set()
        assert eval_set | train_set == all_video_ids


# --------------------------------------------------------------------------
# 4. stratification
# --------------------------------------------------------------------------


def test_category_coverage_balanced_inventory_every_fold_has_every_category():
    inventory = _balanced_inventory(n_categories=3, per_category=5)  # 15 videos
    folds = kfold.assign_folds(inventory, k=5, seed=11)
    coverage = kfold.category_coverage(inventory, folds)

    assert set(coverage) == {"category0", "category1", "category2"}
    for counts in coverage.values():
        assert counts == [1, 1, 1, 1, 1]

    limits = kfold.known_limits(inventory, folds, k=5)
    assert not any("fewer than k videos" in limit for limit in limits)


def test_known_limits_names_under_covered_categories():
    inventory = dict(_balanced_inventory(n_categories=2, per_category=5))
    inventory["rare_vid_a"] = "rare_category"
    inventory["rare_vid_b"] = "rare_category"

    folds = kfold.assign_folds(inventory, k=5, seed=11)
    limits = kfold.known_limits(inventory, folds, k=5)

    matches = [limit for limit in limits if "fewer than k videos" in limit]
    assert len(matches) == 1
    assert "rare_category" in matches[0]
    assert "category0" not in matches[0]


# --------------------------------------------------------------------------
# 5. refusals: k < 2, k > n, empty inventory
# --------------------------------------------------------------------------


def test_assign_folds_refuses_k_less_than_2():
    with pytest.raises(kfold.KFoldRefusal):
        kfold.assign_folds({"a": "cat"}, k=1, seed=1)


def test_assign_folds_refuses_k_greater_than_inventory_size():
    inventory = {"a": "cat", "b": "cat"}
    with pytest.raises(kfold.KFoldRefusal):
        kfold.assign_folds(inventory, k=3, seed=1)


def test_assign_folds_refuses_empty_inventory():
    with pytest.raises(kfold.KFoldRefusal):
        kfold.assign_folds({}, k=2, seed=1)


# --------------------------------------------------------------------------
# 6. sealed-holdout exclusion
# --------------------------------------------------------------------------


def _holdout_scenario(tmp_path: Path):
    videos = [
        ("c1", "concept"), ("c2", "concept"), ("c3", "concept"),
        ("s1", "case_study"), ("s2", "case_study"), ("s3", "case_study"),
    ]
    corpus_path = _write_corpus(tmp_path, videos)
    corpus_sha256 = "does-not-need-to-match-split-digest"
    _write_split_v1(
        tmp_path,
        train_videos=["c1", "c2", "s1", "s2"],
        eval_videos=["c3", "s3"],
        corpus_sha256=corpus_sha256,
    )
    split_v2_path = _write_split_v2(
        tmp_path, dev_videos=["s3"], holdout_videos=["c3"], corpus_sha256=corpus_sha256
    )
    config_path = _write_config(tmp_path)
    return corpus_path, split_v2_path, config_path


def test_resolve_inventory_excludes_holdout_by_default(tmp_path):
    videos = [
        ("c1", "concept"), ("c2", "concept"), ("c3", "concept"),
        ("s1", "case_study"), ("s2", "case_study"), ("s3", "case_study"),
    ]
    corpus_path = _write_corpus(tmp_path, videos)
    records, _ = kfold.load_corpus(corpus_path)
    corpus_sha256 = "x"
    _write_split_v1(
        tmp_path,
        train_videos=["c1", "c2", "s1", "s2"],
        eval_videos=["c3", "s3"],
        corpus_sha256=corpus_sha256,
    )
    split_v2_path = _write_split_v2(
        tmp_path, dev_videos=["s3"], holdout_videos=["c3"], corpus_sha256=corpus_sha256
    )

    resolution = kfold.resolve_inventory(
        records, split_v2_path=split_v2_path, include_holdout=False
    )

    assert "c3" not in resolution.inventory
    assert resolution.excluded_video_ids == ("c3",)
    assert set(resolution.inventory) == {"c1", "c2", "s1", "s2", "s3"}
    assert resolution.forced_inclusion is False


def test_build_plan_excludes_holdout_video_from_every_fold(tmp_path):
    corpus_path, split_v2_path, config_path = _holdout_scenario(tmp_path)

    plan = kfold.build_plan(
        corpus_path=corpus_path,
        k=5,
        seed=5,
        base_config_path=config_path,
        split_v2_path=split_v2_path,
        out_dir=tmp_path / "plan-out",
    )

    assert plan["excluded_holdout_videos"] == ["c3"]
    for fold in plan["folds"]:
        assert "c3" not in fold["eval_videos"]
        assert "c3" not in fold["train_videos"]


def test_build_plan_include_holdout_puts_it_back_and_warns_loudly(tmp_path):
    corpus_path, split_v2_path, config_path = _holdout_scenario(tmp_path)

    plan = kfold.build_plan(
        corpus_path=corpus_path,
        k=5,
        seed=5,
        base_config_path=config_path,
        split_v2_path=split_v2_path,
        include_holdout=True,
        out_dir=tmp_path / "plan-out-included",
    )

    assert plan["excluded_holdout_videos"] == []
    assert plan["holdout_forced_inclusion"] is True
    assert any("LOUD WARNING" in limit for limit in plan["known_limits"])
    all_eval_videos = {vid for fold in plan["folds"] for vid in fold["eval_videos"]}
    assert "c3" in all_eval_videos


def test_resolve_inventory_missing_split_v2_proceeds_with_full_inventory(tmp_path):
    videos = [("v1", "concept"), ("v2", "concept")]
    corpus_path = _write_corpus(tmp_path, videos)
    records, _ = kfold.load_corpus(corpus_path)

    resolution = kfold.resolve_inventory(
        records, split_v2_path=tmp_path / "does-not-exist.json", include_holdout=False
    )

    assert set(resolution.inventory) == {"v1", "v2"}
    assert resolution.excluded_video_ids == ()
    assert "not found" in resolution.note


# --------------------------------------------------------------------------
# 7. plan emission
# --------------------------------------------------------------------------


def _build_small_plan(tmp_path, *, config_text: str = BASE_CONFIG_TEXT):
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    videos = [(f"v{i}", "concept" if i % 2 == 0 else "case_study") for i in range(6)]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = tmp_path / "qlora.yaml"
    config_path.write_text(config_text, encoding="utf-8")
    return kfold.build_plan(
        corpus_path=corpus_path,
        k=3,
        seed=7,
        base_config_path=config_path,
        split_v2_path=tmp_path / "no-split-v2.json",
        out_dir=tmp_path / "plan-out",
    )


def test_fold_evaluate_command_pins_the_base_revision(tmp_path):
    """The emitted evaluate command must pin the same base revision the fold
    trained against: evaluate.py loads the base model itself for a LoRA
    checkpoint, and an unpinned --base-repo-id silently resolves to whatever
    the hub's default branch points at on the day it is run."""
    pinned = BASE_CONFIG_TEXT.replace('revision: null', 'revision: "abc123def456"')
    plan = _build_small_plan(tmp_path, config_text=pinned)

    for fold in plan["folds"]:
        command = fold["commands"]["evaluate"]
        assert "--base-revision" in command
        assert command[command.index("--base-revision") + 1] == "abc123def456"
        # the revision must not be mistaken for the repo id
        assert command[command.index("--base-repo-id") + 1] == "Qwen/Qwen3-8B"


def test_fold_evaluate_command_omits_revision_when_config_is_unpinned(tmp_path):
    """A `revision: null` config must omit the flag entirely rather than pass
    the literal string "null" through to evaluate.py."""
    plan = _build_small_plan(tmp_path)

    for fold in plan["folds"]:
        command = fold["commands"]["evaluate"]
        assert "--base-revision" not in command
        assert "null" not in command


@pytest.mark.parametrize(
    ("revision_line", "expected"),
    [
        ('revision: "abc123"', "abc123"),
        ("revision: abc123", "abc123"),
        ("revision: null", None),
        ("revision: ~", None),
    ],
)
def test_extract_revision_table(revision_line, expected):
    text = BASE_CONFIG_TEXT.replace("revision: null", revision_line)
    assert kfold._extract_revision(text) == expected


def test_plan_id_ignores_the_base_config_so_configs_share_a_fold_geometry(tmp_path):
    """plan_id identifies the fold GEOMETRY, not the config: comparing two
    configs over the SAME folds is the entire point of the tool."""
    plan_a = _build_small_plan(tmp_path / "a")
    other_config = BASE_CONFIG_TEXT.replace("num_train_epochs: 2", "num_train_epochs: 1")
    plan_b = _build_small_plan(tmp_path / "b", config_text=other_config)

    assert plan_a["plan_id"] == plan_b["plan_id"]
    assert [fold["eval_videos"] for fold in plan_a["folds"]] == [
        fold["eval_videos"] for fold in plan_b["folds"]
    ]


def test_write_plan_creates_expected_files_and_valid_content(tmp_path):
    videos = [(f"v{i}", "concept" if i % 2 == 0 else "case_study") for i in range(10)]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = _write_config(tmp_path)
    out_dir = tmp_path / "plan-out"

    plan = kfold.build_plan(
        corpus_path=corpus_path,
        k=3,
        seed=123,
        base_config_path=config_path,
        split_v2_path=tmp_path / "no-split-v2.json",
        out_dir=out_dir,
    )
    written_dir = kfold.write_plan(plan, out_dir, base_config_text=BASE_CONFIG_TEXT)
    assert written_dir == out_dir

    plan_path = out_dir / "plan.json"
    assert plan_path.is_file()
    on_disk = json.loads(plan_path.read_text(encoding="utf-8"))
    assert on_disk["plan_id"] == plan["plan_id"]

    commands_path = out_dir / "commands.sh"
    assert commands_path.is_file()
    mode = stat.S_IMODE(commands_path.stat().st_mode)
    assert mode == 0o644
    assert not os.access(commands_path, os.X_OK)
    commands_text = commands_path.read_text(encoding="utf-8")
    assert "LAUNCHES GPU WORK" in commands_text
    assert "does NOT execute" in commands_text

    for fold in plan["folds"]:
        split_path = Path(fold["split_file"])
        assert split_path.is_file()
        split_payload = json.loads(split_path.read_text(encoding="utf-8"))
        assert splits.is_split_v2(split_payload) is False
        assert split_payload["train_videos"] == fold["train_videos"]
        assert split_payload["eval_videos"] == fold["eval_videos"]

        config_file = Path(fold["config_file"])
        assert config_file.is_file()
        parsed = load_config(config_file)
        assert parsed.paths.dataset_dir == Path(fold["dataset_dir"])


def test_build_plan_is_idempotent_except_generated_utc(tmp_path):
    videos = [(f"v{i}", "concept" if i % 2 == 0 else "case_study") for i in range(10)]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = _write_config(tmp_path)

    kwargs = {
        "corpus_path": corpus_path,
        "k": 3,
        "seed": 123,
        "base_config_path": config_path,
        "split_v2_path": tmp_path / "no-split-v2.json",
        "out_dir": tmp_path / "plan-out",
    }
    plan_a = kfold.build_plan(**kwargs)
    plan_b = kfold.build_plan(**kwargs)

    assert plan_a["plan_id"] == plan_b["plan_id"]
    plan_a.pop("generated_utc")
    plan_b.pop("generated_utc")
    assert plan_a == plan_b


def test_write_plan_out_dir_mismatch_raises(tmp_path):
    videos = [("v1", "concept"), ("v2", "concept"), ("v3", "case_study")]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = _write_config(tmp_path)

    plan = kfold.build_plan(
        corpus_path=corpus_path,
        k=2,
        seed=1,
        base_config_path=config_path,
        split_v2_path=tmp_path / "no-split-v2.json",
        out_dir=tmp_path / "expected-dir",
    )

    with pytest.raises(kfold.KFoldError):
        kfold.write_plan(plan, tmp_path / "wrong-dir", base_config_text=BASE_CONFIG_TEXT)


# --------------------------------------------------------------------------
# 8. aggregation math
# --------------------------------------------------------------------------


def _write_fold_run(
    tmp_path: Path,
    name: str,
    eval_scores: dict,
    *,
    scoring_version: str = "1",
    corpus_sha256: str = "corpus-x",
    eval_set_sha256: str = "eval-default",
    plan_id: str | None = None,
    with_evaluation: bool = True,
) -> Path:
    run_dir = tmp_path / "runs" / name
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    scores_path = eval_dir / "scores.json"
    scores_path.write_text(json.dumps({"eval": eval_scores}), encoding="utf-8")

    manifest: dict = {"run_id": name}
    if plan_id is not None:
        manifest["plan_id"] = plan_id
    if with_evaluation:
        manifest["evaluation"] = {
            "scoring_version": scoring_version,
            "corpus_sha256": corpus_sha256,
            "eval_set_sha256": eval_set_sha256,
            "scores": {"path": str(scores_path), "sha256": "deadbeef"},
        }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def test_aggregate_folds_hand_checked_statistics(tmp_path):
    fold0 = _write_fold_run(
        tmp_path,
        "fold0",
        {
            "count": 10,
            "citation_fidelity": 0.8,
            "conflict_handling": 0.5,
            "bucket_rates": {"pass": 0.8, "no_citation": 0.1},
            "conflict_bucket_rates": {"pass": 0.9},
            "per_task": {
                "cited_qa": {"count": 8, "pass_rate": 0.8},
                "conflict_check": {"count": 2, "pass_rate": 1.0},
            },
        },
        eval_set_sha256="eval-0",
        plan_id="planABC",
    )
    fold1 = _write_fold_run(
        tmp_path,
        "fold1",
        {
            "count": 8,
            "citation_fidelity": 0.6,
            "conflict_handling": 0.5,
            "bucket_rates": {"pass": 0.6, "no_citation": 0.2},
            "conflict_bucket_rates": {"pass": 0.9},
            "per_task": {
                "cited_qa": {"count": 6, "pass_rate": 0.6},
                "conflict_check": {"count": 2, "pass_rate": 1.0},
            },
        },
        eval_set_sha256="eval-1",
        plan_id="planABC",
    )
    fold2 = _write_fold_run(
        tmp_path,
        "fold2",
        {
            "count": 6,
            "citation_fidelity": None,
            "conflict_handling": 0.5,
            "bucket_rates": {},
            "conflict_bucket_rates": {"pass": 0.9},
            "per_task": {"cited_qa": {"count": 0, "pass_rate": None}},
        },
        eval_set_sha256="eval-2",
        plan_id="planABC",
    )

    result = kfold.aggregate_folds([fold0, fold1, fold2])

    assert result["k"] == 3
    assert result["scoring_version"] == "1"
    assert result["corpus_sha256"] == "corpus-x"
    assert result["plan_id"] == "planABC"

    metrics = result["metrics"]

    cf = metrics["citation_fidelity"]
    assert cf["n"] == 2
    assert cf["values"] == [0.8, 0.6, None]
    assert cf["mean"] == pytest.approx(0.7)
    assert cf["std"] == pytest.approx(math.sqrt(0.02))
    assert cf["min"] == pytest.approx(0.6)
    assert cf["max"] == pytest.approx(0.8)

    ch = metrics["conflict_handling"]
    assert ch["n"] == 3
    assert ch["mean"] == pytest.approx(0.5)
    assert ch["std"] == pytest.approx(0.0)

    count = metrics["count"]
    assert count["n"] == 3
    assert count["mean"] == pytest.approx(8.0)
    assert count["std"] == pytest.approx(2.0)
    assert count["min"] == 6
    assert count["max"] == 10

    bucket_pass = metrics["bucket_rates.pass"]
    assert bucket_pass["n"] == 2  # fold2 has no "pass" key at all
    assert bucket_pass["values"] == [0.8, 0.6, None]
    assert bucket_pass["mean"] == pytest.approx(0.7)
    assert bucket_pass["std"] == pytest.approx(math.sqrt(0.02))

    bucket_no_citation = metrics["bucket_rates.no_citation"]
    assert bucket_no_citation["n"] == 2
    assert bucket_no_citation["mean"] == pytest.approx(0.15)
    assert bucket_no_citation["std"] == pytest.approx(math.sqrt(0.005))

    conflict_pass = metrics["conflict_bucket_rates.pass"]
    assert conflict_pass["n"] == 3
    assert conflict_pass["mean"] == pytest.approx(0.9)
    assert conflict_pass["std"] == pytest.approx(0.0)

    cited_qa = metrics["per_task.cited_qa.pass_rate"]
    assert cited_qa["n"] == 2
    assert cited_qa["mean"] == pytest.approx(0.7)
    assert cited_qa["std"] == pytest.approx(math.sqrt(0.02))

    conflict_check = metrics["per_task.conflict_check.pass_rate"]
    assert conflict_check["n"] == 2  # fold2 has no "conflict_check" key at all
    assert conflict_check["values"] == [1.0, 1.0, None]
    assert conflict_check["mean"] == pytest.approx(1.0)
    assert conflict_check["std"] == pytest.approx(0.0)

    report = kfold.format_report(result)
    assert "plan_id: planABC" in report
    assert "advisory:" in report


def test_aggregate_folds_std_is_none_below_two_present_values(tmp_path):
    fold0 = _write_fold_run(
        tmp_path,
        "fold0",
        {"count": 5, "citation_fidelity": 0.5, "conflict_handling": None},
        eval_set_sha256="eval-0",
    )
    fold1 = _write_fold_run(
        tmp_path,
        "fold1",
        {"count": 5, "citation_fidelity": None, "conflict_handling": None},
        eval_set_sha256="eval-1",
    )

    result = kfold.aggregate_folds([fold0, fold1])

    cf = result["metrics"]["citation_fidelity"]
    assert cf["n"] == 1
    assert cf["std"] is None
    assert cf["mean"] == pytest.approx(0.5)

    ch = result["metrics"]["conflict_handling"]
    assert ch["n"] == 0
    assert ch["mean"] is None
    assert ch["std"] is None

    assert "plan_id" not in result  # neither fold's manifest carries one


# --------------------------------------------------------------------------
# 9. aggregate_folds refusals
# --------------------------------------------------------------------------


def test_aggregate_folds_refuses_fewer_than_two_runs(tmp_path):
    fold0 = _write_fold_run(tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0})
    with pytest.raises(kfold.KFoldRefusal):
        kfold.aggregate_folds([fold0])


def test_aggregate_folds_refuses_mixed_scoring_version(tmp_path):
    fold0 = _write_fold_run(
        tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0},
        scoring_version="1", eval_set_sha256="eval-0",
    )
    fold1 = _write_fold_run(
        tmp_path, "fold1", {"count": 1, "citation_fidelity": 1.0},
        scoring_version="2", eval_set_sha256="eval-1",
    )
    with pytest.raises(kfold.KFoldRefusal):
        kfold.aggregate_folds([fold0, fold1])


def test_aggregate_folds_refuses_mixed_corpus_sha256(tmp_path):
    fold0 = _write_fold_run(
        tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0},
        corpus_sha256="corpus-A", eval_set_sha256="eval-0",
    )
    fold1 = _write_fold_run(
        tmp_path, "fold1", {"count": 1, "citation_fidelity": 1.0},
        corpus_sha256="corpus-B", eval_set_sha256="eval-1",
    )
    with pytest.raises(kfold.KFoldRefusal):
        kfold.aggregate_folds([fold0, fold1])


def test_aggregate_folds_refuses_duplicate_eval_set_sha256(tmp_path):
    fold0 = _write_fold_run(
        tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0}, eval_set_sha256="same-eval",
    )
    fold1 = _write_fold_run(
        tmp_path, "fold1", {"count": 1, "citation_fidelity": 1.0}, eval_set_sha256="same-eval",
    )
    with pytest.raises(kfold.KFoldRefusal):
        kfold.aggregate_folds([fold0, fold1])


def test_aggregate_folds_refuses_duplicate_run_dirs(tmp_path):
    fold0 = _write_fold_run(tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0})
    with pytest.raises(kfold.KFoldRefusal):
        kfold.aggregate_folds([fold0, fold0])


def test_load_fold_result_refuses_run_without_evaluation_section(tmp_path):
    fold0 = _write_fold_run(
        tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0}, with_evaluation=False
    )
    with pytest.raises(kfold.KFoldRefusal):
        kfold.load_fold_result(fold0)


def test_load_fold_result_missing_manifest_raises_kfold_error(tmp_path):
    with pytest.raises(kfold.KFoldError):
        kfold.load_fold_result(tmp_path / "does-not-exist")


# --------------------------------------------------------------------------
# 10. CLI
# --------------------------------------------------------------------------


def test_cli_plan_writes_files_and_exits_zero(tmp_path):
    videos = [(f"v{i}", "concept" if i % 2 == 0 else "case_study") for i in range(10)]
    corpus_path = _write_corpus(tmp_path, videos)
    config_path = _write_config(tmp_path)
    out_dir = tmp_path / "cli-plan-out"
    missing_split_v2 = tmp_path / "no-split-v2.json"

    result = subprocess.run(
        [
            sys.executable, "-m", "stoic_training.kfold", "plan",
            "--corpus", str(corpus_path),
            "--config", str(config_path),
            "--out-dir", str(out_dir),
            "--split-v2", str(missing_split_v2),
            "--k", "3",
            "--seed", "1",
        ],
        capture_output=True,
        text=True,
        env=_cpu_only_env(),
    )

    assert result.returncode == 0, result.stderr
    assert (out_dir / "plan.json").is_file()
    assert (out_dir / "commands.sh").is_file()
    assert "launched NOTHING" in result.stdout


def test_cli_aggregate_refusal_exits_2(tmp_path):
    fold0 = _write_fold_run(tmp_path, "fold0", {"count": 1, "citation_fidelity": 1.0})

    result = subprocess.run(
        [sys.executable, "-m", "stoic_training.kfold", "aggregate", str(fold0)],
        capture_output=True,
        text=True,
        env=_cpu_only_env(),
    )

    assert result.returncode == 2
    assert "refused" in result.stderr


# --------------------------------------------------------------------------
# 11. import hygiene
# --------------------------------------------------------------------------


def test_import_hygiene_no_torch_or_yaml_leaked():
    source = (
        "import sys; import stoic_training.kfold; "
        "assert 'torch' not in sys.modules and 'yaml' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, env=_cpu_only_env()
    )
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------
# 12. "never launches" source assertion
# --------------------------------------------------------------------------


def test_kfold_module_source_never_executes_anything():
    source_path = Path(kfold.__file__)
    source = source_path.read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "os.system(" not in source
