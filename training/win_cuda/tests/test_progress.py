"""Tests for plain-text + JSON progress reporting.

Pure stdlib. CPU-only, no torch, no GPU, no network. Clocks are injected via
list-backed fake monotonic counters and fixed datetimes so nothing depends
on real wall-clock timing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from stoic_training import progress


class FakeClock:
    """A monotonic() stand-in driven by an explicit list of return values."""

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> float:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


class FakeUtcNow:
    """A utc_now() stand-in driven by an explicit list of datetimes."""

    def __init__(self, values: list[datetime]) -> None:
        self._values = list(values)
        self._index = 0

    def __call__(self) -> datetime:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


# --- compute_total_steps -----------------------------------------------------


def test_compute_total_steps_sanity_anchor():
    assert (
        progress.compute_total_steps(
            num_examples=2374,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=16,
            num_train_epochs=2,
        )
        == 296
    )


def test_compute_total_steps_max_steps_override():
    assert (
        progress.compute_total_steps(
            num_examples=2374,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=16,
            num_train_epochs=2,
            max_steps=10,
        )
        == 10
    )


def test_compute_total_steps_tiny_dataset_floors_to_one_step_per_epoch():
    # len_dataloader // gradient_accumulation_steps would be 0; must floor to 1.
    steps = progress.compute_total_steps(
        num_examples=4,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        num_train_epochs=1,
    )
    assert steps == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_examples": 0, "per_device_train_batch_size": 1, "gradient_accumulation_steps": 1, "num_train_epochs": 1},
        {"num_examples": 10, "per_device_train_batch_size": 0, "gradient_accumulation_steps": 1, "num_train_epochs": 1},
        {"num_examples": 10, "per_device_train_batch_size": 1, "gradient_accumulation_steps": 0, "num_train_epochs": 1},
        {"num_examples": 10, "per_device_train_batch_size": 1, "gradient_accumulation_steps": 1, "num_train_epochs": 0},
        {"num_examples": -5, "per_device_train_batch_size": 1, "gradient_accumulation_steps": 1, "num_train_epochs": 1},
    ],
)
def test_compute_total_steps_validates_positive_inputs(kwargs):
    with pytest.raises(progress.ProgressError):
        progress.compute_total_steps(**kwargs)


# --- eta_seconds / steps_per_second / format_duration ------------------------


def test_eta_seconds_none_when_step_zero():
    assert progress.eta_seconds(step=0, total_steps=100, elapsed_s=10.0) is None


def test_eta_seconds_none_when_elapsed_not_positive():
    assert progress.eta_seconds(step=5, total_steps=100, elapsed_s=0.0) is None
    assert progress.eta_seconds(step=5, total_steps=100, elapsed_s=-1.0) is None


def test_eta_seconds_zero_when_step_reaches_total():
    assert progress.eta_seconds(step=100, total_steps=100, elapsed_s=50.0) == 0.0
    assert progress.eta_seconds(step=150, total_steps=100, elapsed_s=50.0) == 0.0


def test_eta_seconds_exact_value():
    # rate = 10 steps / 20s = 0.5 steps/s; remaining 40 steps -> 80s
    assert progress.eta_seconds(step=10, total_steps=50, elapsed_s=20.0) == pytest.approx(80.0)


def test_steps_per_second_edge_cases():
    assert progress.steps_per_second(step=0, elapsed_s=10.0) is None
    assert progress.steps_per_second(step=5, elapsed_s=0.0) is None
    assert progress.steps_per_second(step=5, elapsed_s=-1.0) is None
    assert progress.steps_per_second(step=10, elapsed_s=20.0) == pytest.approx(0.5)


def test_format_duration_branches():
    assert progress.format_duration(None) == "unknown"
    assert progress.format_duration(45) == "45s"
    assert progress.format_duration(60 * 12 + 3) == "12m 03s"
    assert progress.format_duration(3600 + 60 * 23 + 45) == "1h 23m 45s"


# --- ProgressSnapshot ----------------------------------------------------------


def test_progress_snapshot_to_dict_has_exact_keys():
    snapshot = progress.ProgressSnapshot(
        run_id="abc123",
        phase="train",
        step=45,
        total_steps=296,
        loss=1.2345,
        steps_per_sec=0.081,
        elapsed_s=555.0,
        eta_s=3092.0,
        eta_utc="2026-07-24T13:45:12+00:00",
        updated_utc="2026-07-24T12:53:40+00:00",
    )
    payload = snapshot.to_dict()
    assert set(payload) == {
        "run_id",
        "phase",
        "step",
        "total_steps",
        "loss",
        "steps_per_sec",
        "elapsed_s",
        "eta_s",
        "eta_utc",
        "updated_utc",
    }
    assert payload["step"] == 45
    assert payload["loss"] == 1.2345


def test_progress_snapshot_to_line_omits_none_fields():
    snapshot = progress.ProgressSnapshot(
        run_id="abc123",
        phase="train",
        step=0,
        total_steps=296,
        loss=None,
        steps_per_sec=None,
        elapsed_s=0.0,
        eta_s=None,
        eta_utc=None,
        updated_utc="2026-07-24T12:00:00+00:00",
    )
    line = snapshot.to_line()
    assert "None" not in line
    assert "loss=" not in line
    assert "eta=" not in line
    assert "step 0/296" in line


def test_progress_snapshot_to_line_includes_populated_fields():
    snapshot = progress.ProgressSnapshot(
        run_id="abc123",
        phase="train",
        step=45,
        total_steps=296,
        loss=1.2345,
        steps_per_sec=0.081,
        elapsed_s=555.0,
        eta_s=3092.0,
        eta_utc="2026-07-24T13:45:12+00:00",
        updated_utc="2026-07-24T12:53:40+00:00",
    )
    line = snapshot.to_line()
    assert "step 45/296" in line
    assert "loss=1.2345" in line
    assert "0.081 steps/s" in line
    assert "elapsed=" in line
    assert "eta=" in line
    assert "2026-07-24T13:45:12+00:00" in line


# --- ProgressWriter ------------------------------------------------------------


def make_writer(tmp_path, *, monotonic_values, utc_values):
    return progress.ProgressWriter(
        tmp_path / "run1",
        "run1",
        monotonic=FakeClock(monotonic_values),
        utc_now=FakeUtcNow(utc_values),
    )


def test_progress_writer_update_writes_progress_json_with_exact_keys(tmp_path):
    start = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 100.0],  # start, then elapsed() call inside update
        utc_values=[start, start + timedelta(seconds=100)],
    )
    snapshot = writer.update(step=10, total_steps=100, loss=0.5)

    payload = json.loads(writer.progress_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "run_id",
        "phase",
        "step",
        "total_steps",
        "loss",
        "steps_per_sec",
        "elapsed_s",
        "eta_s",
        "eta_utc",
        "updated_utc",
    }
    assert payload["run_id"] == "run1"
    assert payload["phase"] == "train"
    assert payload["step"] == 10
    assert payload["total_steps"] == 100
    assert payload["loss"] == 0.5
    assert payload["elapsed_s"] == pytest.approx(100.0)
    assert payload["steps_per_sec"] == pytest.approx(0.1)
    assert payload["eta_s"] == pytest.approx(900.0)
    assert snapshot.eta_utc is not None


def test_progress_writer_update_appends_to_log_file(tmp_path):
    start = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 10.0, 20.0],
        utc_values=[start] * 6,
    )
    writer.update(step=1, total_steps=10)
    writer.update(step=2, total_steps=10)

    lines = writer.log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "step 1/10" in lines[0]
    assert "step 2/10" in lines[1]


def test_progress_writer_log_works_before_any_update(tmp_path):
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)],
    )
    writer.log("starting up")
    text = writer.log_path.read_text(encoding="utf-8")
    assert "starting up" in text


def test_progress_writer_publishes_startup_snapshot_on_construction(tmp_path):
    """progress.json must exist from the first second so `status` never exits 1
    during the minutes a real run spends loading the base model."""
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)],
    )
    assert writer.progress_path.is_file()
    payload = json.loads(writer.progress_path.read_text(encoding="utf-8"))
    assert payload["step"] == 0
    assert payload["total_steps"] == 0
    assert payload["eta_s"] is None
    # The construction snapshot must not emit a log line of its own.
    assert not writer.log_path.exists() or writer.log_path.read_text(encoding="utf-8") == ""


def test_progress_writer_update_log_false_skips_log_line(tmp_path):
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 10.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)] * 4,
    )
    writer.update(step=1, total_steps=10, log=False)
    assert not writer.log_path.exists()
    assert writer.progress_path.exists()


def test_progress_writer_progress_json_always_parses_across_updates(tmp_path):
    start = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0],
        utc_values=[start] * 12,
    )
    for step in (1, 2, 3):
        writer.update(step=step, total_steps=10)
        payload = json.loads(writer.progress_path.read_text(encoding="utf-8"))
        assert payload["step"] == step

    # no leftover temp file after atomic replace
    assert not (tmp_path / "run1" / "progress.json.tmp").exists()


def test_progress_writer_set_phase_reflected_in_next_update(tmp_path):
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 10.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)] * 4,
    )
    writer.set_phase("eval")
    snapshot = writer.update(step=1, total_steps=10)
    assert snapshot.phase == "eval"


def test_progress_writer_finish_writes_terminal_snapshot(tmp_path):
    start = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 100.0, 200.0],
        utc_values=[start] * 8,
    )
    writer.update(step=100, total_steps=100)
    snapshot = writer.finish("run complete")

    assert snapshot.phase == "done"
    assert snapshot.step == 100
    assert snapshot.total_steps == 100
    assert snapshot.eta_s == 0.0

    payload = json.loads(writer.progress_path.read_text(encoding="utf-8"))
    assert payload["phase"] == "done"
    assert payload["eta_s"] == 0.0

    log_text = writer.log_path.read_text(encoding="utf-8")
    assert "run complete" in log_text


def test_progress_writer_finish_without_update_uses_zero_zero(tmp_path):
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 5.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)] * 4,
    )
    snapshot = writer.finish("aborted early")
    assert snapshot.step == 0
    assert snapshot.total_steps == 0


def test_progress_writer_creates_run_dir(tmp_path):
    run_dir = tmp_path / "nested" / "run2"
    writer = progress.ProgressWriter(
        run_dir,
        "run2",
        monotonic=FakeClock([0.0]),
        utc_now=FakeUtcNow([datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)]),
    )
    assert run_dir.is_dir()
    assert writer.log_path == run_dir / "train.log"
    assert writer.progress_path == run_dir / "progress.json"


# --- read_progress / format_progress -------------------------------------------


def test_read_progress_raises_when_missing(tmp_path):
    with pytest.raises(progress.ProgressError):
        progress.read_progress(tmp_path / "does-not-exist")


def test_read_progress_reads_written_snapshot(tmp_path):
    writer = make_writer(
        tmp_path,
        monotonic_values=[0.0, 10.0],
        utc_values=[datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)] * 4,
    )
    writer.update(step=3, total_steps=10)
    payload = progress.read_progress(tmp_path / "run1")
    assert payload["step"] == 3


def test_format_progress_handles_full_payload_without_raising():
    payload = {
        "run_id": "abc123",
        "phase": "train",
        "step": 45,
        "total_steps": 296,
        "loss": 1.2345,
        "steps_per_sec": 0.081,
        "elapsed_s": 555.0,
        "eta_s": 3092.0,
        "eta_utc": "2026-07-24T13:45:12+00:00",
        "updated_utc": "2026-07-24T12:53:40+00:00",
    }
    now = datetime(2026, 7, 24, 12, 54, 40, tzinfo=UTC)
    text = progress.format_progress(payload, now=now)
    assert "abc123" in text
    assert "45/296" in text
    assert "1m 00s ago" in text


def test_format_progress_tolerates_empty_dict():
    text = progress.format_progress({})
    assert "unknown" in text
    assert "run_id" in text


def test_format_progress_tolerates_partial_dict_with_bad_updated_utc():
    text = progress.format_progress({"step": 5, "phase": "train", "updated_utc": "not-a-date"})
    assert "5" in text
    assert "unknown" in text
