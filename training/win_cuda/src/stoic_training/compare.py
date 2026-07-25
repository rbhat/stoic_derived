"""Run-over-run comparison for the offline research-assistant SLM.

Purpose guardrail: this compares evaluation runs for an OFFLINE research
assistant that proposes cited rule candidates for human review; its output
never touches any live trading path. No score computed here ever gates a
live release -- that gate remains a human-approved, signed SP0.

Pure stdlib (json, math, argparse, pathlib, dataclasses, os) -- no torch, no
yaml -- so this module is importable and runnable off the GPU box, in CI,
with no model loaded. It reads the corpus/eval-set digests *from* each run's
manifest `evaluation` section (see `manifest.update_manifest_evaluation`);
it never hashes anything itself.

CLI: `python -m stoic_training.compare <run_a> <run_b> [--runs-root DIR] [--json]`

Refuses (`CompareRefusal`, exit 2) to compare two runs whose manifests
disagree on `corpus_sha256`, `eval_set_sha256`, or `scoring_version`, or
where either manifest lacks an `evaluation` section at all -- comparing
scores computed against different corpora, eval sets, or scoring rules is
meaningless, not just noisy. Exit 1 covers usage/IO problems (missing run
dir, missing scores.json, a details entry without `example_id`). Exit 0 on
success.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# src/stoic_training/compare.py -> stoic_training -> src -> win_cuda
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent.parent

_HEADLINE_METRICS = ("citation_fidelity", "conflict_handling", "count")


class CompareRefusal(RuntimeError):
    """Raised when two runs are not comparable (mismatched corpus/eval/scoring)."""


@dataclass(frozen=True, slots=True)
class FlipResult:
    fixed: tuple[str, ...]  # example_ids: fail in A -> pass in B
    broke: tuple[str, ...]  # pass in A -> fail in B
    unchanged_pass: int
    unchanged_fail: int
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]


def default_runs_root() -> Path:
    """`$STOIC_TRAIN_HOME/runs`, defaulting under `<repo>/.artifacts/training`.

    Kept in lockstep with config.default_train_home(); the default is
    inlined here rather than imported so this module stays stdlib-only
    (importing config.py would pull in yaml).
    """
    env = os.environ.get("STOIC_TRAIN_HOME")
    home = Path(env).expanduser() if env else REPO_ROOT / ".artifacts" / "training"
    return home / "runs"


def resolve_run_dir(run_arg: str | Path, runs_root: str | Path) -> Path:
    """Resolve a run argument: an existing dir with manifest.json wins outright;
    otherwise `<runs_root>/<run_arg>`."""
    candidate = Path(run_arg)
    if candidate.is_dir() and (candidate / "manifest.json").is_file():
        return candidate
    return Path(runs_root) / run_arg


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_scores(run_dir: Path, evaluation: Mapping[str, Any]) -> dict[str, Any]:
    scores_info = evaluation.get("scores") or {}
    declared_path = scores_info.get("path")
    path = Path(declared_path) if declared_path else None
    if path is None or not path.is_file():
        # The run dir may have been moved since the manifest was written.
        path = run_dir / "evaluation" / "scores.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"scores.json not found for run {run_dir} "
            f"(tried manifest path {declared_path!r} and {path})"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require_evaluation(manifest: Mapping[str, Any], run_dir: Path) -> dict[str, Any]:
    evaluation = manifest.get("evaluation")
    if not isinstance(evaluation, dict) or not evaluation:
        raise CompareRefusal(
            f"run {run_dir} has no `evaluation` section in manifest.json -- "
            "it has not been scored yet, or was scored before WP1"
        )
    return evaluation


def _refuse_on_mismatch(field: str, eval_a: Mapping[str, Any], eval_b: Mapping[str, Any]) -> None:
    value_a = eval_a.get(field)
    value_b = eval_b.get(field)
    if value_a != value_b:
        raise CompareRefusal(
            f"{field} mismatch: run_a has {value_a!r}, run_b has {value_b!r} -- refusing to "
            "compare runs scored against different corpora/eval-sets/scoring versions"
        )


def _delta(value_a: Any, value_b: Any) -> float | None:
    if value_a is None or value_b is None:
        return None
    return value_b - value_a


def _headline_deltas(eval_a: Mapping[str, Any], eval_b: Mapping[str, Any]) -> dict[str, Any]:
    return {
        metric: {
            "a": eval_a.get(metric),
            "b": eval_b.get(metric),
            "delta": _delta(eval_a.get(metric), eval_b.get(metric)),
        }
        for metric in _HEADLINE_METRICS
    }


def _per_task_deltas(
    per_task_a: Mapping[str, Any], per_task_b: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for task in sorted(set(per_task_a) | set(per_task_b)):
        a = per_task_a.get(task) or {}
        b = per_task_b.get(task) or {}
        result[task] = {
            "count_a": a.get("count"),
            "count_b": b.get("count"),
            "pass_rate_a": a.get("pass_rate"),
            "pass_rate_b": b.get("pass_rate"),
            "pass_rate_delta": _delta(a.get("pass_rate"), b.get("pass_rate")),
        }
    return result


def _bucket_group_deltas(
    counts_a: Mapping[str, Any] | None,
    counts_b: Mapping[str, Any] | None,
    rates_a: Mapping[str, Any] | None,
    rates_b: Mapping[str, Any] | None,
) -> dict[str, Any]:
    counts_a = counts_a or {}
    counts_b = counts_b or {}
    rates_a = rates_a or {}
    rates_b = rates_b or {}
    result: dict[str, Any] = {}
    for bucket in sorted(set(counts_a) | set(counts_b)):
        count_a = counts_a.get(bucket)
        count_b = counts_b.get(bucket)
        count_delta = (
            count_b - count_a if count_a is not None and count_b is not None else None
        )
        result[bucket] = {
            "count_a": count_a,
            "count_b": count_b,
            "count_delta": count_delta,
            "rate_a": rates_a.get(bucket),
            "rate_b": rates_b.get(bucket),
            "rate_delta": _delta(rates_a.get(bucket), rates_b.get(bucket)),
        }
    return result


def _bucket_deltas(eval_a: Mapping[str, Any], eval_b: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "citation_buckets": _bucket_group_deltas(
            eval_a.get("buckets"), eval_b.get("buckets"),
            eval_a.get("bucket_rates"), eval_b.get("bucket_rates"),
        ),
        "conflict_buckets": _bucket_group_deltas(
            eval_a.get("conflict_buckets"), eval_b.get("conflict_buckets"),
            eval_a.get("conflict_bucket_rates"), eval_b.get("conflict_bucket_rates"),
        ),
    }


def _index_by_example_id(details: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    by_id: dict[str, Any] = {}
    for entry in details:
        example_id = entry.get("example_id")
        if not example_id:
            raise ValueError(
                f"details entry in run {label} is missing example_id: {entry!r}"
            )
        by_id[example_id] = entry
    return by_id


def paired_flips(
    details_a: Sequence[Mapping[str, Any]], details_b: Sequence[Mapping[str, Any]]
) -> FlipResult:
    """Pair `eval.details` entries by `example_id` and classify pass/fail flips."""
    index_a = _index_by_example_id(details_a, "a")
    index_b = _index_by_example_id(details_b, "b")

    ids_a = set(index_a)
    ids_b = set(index_b)
    common = ids_a & ids_b

    fixed: list[str] = []
    broke: list[str] = []
    unchanged_pass = 0
    unchanged_fail = 0
    for example_id in common:
        passed_a = bool(index_a[example_id].get("passed"))
        passed_b = bool(index_b[example_id].get("passed"))
        if passed_a and not passed_b:
            broke.append(example_id)
        elif not passed_a and passed_b:
            fixed.append(example_id)
        elif passed_a and passed_b:
            unchanged_pass += 1
        else:
            unchanged_fail += 1

    return FlipResult(
        fixed=tuple(sorted(fixed)),
        broke=tuple(sorted(broke)),
        unchanged_pass=unchanged_pass,
        unchanged_fail=unchanged_fail,
        only_in_a=tuple(sorted(ids_a - ids_b)),
        only_in_b=tuple(sorted(ids_b - ids_a)),
    )


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact binomial (McNemar) p-value on discordant pair counts.

    n = b + c; p = 1.0 when n == 0; otherwise
    p = min(1.0, 2 * sum_{k=0..min(b,c)} C(n, k) / 2**n). Uses math.comb only.
    """
    n = b + c
    if n == 0:
        return 1.0
    k_max = min(b, c)
    tail = sum(math.comb(n, k) for k in range(k_max + 1))
    return min(1.0, 2 * tail / (2**n))


