"""k-fold-by-video runner: plan emission + fold-run aggregation.

Purpose guardrail: this plans and aggregates evaluation runs for an OFFLINE
research assistant that proposes cited rule candidates for human review; no
score computed or aggregated here ever gates a live release (VISION.md,
design doc `2026-07-24-eval-comparison-design.md` section 7).

Design doc section 5.3: "k-fold by video is affordable ... and is the
recommended tool when a config decision looks split-sensitive: it yields a
variance estimate across folds instead of trusting one 3-video sample. Not
the default loop -- a checkpoint before big decisions." This module has two
halves that mirror that framing:

  * **plan** (`build_plan` / `write_plan`) -- deterministically partitions
    the training-eligible videos into k folds and writes, per fold, a
    v1-layout split file, a per-fold `qlora.yaml`, and a NOT-EXECUTED
    `commands.sh`. This half never touches the GPU, never imports torch or
    yaml at module scope, and never runs a subprocess -- it only emits a
    plan a human launches deliberately.
  * **aggregate** (`load_fold_result` / `aggregate_folds`) -- once a human
    has run some subset of `commands.sh` and scored each fold, combines the
    resulting `manifest.json` + `evaluation/scores.json` pairs into a
    mean/std/min/max variance estimate per metric, guarded against mixing
    incomparable folds the same way `compare.py` guards pairwise
    comparisons.

The video stays the atomic split unit throughout (design doc section 5.3,
non-negotiable): fold assignment operates on whole videos, never on
records or time slices within one.

Pure stdlib at module scope, plus `stoic_training.splits` (also pure
stdlib) -- no torch, no transformers, no module-level yaml, so this module
is importable and runnable off the GPU box with no model loaded. `yaml` is
only ever pulled in (via `stoic_training.config.load_config`) inside
`_write_fold`, to validate a freshly written per-fold config, and nowhere
else.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shlex
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from stoic_training import splits as splits_mod

KFOLD_PLAN_VERSION = "1"
DEFAULT_K = 5
# Distinct from split-v1's 20260724 and split-v2's 20260725 so fold
# assignment is uncorrelated with either existing split.
DEFAULT_KFOLD_SEED = 20260726

# src/stoic_training/kfold.py -> stoic_training -> src -> win_cuda
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
# win_cuda -> training -> repo root (same derivation as build_dataset.py / config.py)
REPO_ROOT = PACKAGE_ROOT.parent.parent
DEFAULT_CORPUS = REPO_ROOT / "edu" / "derived" / "dataset.jsonl"
DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "qlora.yaml"

# \x1f (unit separator) frames plan_id fields the same way evaluate.py's
# example_id frames its fields: it cannot appear in a video id, category,
# corpus digest, or decimal seed/k, so it safely disambiguates the joined
# fields hashed into a stable plan_id.
KFOLD_ID_SEPARATOR = "\x1f"

FOLD_PROCEDURE: tuple[str, ...] = (
    "1. Group videos by category; sort categories, and sort the video ids within each "
    "category, so the input order of the inventory never influences the outcome.",
    "2. Shuffle each category's video list with random.Random(f'{seed}:{category}') -- "
    "the same per-category-seed convention as build_dataset.generate_split.",
    "3. Deal each category's shuffled videos round-robin into the k folds, continuing "
    "the deal position across categories with a running offset (category B does not "
    "restart at fold 0) -- this is what keeps both fold SIZES and CATEGORY MIX balanced.",
    "4. Each fold is returned as a sorted tuple; the folds are a partition of the "
    "inventory (every video in exactly one fold, union equals the inventory, no fold "
    "empty).",
)

_DATASET_DIR_RE = re.compile(r"^(\s*dataset_dir:\s*).*$", re.MULTILINE)
_REPO_ID_RE = re.compile(r"^\s*repo_id:\s*(.+?)\s*$", re.MULTILINE)
_REVISION_RE = re.compile(r"^\s*revision:\s*(.+?)\s*$", re.MULTILINE)
# YAML spellings of "no value" that must not be passed through as a literal
# revision string on the command line.
_YAML_NULLS = frozenset({"null", "~", "none", ""})


class KFoldError(RuntimeError):
    """Usage/IO problem: missing file, malformed input, bad CLI args (exit 1)."""


class KFoldRefusal(RuntimeError):
    """Raised when a guard invariant would otherwise fail silently (exit 2)."""


def default_kfold_root() -> Path:
    """`$STOIC_TRAIN_HOME/kfold`, defaulting under `<repo>/.artifacts/training`.

    Kept in lockstep with config.default_train_home() / compare.default_runs_root() /
    build_dataset.default_out_dir(); inlined rather than imported so this module's
    only project-internal import stays `stoic_training.splits`.
    """
    env = os.environ.get("STOIC_TRAIN_HOME")
    home = Path(env).expanduser() if env else REPO_ROOT / ".artifacts" / "training"
    return home / "kfold"


def default_runs_root() -> Path:
    """`$STOIC_TRAIN_HOME/runs` -- where train.py's default `paths.run_dir` resolves.

    Used only as the `aggregate` subcommand's `--runs-root` default (fold runs are
    ordinary training runs, not kfold plan artifacts, so they live under `runs/`, not
    `kfold/`). Inlined rather than imported from compare.py for the same reason as
    `default_kfold_root`.
    """
    env = os.environ.get("STOIC_TRAIN_HOME")
    home = Path(env).expanduser() if env else REPO_ROOT / ".artifacts" / "training"
    return home / "runs"


# --------------------------------------------------------------------------
# Part A: fold assignment
# --------------------------------------------------------------------------


def load_corpus(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    """Read the JSONL corpus; returns (records, corpus_sha256).

    Deliberately NOT imported from build_dataset.py (spec: kfold.py must not import
    or modify it) -- this is the same few lines duplicated locally.
    """
    path = Path(path)
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    records: list[dict[str, Any]] = []
    for line in raw.decode("utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(json.loads(stripped))
    return records, digest


def video_inventory(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Ordered video_id -> category, first-seen order (build_dataset.videos_by_category,
    minus the by-category grouping, which assign_folds does itself)."""
    inventory: dict[str, str] = {}
    for record in records:
        inventory.setdefault(record["video_id"], record["category"])
    return inventory


