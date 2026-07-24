"""Show a training/export/evaluate run's live progress from progress.json.

Purpose guardrail: this reports status for training an OFFLINE research
assistant SLM that proposes cited rule candidates for human review; its
output never touches any live trading path. It only reads progress.json and
prints a formatted summary -- it never loads a model and never touches the
GPU.

CLI: python -m stoic_training.status [--run-dir DIR] [--run-id ID] [--train-home DIR]

Run-directory resolution order:
  1. --run-dir, if given, wins outright.
  2. Else --run-id selects <train_home>/runs/<run_id>.
  3. Else the run dir under <train_home>/runs whose progress.json has the
     newest mtime is auto-selected (the run most recently touched by
     train.py/export.py/evaluate.py).
train_home defaults to config.default_train_home(), which honours
$STOIC_TRAIN_HOME.

Exits 0 and prints the run dir, the formatted progress, and a `tail -f`
reminder on success. Exits 1 with a clear one-line stderr message (no
traceback) when nothing can be resolved -- e.g. no runs directory yet, or
run directories exist but none has written a progress.json.

Pure stdlib; no torch import anywhere in this module.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from stoic_training import progress
from stoic_training.config import default_train_home


class StatusError(RuntimeError):
    """Raised when no run directory can be resolved from the given arguments."""


def select_run_dir(
    *,
    run_dir: Path | None,
    run_id: str | None,
    train_home: Path,
) -> Path:
    """Pure, testable run-directory selection (see module docstring for order).

    Raises StatusError with a clear message when nothing resolves: no runs
    directory, an empty runs directory, or run directories that exist but
    have no progress.json yet.
    """
    if run_dir is not None:
        return Path(run_dir)
    if run_id is not None:
        return Path(train_home) / "runs" / run_id

    runs_dir = Path(train_home) / "runs"
    if not runs_dir.is_dir():
        raise StatusError(f"no runs directory found at {runs_dir}")

    candidate_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    if not candidate_dirs:
        raise StatusError(f"no run directories found under {runs_dir}")

    with_progress = [
        (candidate, candidate / "progress.json")
        for candidate in candidate_dirs
        if (candidate / "progress.json").is_file()
    ]
    if not with_progress:
        noun = "directory" if len(candidate_dirs) == 1 else "directories"
        raise StatusError(
            f"{len(candidate_dirs)} run {noun} found under {runs_dir}, but none has "
            "written a progress.json yet"
        )

    newest_run_dir, _ = max(with_progress, key=lambda pair: pair[1].stat().st_mtime)
    return newest_run_dir


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a run's live progress.json as a human-readable summary."
    )
    parser.add_argument(
        "--run-dir", type=Path, default=None, help="Exact run dir; wins over --run-id"
    )
    parser.add_argument(
        "--run-id", default=None, help="Select <train-home>/runs/<run-id>"
    )
    parser.add_argument(
        "--train-home",
        type=Path,
        default=None,
        help="Defaults to config.default_train_home() "
        "($STOIC_TRAIN_HOME or <repo>/.artifacts/training)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    train_home = args.train_home or default_train_home()

    try:
        run_dir = select_run_dir(run_dir=args.run_dir, run_id=args.run_id, train_home=train_home)
        payload = progress.read_progress(run_dir)
    except (StatusError, progress.ProgressError) as exc:
        print(f"stoic_training.status: {exc}", file=sys.stderr)
        return 1

    print(f"run_dir: {run_dir}")
    print(progress.format_progress(payload))
    print(f"\ntail -f {run_dir / 'train.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
