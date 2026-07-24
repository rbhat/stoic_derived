"""Plain-text + JSON progress reporting for long-running training entrypoints.

Purpose guardrail: this reports progress for training an OFFLINE research
assistant SLM that proposes cited rule candidates for human review; its
output never touches any live trading path. It only writes log lines and a
progress.json file describing training/export/evaluate progress.

Pure stdlib. No torch/transformers/etc. import, so this module stays cheap
to import from tests and from train.py/export.py/evaluate.py at startup.
Callers `tail -f <run_dir>/train.log` for a human log and poll
`<run_dir>/progress.json` for a machine-readable snapshot with an ETA.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class ProgressError(RuntimeError):
    """Raised when progress arithmetic is invalid or progress.json is unusable."""


def compute_total_steps(
    *,
    num_examples: int,
    per_device_train_batch_size: int,
    gradient_accumulation_steps: int,
    num_train_epochs: int,
    max_steps: int = -1,
    world_size: int = 1,
) -> int:
    """Mirror HuggingFace Trainer's own step arithmetic so ETA matches reality."""
    if max_steps > 0:
        return max_steps
    if num_examples <= 0:
        raise ProgressError(f"num_examples must be positive, got {num_examples}")
    if per_device_train_batch_size <= 0:
        raise ProgressError(
            f"per_device_train_batch_size must be positive, got {per_device_train_batch_size}"
        )
    if gradient_accumulation_steps <= 0:
        raise ProgressError(
            f"gradient_accumulation_steps must be positive, got {gradient_accumulation_steps}"
        )
    if num_train_epochs <= 0:
        raise ProgressError(f"num_train_epochs must be positive, got {num_train_epochs}")
    if world_size <= 0:
        raise ProgressError(f"world_size must be positive, got {world_size}")

    len_dataloader = math.ceil(num_examples / (per_device_train_batch_size * world_size))
    num_update_steps_per_epoch = max(len_dataloader // gradient_accumulation_steps, 1)
    return math.ceil(num_train_epochs * num_update_steps_per_epoch)


def eta_seconds(*, step: int, total_steps: int, elapsed_s: float) -> float | None:
    """Average-rate ETA in seconds, or None when it cannot be estimated."""
    if step <= 0 or elapsed_s <= 0:
        return None
    if step >= total_steps:
        return 0.0
    return (total_steps - step) * (elapsed_s / step)


def steps_per_second(*, step: int, elapsed_s: float) -> float | None:
    if step <= 0 or elapsed_s <= 0:
        return None
    return step / elapsed_s


def format_duration(seconds: float | None) -> str:
    """Render seconds as "1h 23m 45s" / "12m 03s" / "45s"; "unknown" for None."""
    if seconds is None:
        return "unknown"
    total = int(round(seconds))
    if total < 0:
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _default_utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    run_id: str
    phase: str
    step: int
    total_steps: int
    loss: float | None
    steps_per_sec: float | None
    elapsed_s: float
    eta_s: float | None
    eta_utc: str | None
    updated_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "step": self.step,
            "total_steps": self.total_steps,
            "loss": self.loss,
            "steps_per_sec": self.steps_per_sec,
            "elapsed_s": self.elapsed_s,
            "eta_s": self.eta_s,
            "eta_utc": self.eta_utc,
            "updated_utc": self.updated_utc,
        }

    def to_line(self) -> str:
        pct = (self.step / self.total_steps * 100) if self.total_steps > 0 else 0.0
        parts = [f"{self.phase} step {self.step}/{self.total_steps} ({pct:.1f}%)"]
        if self.loss is not None:
            parts.append(f"loss={self.loss:.4f}")
        if self.steps_per_sec is not None:
            parts.append(f"{self.steps_per_sec:.3f} steps/s")
        parts.append(f"elapsed={format_duration(self.elapsed_s)}")
        if self.eta_s is not None:
            eta_bit = f"eta={format_duration(self.eta_s)}"
            if self.eta_utc is not None:
                eta_bit += f" (ETA {self.eta_utc})"
            parts.append(eta_bit)
        return " ".join(parts)