def compare_runs(run_a_dir: str | Path, run_b_dir: str | Path) -> dict[str, Any]:
    """Compare two evaluated run directories. Raises CompareRefusal on guard failure."""
    run_a_dir = Path(run_a_dir)
    run_b_dir = Path(run_b_dir)

    manifest_a = _load_manifest(run_a_dir)
    manifest_b = _load_manifest(run_b_dir)

    eval_a = _require_evaluation(manifest_a, run_a_dir)
    eval_b = _require_evaluation(manifest_b, run_b_dir)

    for field in ("corpus_sha256", "eval_set_sha256", "scoring_version"):
        _refuse_on_mismatch(field, eval_a, eval_b)

    scores_a = _load_scores(run_a_dir, eval_a)
    scores_b = _load_scores(run_b_dir, eval_b)

    eval_scores_a = scores_a.get("eval") or {}
    eval_scores_b = scores_b.get("eval") or {}

    details_a = eval_scores_a.get("details") or []
    details_b = eval_scores_b.get("details") or []
    flips = paired_flips(details_a, details_b)

    return {
        "run_a": str(run_a_dir),
        "run_b": str(run_b_dir),
        "corpus_sha256": eval_a.get("corpus_sha256"),
        "eval_set_sha256": eval_a.get("eval_set_sha256"),
        "scoring_version": eval_a.get("scoring_version"),
        "headline": _headline_deltas(eval_scores_a, eval_scores_b),
        "per_task": _per_task_deltas(
            eval_scores_a.get("per_task") or {}, eval_scores_b.get("per_task") or {}
        ),
        "buckets": _bucket_deltas(eval_scores_a, eval_scores_b),
        "flips": {
            "fixed": list(flips.fixed),
            "broke": list(flips.broke),
            "unchanged_pass": flips.unchanged_pass,
            "unchanged_fail": flips.unchanged_fail,
            "only_in_a": list(flips.only_in_a),
            "only_in_b": list(flips.only_in_b),
            "mcnemar_p": mcnemar_exact_p(len(flips.broke), len(flips.fixed)),
        },
    }


