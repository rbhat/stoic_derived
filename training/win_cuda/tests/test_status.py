"""Tests for status.py's run-dir selection and CLI output.

Pure stdlib, CPU-only, no torch import: status.py only reads progress.json.
"""

from __future__ import annotations

import json
import time

import pytest

from stoic_training import status


def write_progress(run_dir, *, run_id: str, step: int = 5, total_steps: int = 100) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "phase": "train",
        "step": step,
        "total_steps": total_steps,
        "loss": 0.5,
        "steps_per_sec": 0.1,
        "elapsed_s": 50.0,
        "eta_s": 950.0,
        "eta_utc": "2026-07-24T13:00:00+00:00",
        "updated_utc": "2026-07-24T12:00:00+00:00",
    }
    (run_dir / "progress.json").write_text(json.dumps(payload), encoding="utf-8")


# --- select_run_dir ------------------------------------------------------------


def test_select_run_dir_explicit_run_dir_wins(tmp_path):
    explicit = tmp_path / "somewhere-else"
    other_train_home = tmp_path / "train-home"
    resolved = status.select_run_dir(run_dir=explicit, run_id="abc123", train_home=other_train_home)
    assert resolved == explicit


def test_select_run_dir_uses_run_id(tmp_path):
    train_home = tmp_path / "train-home"
    resolved = status.select_run_dir(run_dir=None, run_id="abc123", train_home=train_home)
    assert resolved == train_home / "runs" / "abc123"


def test_select_run_dir_auto_selects_newest_progress_json(tmp_path):
    train_home = tmp_path / "train-home"
    runs_dir = train_home / "runs"

    older = runs_dir / "run-older"
    newer = runs_dir / "run-newer"
    write_progress(older, run_id="run-older")
    time.sleep(0.01)
    write_progress(newer, run_id="run-newer")

    # Nudge the newer file's mtime forward explicitly for a robust ordering
    # signal regardless of filesystem timestamp resolution.
    now = time.time()
    import os

    os.utime(older / "progress.json", (now - 100, now - 100))
    os.utime(newer / "progress.json", (now, now))

    resolved = status.select_run_dir(run_dir=None, run_id=None, train_home=train_home)
    assert resolved == newer


def test_select_run_dir_raises_when_no_runs_directory(tmp_path):
    train_home = tmp_path / "train-home"
    with pytest.raises(status.StatusError, match="no runs directory"):
        status.select_run_dir(run_dir=None, run_id=None, train_home=train_home)


def test_select_run_dir_raises_when_runs_directory_empty(tmp_path):
    train_home = tmp_path / "train-home"
    (train_home / "runs").mkdir(parents=True)
    with pytest.raises(status.StatusError, match="no run directories"):
        status.select_run_dir(run_dir=None, run_id=None, train_home=train_home)


def test_select_run_dir_raises_when_run_dirs_have_no_progress_json(tmp_path):
    train_home = tmp_path / "train-home"
    (train_home / "runs" / "run-a").mkdir(parents=True)
    (train_home / "runs" / "run-b").mkdir(parents=True)
    with pytest.raises(status.StatusError, match="none has written a progress.json"):
        status.select_run_dir(run_dir=None, run_id=None, train_home=train_home)


# --- main() output ---------------------------------------------------------------


def test_main_prints_run_id_and_tail_hint(tmp_path, capsys):
    train_home = tmp_path / "train-home"
    run_dir = train_home / "runs" / "abc123def456"
    write_progress(run_dir, run_id="abc123def456")

    exit_code = status.main(["--train-home", str(train_home)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "abc123def456" in captured.out
    assert "tail -f" in captured.out
    assert str(run_dir / "train.log") in captured.out


def test_main_returns_1_with_stderr_message_and_no_traceback(tmp_path, capsys):
    train_home = tmp_path / "train-home"
    exit_code = status.main(["--train-home", str(train_home)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err


def test_main_run_dir_flag(tmp_path, capsys):
    run_dir = tmp_path / "explicit-run"
    write_progress(run_dir, run_id="explicit-id")

    exit_code = status.main(["--run-dir", str(run_dir)])

    assert exit_code == 0
    assert "explicit-id" in capsys.readouterr().out


def test_main_run_id_flag(tmp_path, capsys):
    train_home = tmp_path / "train-home"
    run_dir = train_home / "runs" / "my-run-id"
    write_progress(run_dir, run_id="my-run-id")

    exit_code = status.main(["--train-home", str(train_home), "--run-id", "my-run-id"])

    assert exit_code == 0
    assert "my-run-id" in capsys.readouterr().out