class ProgressWriter:
    """Appends human-readable lines to <run_dir>/<log_name> and rewrites
    <run_dir>/progress.json on every update."""

    def __init__(
        self,
        run_dir: str | Path,
        run_id: str,
        *,
        log_name: str = "train.log",
        phase: str = "train",
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = _default_utc_now,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._phase = phase
        self._monotonic = monotonic
        self._utc_now = utc_now
        self._start = monotonic()
        self.log_path = self.run_dir / log_name
        self.progress_path = self.run_dir / "progress.json"
        self._last_step = 0
        self._last_total_steps = 0
        # Write a snapshot immediately so `status` has something to report from
        # the very first second of a run. Without this, progress.json only
        # appears at the first logging step -- minutes into a real run, while
        # the base model loads -- and status would exit 1 as if nothing ran.
        self.update(step=0, total_steps=0, log=False)

    def log(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{self._utc_now().isoformat()}] {message}\n")
            handle.flush()

    def elapsed(self) -> float:
        return self._monotonic() - self._start

    def _write_progress_json(self, snapshot: ProgressSnapshot) -> None:
        payload = json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n"
        tmp_path = self.progress_path.with_suffix(".json.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.progress_path)

    def update(
        self,
        *,
        step: int,
        total_steps: int,
        loss: float | None = None,
        phase: str | None = None,
        log: bool = True,
    ) -> ProgressSnapshot:
        if phase is not None:
            self._phase = phase
        elapsed_s = self.elapsed()
        eta_s = eta_seconds(step=step, total_steps=total_steps, elapsed_s=elapsed_s)
        eta_utc = (
            (self._utc_now() + timedelta(seconds=eta_s)).isoformat() if eta_s is not None else None
        )
        snapshot = ProgressSnapshot(
            run_id=self.run_id,
            phase=self._phase,
            step=step,
            total_steps=total_steps,
            loss=loss,
            steps_per_sec=steps_per_second(step=step, elapsed_s=elapsed_s),
            elapsed_s=elapsed_s,
            eta_s=eta_s,
            eta_utc=eta_utc,
            updated_utc=self._utc_now().isoformat(),
        )
        self._write_progress_json(snapshot)
        if log:
            self.log(snapshot.to_line())
        self._last_step = step
        self._last_total_steps = total_steps
        return snapshot

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def finish(self, message: str, *, phase: str = "done") -> ProgressSnapshot:
        self._phase = phase
        self.log(message)
        elapsed_s = self.elapsed()
        snapshot = ProgressSnapshot(
            run_id=self.run_id,
            phase=self._phase,
            step=self._last_total_steps,
            total_steps=self._last_total_steps,
            loss=None,
            steps_per_sec=steps_per_second(step=self._last_total_steps, elapsed_s=elapsed_s),
            elapsed_s=elapsed_s,
            eta_s=0.0,
            eta_utc=self._utc_now().isoformat(),
            updated_utc=self._utc_now().isoformat(),
        )
        self._write_progress_json(snapshot)
        return snapshot


def read_progress(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "progress.json"
    if not path.is_file():
        raise ProgressError(f"no progress.json found at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProgressError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProgressError(f"{path} must contain a JSON object")
    return payload


def format_progress(payload: Mapping[str, Any], *, now: datetime | None = None) -> str:
    """Render a partial/missing-key progress payload as a human-readable block."""

    def get(key: str) -> Any:
        return payload.get(key)

    run_id = get("run_id") or "unknown"
    phase = get("phase") or "unknown"
    step = get("step")
    total_steps = get("total_steps")
    if isinstance(step, int) and isinstance(total_steps, int) and total_steps > 0:
        pct = step / total_steps * 100
        step_line = f"step {step}/{total_steps} ({pct:.1f}%)"
    elif isinstance(step, int) and isinstance(total_steps, int):
        step_line = f"step {step}/{total_steps}"
    elif isinstance(step, int):
        step_line = f"step {step}/unknown"
    else:
        step_line = "step unknown"

    loss = get("loss")
    loss_line = f"{loss:.4f}" if isinstance(loss, (int, float)) else "unknown"

    steps_per_sec = get("steps_per_sec")
    rate_line = (
        f"{steps_per_sec:.3f} steps/s" if isinstance(steps_per_sec, (int, float)) else "unknown"
    )

    elapsed_s = get("elapsed_s")
    elapsed_line = (
        format_duration(elapsed_s) if isinstance(elapsed_s, (int, float)) else "unknown"
    )

    eta_s = get("eta_s")
    eta_duration = format_duration(eta_s) if isinstance(eta_s, (int, float)) else "unknown"
    eta_utc = get("eta_utc") or "unknown"

    updated_utc = get("updated_utc")
    staleness = "unknown"
    if isinstance(updated_utc, str):
        try:
            updated_dt = datetime.fromisoformat(updated_utc)
        except ValueError:
            updated_dt = None
        if updated_dt is not None:
            reference = now if now is not None else datetime.now(UTC)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=UTC)
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=UTC)
            age_s = (reference - updated_dt).total_seconds()
            if age_s < 0:
                staleness = "updated in the future (clock skew?)"
            else:
                staleness = f"{format_duration(age_s)} ago"

    return "\n".join(
        [
            f"run_id: {run_id}",
            f"phase: {phase}",
            step_line,
            f"loss: {loss_line}",
            f"rate: {rate_line}",
            f"elapsed: {elapsed_line}",
            f"eta: {eta_duration} (ETA {eta_utc})",
            f"updated_utc: {updated_utc if isinstance(updated_utc, str) else 'unknown'}"
            f" ({staleness})",
        ]
    )


__all__ = [
    "ProgressError",
    "ProgressSnapshot",
    "ProgressWriter",
    "compute_total_steps",
    "eta_seconds",
    "format_duration",
    "format_progress",
    "read_progress",
    "steps_per_second",
]