def assign_folds(
    inventory: Mapping[str, str], *, k: int, seed: int
) -> tuple[tuple[str, ...], ...]:
    """Deterministic, category-stratified partition of `inventory` into k folds.

    Procedure (also recorded verbatim in the emitted plan's `procedure` field, see
    `FOLD_PROCEDURE`, so a reader can reproduce it without this source):

      1. Group videos by category; sort categories, and sort the video ids within
         each category, so the input order of the inventory never influences the
         outcome.
      2. Shuffle each category's video list with `random.Random(f"{seed}:{category}")`
         -- the same per-category-seed convention as `build_dataset.generate_split`.
      3. Deal each category's shuffled videos round-robin into the k folds,
         continuing the deal position across categories with a running offset
         (category B does not restart at fold 0) -- this is what keeps both fold
         SIZES and CATEGORY MIX balanced.
      4. Each fold is returned as a sorted tuple; the folds are a partition of the
         inventory (every video in exactly one fold, union equals the inventory, no
         fold empty).

    Raises `KFoldRefusal` for `k < 2` (no variance estimate from a single fold),
    `k > len(inventory)` (cannot make more folds than videos), or an empty inventory.
    """
    if not inventory:
        raise KFoldRefusal("cannot assign folds: the video inventory is empty")
    if k < 2:
        raise KFoldRefusal(f"k must be >= 2 to compute a fold variance estimate (got k={k})")
    if k > len(inventory):
        raise KFoldRefusal(
            f"k={k} exceeds the inventory size ({len(inventory)} videos) -- cannot make "
            "more folds than videos"
        )

    by_category: dict[str, list[str]] = {}
    for video_id, category in inventory.items():
        by_category.setdefault(category, []).append(video_id)

    folds: list[list[str]] = [[] for _ in range(k)]
    offset = 0
    for category in sorted(by_category):
        videos = sorted(by_category[category])
        random.Random(f"{seed}:{category}").shuffle(videos)
        for i, video_id in enumerate(videos):
            folds[(offset + i) % k].append(video_id)
        offset += len(videos)

    for index, fold in enumerate(folds):
        if not fold:
            raise KFoldRefusal(
                f"fold assignment produced an empty fold {index} for k={k} over "
                f"{len(inventory)} videos; reduce k"
            )

    return tuple(tuple(sorted(fold)) for fold in folds)


def category_coverage(
    inventory: Mapping[str, str], folds: Sequence[Sequence[str]]
) -> dict[str, list[int]]:
    """category -> per-fold video counts, indexed by fold number.

    A 0 anywhere in a category's list means that category has fewer than `len(folds)`
    videos and is therefore absent from at least one fold's eval set -- `known_limits`
    names those categories explicitly.
    """
    categories = sorted(set(inventory.values()))
    coverage: dict[str, list[int]] = {category: [0] * len(folds) for category in categories}
    for fold_index, fold in enumerate(folds):
        for video_id in fold:
            coverage[inventory[video_id]][fold_index] += 1
    return coverage


def known_limits(
    inventory: Mapping[str, str], folds: Sequence[Sequence[str]], *, k: int
) -> list[str]:
    """Human-readable caveats for this fold assignment (split-v2.json's discipline)."""
    coverage = category_coverage(inventory, folds)
    under_covered = sorted(category for category, counts in coverage.items() if min(counts) == 0)

    limits: list[str] = []
    if under_covered:
        limits.append(
            "Categories with fewer than k videos cannot appear in every fold: "
            f"{', '.join(under_covered)}. Those folds' eval sets are missing that "
            "category entirely, which confounds fold-to-fold variance with category mix."
        )
    limits.append(
        f"With {len(inventory)} videos split {k}-ways, each fold's eval set is small "
        f"(~{len(inventory) // k} video(s)); fold variance measures this coarseness as "
        "much as any config difference (design doc section 5.3: 'with 16 videos, any "
        "split is coarse')."
    )
    limits.append(
        "The video is the atomic split unit; no within-video splitting is used or "
        "permitted (design doc sections 5.3 and 7)."
    )
    return limits