def format_report(result: Mapping[str, Any]) -> str:
    lines = [
        f"run_a: {result['run_a']}",
        f"run_b: {result['run_b']}",
        f"corpus_sha256: {result['corpus_sha256']}",
        f"eval_set_sha256: {result['eval_set_sha256']}",
        f"scoring_version: {result['scoring_version']}",
        "",
        "headline:",
    ]
    for metric, values in result["headline"].items():
        lines.append(f"  {metric}: a={values['a']} b={values['b']} delta={values['delta']}")

    lines.append("")
    lines.append("per_task pass_rate:")
    for task, values in sorted(result["per_task"].items()):
        lines.append(
            f"  {task}: a={values['pass_rate_a']} b={values['pass_rate_b']} "
            f"delta={values['pass_rate_delta']}"
        )

    for group_name, group in sorted(result["buckets"].items()):
        lines.append("")
        lines.append(f"{group_name}:")
        for bucket, values in sorted(group.items()):
            lines.append(
                f"  {bucket}: count a={values['count_a']} b={values['count_b']} "
                f"delta={values['count_delta']}; rate a={values['rate_a']} "
                f"b={values['rate_b']} delta={values['rate_delta']}"
            )

    flips = result["flips"]
    lines.append("")
    lines.append(
        f"paired flips: fixed={len(flips['fixed'])} broke={len(flips['broke'])} "
        f"unchanged_pass={flips['unchanged_pass']} unchanged_fail={flips['unchanged_fail']} "
        f"mcnemar_p={flips['mcnemar_p']}"
    )
    lines.append(f"fixed ids: {', '.join(flips['fixed']) or '(none)'}")
    lines.append(f"broke ids: {', '.join(flips['broke']) or '(none)'}")
    lines.append(f"only_in_a: {', '.join(flips['only_in_a']) or '(none)'}")
    lines.append(f"only_in_b: {', '.join(flips['only_in_b']) or '(none)'}")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two evaluated runs: headline/bucket deltas, paired flips, McNemar p."
    )
    parser.add_argument("run_a", help="Run dir, or run_id under --runs-root")
    parser.add_argument("run_b", help="Run dir, or run_id under --runs-root")
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Emit the full comparison as JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runs_root = args.runs_root if args.runs_root is not None else default_runs_root()

    run_a_dir = resolve_run_dir(args.run_a, runs_root)
    run_b_dir = resolve_run_dir(args.run_b, runs_root)

    try:
        result = compare_runs(run_a_dir, run_b_dir)
    except CompareRefusal as exc:
        print(f"stoic_training.compare: refused: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"stoic_training.compare: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