# --------------------------------------------------------------------------
# Part B: plan emission (never executes anything)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HoldoutResolution:
    """The fold inventory after applying (or deliberately skipping) holdout exclusion."""

    inventory: dict[str, str]
    excluded_video_ids: tuple[str, ...]
    note: str
    forced_inclusion: bool


def resolve_inventory(
    records: Sequence[Mapping[str, Any]],
    *,
    split_v2_path: str | Path,
    include_holdout: bool,
) -> HoldoutResolution:
    """Build the fold inventory, excluding split-v2's sealed holdout videos by default.

    A k-fold run trains on every video not in its own eval fold, so training on the
    sealed holdout would silently contaminate every future holdout number (design doc
    section 5.2). `--include-holdout` overrides this deliberately; the caller is
    expected to add a loud `known_limits` entry when `forced_inclusion` is True.

    If `split_v2_path` is absent or unreadable, the full inventory is used and that
    fact is recorded in `note` rather than raised -- a missing split-v2.json is not a
    kfold error, it just means there is nothing to exclude.
    """
    inventory = video_inventory(records)
    split_v2_path = Path(split_v2_path)

    if not split_v2_path.is_file():
        return HoldoutResolution(
            inventory=inventory,
            excluded_video_ids=(),
            note=(
                f"split-v2 file not found at {split_v2_path}; proceeding with the full "
                "inventory (nothing to exclude)."
            ),
            forced_inclusion=False,
        )

    try:
        split_v2 = splits_mod.load_split_v2(split_v2_path)
    except splits_mod.SplitError as exc:
        return HoldoutResolution(
            inventory=inventory,
            excluded_video_ids=(),
            note=(
                f"split-v2 file at {split_v2_path} could not be read ({exc}); proceeding "
                "with the full inventory (nothing to exclude)."
            ),
            forced_inclusion=False,
        )

    holdout = tuple(sorted(set(split_v2.holdout_videos) & set(inventory)))
    if not holdout:
        return HoldoutResolution(
            inventory=inventory,
            excluded_video_ids=(),
            note=(
                f"split-v2 holdout videos are not present in this corpus's inventory "
                f"({split_v2_path}); nothing to exclude."
            ),
            forced_inclusion=False,
        )

    if include_holdout:
        return HoldoutResolution(
            inventory=inventory,
            excluded_video_ids=(),
            note=(
                f"--include-holdout: sealed holdout video(s) {', '.join(holdout)} from "
                f"{split_v2_path} were deliberately INCLUDED in the fold inventory."
            ),
            forced_inclusion=True,
        )

    filtered = {video_id: cat for video_id, cat in inventory.items() if video_id not in holdout}
    return HoldoutResolution(
        inventory=filtered,
        excluded_video_ids=holdout,
        note=(
            f"excluded {', '.join(holdout)} (sealed holdout of {split_v2_path}): a k-fold "
            "run trains on every video not in its own eval fold, so training on the sealed "
            "holdout would silently contaminate every future holdout number (design doc "
            "section 5.2). Pass --include-holdout to override deliberately."
        ),
        forced_inclusion=False,
    )


def plan_id_for(*, seed: int, k: int, corpus_sha256: str, inventory: Mapping[str, str]) -> str:
    """sha256 of explicitly framed, \\x1f-separated fields, first 16 hex chars

    (same framing style as evaluate.example_id)."""
    payload = KFOLD_ID_SEPARATOR.join(
        (
            f"plan_version={KFOLD_PLAN_VERSION}",
            f"seed={seed}",
            f"k={k}",
            f"corpus_sha256={corpus_sha256}",
            f"inventory={','.join(sorted(inventory))}",
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _extract_repo_id(config_text: str) -> str:
    match = _REPO_ID_RE.search(config_text)
    if not match:
        raise KFoldError("could not find a `repo_id:` line in the base config")
    return match.group(1).strip("\"'")


def _extract_revision(config_text: str) -> str | None:
    """The pinned base-model revision from the base config, or None if unpinned.

    The emitted evaluate command must pin the same base revision the fold was
    trained against: `evaluate.py` loads the base model itself (a LoRA adapter
    checkpoint is meaningless without it), and an unpinned `--base-repo-id`
    silently resolves to whatever the hub's default branch points at today.
    Returns None for a `null`/absent revision, in which case the command simply
    omits the flag rather than passing the string "null" -- train.py already
    refuses a non-smoke run against an unpinned base, so that case cannot
    produce a fold checkpoint anyway.
    """
    match = _REVISION_RE.search(config_text)
    if not match:
        return None
    revision = match.group(1).strip().strip("\"'")
    return None if revision.lower() in _YAML_NULLS else revision


def _fold_commands(
    *,
    fold_index: int,
    k: int,
    split_file: Path,
    dataset_dir: Path,
    config_file: Path,
    base_repo_id: str,
    base_revision: str | None,
) -> dict[str, list[str]]:
    hypothesis = f"k-fold fold {fold_index}/{k}: variance estimate, not a result"
    evaluate_command = [
        "uv", "run", "python", "-m", "stoic_training.evaluate",
        "--eval-jsonl", str(dataset_dir / "eval.jsonl"),
        "--checkpoint", "<RUN_DIR>/checkpoint/final",
        "--base-repo-id", base_repo_id,
    ]
    if base_revision is not None:
        evaluate_command += ["--base-revision", base_revision]
    evaluate_command += ["--run-dir", "<RUN_DIR>"]
    return {
        "build": [
            "uv", "run", "python", "-m", "stoic_training.build_dataset",
            "--split", str(split_file),
            "--out", str(dataset_dir),
        ],
        "train": [
            "uv", "run", "python", "-m", "stoic_training.train",
            "--config", str(config_file),
            "--hypothesis", hypothesis,
        ],
        # The trained run id (and hence run dir) is only known after train.py
        # finishes; kfold.py does not invent one. <RUN_DIR> is a literal
        # placeholder a human fills in from train.py's printed manifest.
        "evaluate": evaluate_command,
    }


def build_plan(
    *,
    corpus_path: str | Path = DEFAULT_CORPUS,
    k: int = DEFAULT_K,
    seed: int = DEFAULT_KFOLD_SEED,
    base_config_path: str | Path = DEFAULT_CONFIG,
    base_config_text: str | None = None,
    split_v2_path: str | Path | None = None,
    include_holdout: bool = False,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build (but do not write) a k-fold plan. NEVER executes anything.

    `out_dir` defaults to `default_kfold_root() / plan_id`, computed from this
    call's own inputs -- so regenerating with the same seed/k/corpus yields the
    same default location, and `plan.json` is byte-identical except
    `generated_utc`. Passing an explicit `out_dir` must be matched by the SAME
    value passed to `write_plan` (see `plan_out_dir`).

    Note that `plan_id` deliberately hashes only seed/k/corpus_sha256/inventory
    (see `plan_id_for`) -- NOT the base config. The plan id identifies the fold
    GEOMETRY, which is what must be stable and reproducible; comparing two
    configs over the same folds is the entire point of the tool, so two plans
    that differ only by config are meant to share a fold partition. The config
    actually used is recorded per fold and in `base_config`.
    """
    corpus_path = Path(corpus_path)
    if not corpus_path.is_file():
        raise KFoldError(f"corpus not found: {corpus_path}")
    records, corpus_sha256 = load_corpus(corpus_path)

    base_config_path = Path(base_config_path)
    if base_config_text is None:
        if not base_config_path.is_file():
            raise KFoldError(f"base config not found: {base_config_path}")
        base_config_text = base_config_path.read_text(encoding="utf-8")
    base_repo_id = _extract_repo_id(base_config_text)
    base_revision = _extract_revision(base_config_text)

    resolved_split_v2_path = (
        Path(split_v2_path) if split_v2_path is not None else splits_mod.DEFAULT_SPLIT_V2_PATH
    )
    resolution = resolve_inventory(
        records, split_v2_path=resolved_split_v2_path, include_holdout=include_holdout
    )
    inventory = resolution.inventory

    folds = assign_folds(inventory, k=k, seed=seed)
    coverage = category_coverage(inventory, folds)
    limits = known_limits(inventory, folds, k=k)
    limits.append(resolution.note)
    if resolution.forced_inclusion:
        limits.append(
            "LOUD WARNING: --include-holdout was used. Checkpoints trained under this "
            "plan include the sealed holdout of split-v2.json in their TRAINING set and "
            "must NEVER be used to produce a holdout release-candidate number (design doc "
            "section 5.2)."
        )

    plan_id = plan_id_for(seed=seed, k=k, corpus_sha256=corpus_sha256, inventory=inventory)
    resolved_out_dir = Path(out_dir) if out_dir is not None else (default_kfold_root() / plan_id)

    folds_payload = []
    for fold_index, eval_videos in enumerate(folds):
        train_videos = tuple(sorted(set(inventory) - set(eval_videos)))
        fold_dir = resolved_out_dir / f"fold-{fold_index}"
        split_file = fold_dir / "split.json"
        dataset_dir = fold_dir / "dataset"
        config_file = fold_dir / "qlora.yaml"
        folds_payload.append(
            {
                "fold": fold_index,
                "eval_videos": list(eval_videos),
                "train_videos": list(train_videos),
                "split_file": str(split_file),
                "dataset_dir": str(dataset_dir),
                "config_file": str(config_file),
                "commands": _fold_commands(
                    fold_index=fold_index,
                    k=k,
                    split_file=split_file,
                    dataset_dir=dataset_dir,
                    config_file=config_file,
                    base_repo_id=base_repo_id,
                    base_revision=base_revision,
                ),
            }
        )

    return {
        "plan_version": KFOLD_PLAN_VERSION,
        "plan_id": plan_id,
        "generated_utc": datetime.now(UTC).isoformat(),
        "seed": seed,
        "k": k,
        "corpus_sha256": corpus_sha256,
        "corpus_path": str(corpus_path.resolve()),
        "base_config": str(base_config_path.resolve()),
        "procedure": list(FOLD_PROCEDURE),
        "known_limits": limits,
        "excluded_holdout_videos": list(resolution.excluded_video_ids),
        "inventory_size": len(inventory),
        "category_coverage": coverage,
        "folds": folds_payload,
        # Beyond the interface spec's field list: an explicit, directly-testable
        # boolean instead of asking the CLI to grep known_limits for the LOUD
        # WARNING string.
        "holdout_forced_inclusion": resolution.forced_inclusion,
    }


def plan_out_dir(plan: Mapping[str, Any]) -> Path:
    """The directory `write_plan` writes under, derived from fold 0's `split_file`.

    Equals `default_kfold_root() / plan_id` when `build_plan` was called with its
    default `out_dir=None`; recovers an explicit `out_dir` instead when one was given.
    """
    folds = plan.get("folds") or []
    if not folds:
        raise KFoldError("plan has no folds; cannot derive its output directory")
    return Path(folds[0]["split_file"]).parent.parent


def _rewrite_dataset_dir(config_text: str, dataset_dir: Path) -> str:
    """Regex-replace the single `dataset_dir:` line, preserving every comment."""
    matches = list(_DATASET_DIR_RE.finditer(config_text))
    if len(matches) != 1:
        raise KFoldError(
            f"expected exactly one `dataset_dir:` line in the base config, found "
            f"{len(matches)}"
        )
    prefix = matches[0].group(1)
    new_line = f'{prefix}"{dataset_dir.as_posix()}"'
    # Replacement is a callback (not a template string) so a Windows-style path in
    # dataset_dir can never be misparsed as a backreference escape by re.sub.
    return _DATASET_DIR_RE.sub(lambda _match: new_line, config_text, count=1)


def _write_fold(plan: Mapping[str, Any], fold: Mapping[str, Any], *, base_config_text: str) -> None:
    fold_index = fold["fold"]
    split_path = Path(fold["split_file"])
    dataset_dir = Path(fold["dataset_dir"])
    config_path = Path(fold["config_file"])

    split_payload = {
        "version": f"kfold-{plan['plan_id']}-fold{fold_index}",
        "seed": plan["seed"],
        "corpus_sha256": plan["corpus_sha256"],
        "train_videos": list(fold["train_videos"]),
        "eval_videos": list(fold["eval_videos"]),
        "note": (
            f"Generated k-fold split: plan {plan['plan_id']}, fold {fold_index}/{plan['k']}. "
            "NOT a committed lineage split -- do not confuse with splits/split-v1.json or "
            "splits/split-v2.json. See the sibling plan.json for full provenance."
        ),
    }
    if splits_mod.is_split_v2(split_payload):
        raise KFoldError(
            f"generated fold-{fold_index} split payload was misdetected as a split-v2 "
            "file (splits.is_split_v2 returned True) -- this must never happen"
        )
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(
        json.dumps(split_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    config_text = _rewrite_dataset_dir(base_config_text, dataset_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")

    from stoic_training.config import load_config  # lazy: pulls in yaml

    parsed = load_config(config_path)
    if parsed.paths.dataset_dir != dataset_dir:
        raise KFoldError(
            f"fold {fold_index} config validation failed: {config_path} parsed to "
            f"paths.dataset_dir={parsed.paths.dataset_dir!r}, expected {dataset_dir!r}"
        )


def _commands_sh_text(plan: Mapping[str, Any]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "# ============================================================================",
        "# THIS SCRIPT LAUNCHES GPU WORK: a dataset build, a QLoRA training run, and an",
        "# evaluation run for EACH k-fold fold below. stoic_training.kfold deliberately",
        "# does NOT execute any of these commands itself -- generating a plan must never",
        "# touch the GPU. A human (or the top-level orchestrating agent) must read this",
        "# file and launch it DETACHED, and only once the GPU is confirmed free.",
        "# ============================================================================",
        "set -euo pipefail",
        "",
    ]
    for fold in plan["folds"]:
        fold_index = fold["fold"]
        lines.append(f"# --- fold {fold_index}/{plan['k']} ---")
        lines.append(shlex.join(fold["commands"]["build"]))
        lines.append(shlex.join(fold["commands"]["train"]))
        lines.append(
            "# The run id is only known once training finishes (see the run dir train.py "
            "printed). Fill in <RUN_DIR> below -- this plan does not invent a run id."
        )
        lines.append(shlex.join(fold["commands"]["evaluate"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def write_plan(plan: Mapping[str, Any], out_dir: str | Path, *, base_config_text: str) -> Path:
    """Write `plan` to disk under `out_dir`. NEVER executes anything (no subprocess call
    of any kind lives in this module -- see `_commands_sh_text`, which only writes text).

    `out_dir` must equal `plan_out_dir(plan)` -- i.e. the same value (or None) that was
    passed to the `build_plan` call which produced `plan` -- otherwise the fold paths
    baked into `plan["folds"]` would point somewhere other than where this function
    actually writes them.
    """
    out_dir = Path(out_dir)
    expected = plan_out_dir(plan)
    if out_dir != expected:
        raise KFoldError(
            f"write_plan out_dir {out_dir} does not match the directory this plan's fold "
            f"paths were computed against ({expected}); pass build_plan(out_dir=...) the "
            "same value, or omit out_dir on both calls to use the default."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    plan_path = out_dir / "plan.json"
    plan_path.write_text(json.dumps(dict(plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for fold in plan["folds"]:
        _write_fold(plan, fold, base_config_text=base_config_text)

    commands_path = out_dir / "commands.sh"
    commands_path.write_text(_commands_sh_text(plan), encoding="utf-8")
    commands_path.chmod(0o644)

    return out_dir


# --------------------------------------------------------------------------
# Part C: aggregation across completed fold runs
# --------------------------------------------------------------------------


def _read_json(path: Path, *, what: str) -> dict[str, Any]:
    if not path.is_file():
        raise KFoldError(f"{what} not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KFoldError(f"invalid JSON in {what} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KFoldError(f"{path} must contain a JSON object")
    return payload


def load_fold_result(run_dir: str | Path) -> dict[str, Any]:
    """Read one fold's evaluated run: manifest.json's `evaluation` section plus
    `evaluation/scores.json`.

    Small local re-implementation of compare.py's private `_load_manifest` /
    `_load_scores` (compare.py is owned by a concurrent workstream and must not be
    imported for internals here, per spec). Raises `KFoldError` for missing/malformed
    files and `KFoldRefusal` when a run has no `evaluation` section (unscored run).
    """
    run_dir = Path(run_dir)
    manifest = _read_json(run_dir / "manifest.json", what="manifest")

    evaluation = manifest.get("evaluation")
    if not isinstance(evaluation, dict) or not evaluation:
        raise KFoldRefusal(
            f"run {run_dir} has no `evaluation` section in manifest.json -- it has not "
            "been scored yet"
        )

    scores_info = evaluation.get("scores") or {}
    declared_path = scores_info.get("path")
    scores_path = Path(declared_path) if declared_path else None
    if scores_path is None or not scores_path.is_file():
        scores_path = run_dir / "evaluation" / "scores.json"
    scores = _read_json(scores_path, what="scores.json")

    eval_scores = scores.get("eval")
    if not isinstance(eval_scores, dict):
        raise KFoldError(f"{scores_path}: missing top-level `eval` section")

    return {
        "run_dir": run_dir,
        "manifest": manifest,
        "evaluation": evaluation,
        "eval_scores": eval_scores,
        "plan_id": manifest.get("plan_id"),
        "scoring_version": evaluation.get("scoring_version"),
        "corpus_sha256": evaluation.get("corpus_sha256"),
        "eval_set_sha256": evaluation.get("eval_set_sha256"),
    }


def _stat(values: Sequence[float | None]) -> dict[str, Any]:
    """{"n", "mean", "std", "min", "max", "values"} over the non-None entries of `values`.

    `values` keeps every entry (including None) in the given run order; `n` and the
    other summary stats are computed over the non-None subset only. `std` is the
    sample standard deviation (`statistics.stdev`, ddof=1) and is None for n < 2.
    """
    present = [value for value in values if value is not None]
    n = len(present)
    return {
        "n": n,
        "mean": statistics.fmean(present) if n else None,
        "std": statistics.stdev(present) if n >= 2 else None,
        "min": min(present) if n else None,
        "max": max(present) if n else None,
        "values": list(values),
    }


def _aggregate_metrics(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-metric fold statistics.

    A metric's key namespace ("known bucket namespace") is the union of keys observed
    across ALL of `results`' `bucket_rates` / `conflict_bucket_rates` / `per_task`
    dicts -- not a global constant imported from evaluate.py. A key present in some
    folds and absent (not merely null) in others still gets an entry: `.get(key)`
    contributes None for the folds missing it, so `n` only counts folds that actually
    reported that key. A key absent from every fold's dict does not appear at all
    (there is nothing "known" about it in this aggregation).
    """
    eval_scores_list = [result["eval_scores"] for result in results]
    metrics: dict[str, Any] = {}

    for key in ("citation_fidelity", "conflict_handling", "count"):
        metrics[key] = _stat([scores.get(key) for scores in eval_scores_list])

    bucket_keys = sorted(
        {key for scores in eval_scores_list for key in (scores.get("bucket_rates") or {})}
    )
    for key in bucket_keys:
        metrics[f"bucket_rates.{key}"] = _stat(
            [(scores.get("bucket_rates") or {}).get(key) for scores in eval_scores_list]
        )

    conflict_keys = sorted(
        {
            key
            for scores in eval_scores_list
            for key in (scores.get("conflict_bucket_rates") or {})
        }
    )
    for key in conflict_keys:
        metrics[f"conflict_bucket_rates.{key}"] = _stat(
            [(scores.get("conflict_bucket_rates") or {}).get(key) for scores in eval_scores_list]
        )

    task_keys = sorted(
        {task for scores in eval_scores_list for task in (scores.get("per_task") or {})}
    )
    for task in task_keys:
        metrics[f"per_task.{task}.pass_rate"] = _stat(
            [
                ((scores.get("per_task") or {}).get(task) or {}).get("pass_rate")
                for scores in eval_scores_list
            ]
        )

    return metrics


def aggregate_folds(run_dirs: Sequence[str | Path]) -> dict[str, Any]:
    """Combine scored fold runs into a variance estimate. Raises `KFoldRefusal` (exit 2)
    on any guard violation.

    Guards, in order: fewer than 2 run dirs (a variance estimate needs at least two
    folds); mixed `scoring_version` across folds; mixed `corpus_sha256` across folds;
    a duplicate `eval_set_sha256` across two folds; duplicate run dirs.

    The duplicate-`eval_set_sha256` guard is the INVERSE of compare.py's mismatch
    guard: `compare.py` refuses two runs scored against *different* eval sets, because
    it pairs examples by id from what should be the SAME eval set. k-fold spreads runs
    over deliberately DISJOINT eval sets (each fold's held-out videos), so two folds
    reporting the identical eval-set digest means the same fold was scored twice, not
    that anything is being compared correctly.
    """
    run_dir_paths = [Path(run_dir) for run_dir in run_dirs]

    if len(run_dir_paths) < 2:
        raise KFoldRefusal(
            f"aggregate_folds needs at least 2 run dirs to compute a variance estimate "
            f"(got {len(run_dir_paths)})"
        )

    results = [load_fold_result(path) for path in run_dir_paths]

    scoring_versions = {result["scoring_version"] for result in results}
    if len(scoring_versions) > 1:
        raise KFoldRefusal(
            f"mixed scoring_version across folds: {sorted(scoring_versions)} -- comparing "
            "scores computed under different scoring rules is meaningless"
        )

    corpus_shas = {result["corpus_sha256"] for result in results}
    if len(corpus_shas) > 1:
        raise KFoldRefusal(
            f"mixed corpus_sha256 across folds: {sorted(corpus_shas)} -- folds must be "
            "scored against the same corpus"
        )

    eval_set_shas = [result["eval_set_sha256"] for result in results if result["eval_set_sha256"]]
    seen_eval: set[str] = set()
    duplicate_eval: set[str] = set()
    for sha in eval_set_shas:
        if sha in seen_eval:
            duplicate_eval.add(sha)
        seen_eval.add(sha)
    if duplicate_eval:
        raise KFoldRefusal(
            f"duplicate eval_set_sha256 across folds: {sorted(duplicate_eval)} -- folds must "
            "score DIFFERENT eval sets by construction (each fold's held-out videos are "
            "disjoint from every other fold's); two identical digests mean the same fold was "
            "scored twice, not that two folds agree. (Inverse of compare.py's guard: compare "
            "pairs two runs against ONE shared eval set, k-fold spreads runs over DISJOINT "
            "eval sets.)"
        )

    resolved = [path.resolve() for path in run_dir_paths]
    seen_dirs: set[Path] = set()
    duplicate_dirs: set[Path] = set()
    for path in resolved:
        if path in seen_dirs:
            duplicate_dirs.add(path)
        seen_dirs.add(path)
    if duplicate_dirs:
        raise KFoldRefusal(
            f"duplicate run dir(s) passed to aggregate_folds: "
            f"{sorted(str(path) for path in duplicate_dirs)}"
        )

    plan_ids = {result["plan_id"] for result in results}
    plan_id = next(iter(plan_ids)) if len(plan_ids) == 1 and None not in plan_ids else None

    result: dict[str, Any] = {
        "k": len(results),
        "run_dirs": [str(path) for path in run_dir_paths],
        "scoring_version": next(iter(scoring_versions)),
        "corpus_sha256": next(iter(corpus_shas)),
        "metrics": _aggregate_metrics(results),
        "advisory": (
            "Fold variance is a variance ESTIMATE for a config decision, not a headline "
            "score. k-fold checkpoints train on videos the main lineage holds out for its "
            "own eval/holdout, so k-fold numbers must never be compared with main-lineage "
            "runs (design doc section 5.3)."
        ),
    }
    if plan_id is not None:
        result["plan_id"] = plan_id
    return result


def format_report(result: Mapping[str, Any]) -> str:
    lines = [
        f"k: {result['k']}",
        f"scoring_version: {result['scoring_version']}",
        f"corpus_sha256: {result['corpus_sha256']}",
    ]
    if "plan_id" in result:
        lines.append(f"plan_id: {result['plan_id']}")
    lines.append("run_dirs:")
    for run_dir in result["run_dirs"]:
        lines.append(f"  {run_dir}")

    lines.append("")
    lines.append("metrics:")
    for name, stat in sorted(result["metrics"].items()):
        mean = "n/a" if stat["mean"] is None else f"{stat['mean']:.4f}"
        std = "n/a" if stat["std"] is None else f"{stat['std']:.4f}"
        lines.append(
            f"  {name}: n={stat['n']} mean={mean} std={std} min={stat['min']} "
            f"max={stat['max']} values={stat['values']}"
        )

    lines.append("")
    lines.append(f"advisory: {result['advisory']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _resolve_run_dir(run_arg: str, runs_root: Path) -> Path:
    candidate = Path(run_arg)
    if candidate.is_dir() and (candidate / "manifest.json").is_file():
        return candidate
    return runs_root / run_arg


def cmd_plan(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus)
    base_config_path = Path(args.config)
    if not base_config_path.is_file():
        raise KFoldError(f"base config not found: {base_config_path}")
    base_config_text = base_config_path.read_text(encoding="utf-8")

    split_v2_path = (
        Path(args.split_v2) if args.split_v2 is not None else splits_mod.DEFAULT_SPLIT_V2_PATH
    )

    plan = build_plan(
        corpus_path=corpus_path,
        k=args.k,
        seed=args.seed,
        base_config_path=base_config_path,
        base_config_text=base_config_text,
        split_v2_path=split_v2_path,
        include_holdout=args.include_holdout,
        out_dir=args.out_dir,
    )

    out_dir = plan_out_dir(plan)
    write_plan(plan, out_dir, base_config_text=base_config_text)

    if plan["holdout_forced_inclusion"]:
        print(
            "WARNING: --include-holdout used -- checkpoints from this plan must NEVER "
            "be used for a holdout release-candidate number.",
            file=sys.stderr,
        )

    print(f"plan_id: {plan['plan_id']}")
    print(f"{'fold':<6}{'eval_videos':>14}{'train_videos':>15}")
    for fold in plan["folds"]:
        print(f"{fold['fold']:<6}{len(fold['eval_videos']):>14}{len(fold['train_videos']):>15}")
    print(f"plan dir: {out_dir}")
    print("known limits:")
    for limit in plan["known_limits"]:
        print(f"  - {limit}")
    print(
        "\nThis command launched NOTHING. Review "
        f"{out_dir / 'commands.sh'}, fill in <RUN_DIR> after each fold's training "
        "command completes, and run the commands deliberately -- detached, only when "
        "the GPU is free."
    )
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    runs_root = Path(args.runs_root) if args.runs_root is not None else default_runs_root()
    run_dirs = [_resolve_run_dir(run_arg, runs_root) for run_arg in args.runs]
    result = aggregate_folds(run_dirs)

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.out is not None:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    if args.json:
        print(payload)
    else:
        print(format_report(result))
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="k-fold-by-video planner and fold-aggregation tool. Never launches "
        "GPU work; `plan` only emits a plan for a human to run deliberately."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Emit a k-fold plan (folds, splits, configs, commands.sh)")
    plan.add_argument("--k", type=int, default=DEFAULT_K)
    plan.add_argument("--seed", type=int, default=DEFAULT_KFOLD_SEED)
    plan.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    plan.add_argument("--out-dir", type=Path, default=None)
    plan.add_argument(
        "--include-holdout",
        action="store_true",
        help="Deliberately include split-v2's sealed holdout videos in the fold "
        "inventory. Checkpoints from the resulting plan must never be used for a "
        "holdout release-candidate number.",
    )
    plan.add_argument(
        "--split-v2",
        type=Path,
        default=None,
        help="split-v2.json path (default: splits.DEFAULT_SPLIT_V2_PATH)",
    )
    plan.set_defaults(func=cmd_plan)

    aggregate = sub.add_parser(
        "aggregate", help="Aggregate scored fold runs into a variance estimate"
    )
    aggregate.add_argument("runs", nargs="+", help="Run dir, or run_id under --runs-root")
    aggregate.add_argument("--runs-root", type=Path, default=None)
    aggregate.add_argument("--json", action="store_true", help="Emit the result as JSON")
    aggregate.add_argument("--out", type=Path, default=None, help="Also write the result here")
    aggregate.set_defaults(func=cmd_aggregate)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return int(args.func(args))
    except KFoldRefusal as exc:
        print(f"stoic_training.kfold: refused: {exc}", file=sys.stderr)
        return 2
    except KFoldError as exc:
        print(f"stoic_training.kfold: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_CORPUS",
    "DEFAULT_K",
    "DEFAULT_KFOLD_SEED",
    "FOLD_PROCEDURE",
    "KFOLD_ID_SEPARATOR",
    "KFOLD_PLAN_VERSION",
    "PACKAGE_ROOT",
    "REPO_ROOT",
    "HoldoutResolution",
    "KFoldError",
    "KFoldRefusal",
    "aggregate_folds",
    "assign_folds",
    "build_plan",
    "category_coverage",
    "default_kfold_root",
    "default_runs_root",
    "format_report",
    "known_limits",
    "load_corpus",
    "load_fold_result",
    "main",
    "parse_args",
    "plan_id_for",
    "plan_out_dir",
    "resolve_inventory",
    "video_inventory",
    "write_plan",
]
