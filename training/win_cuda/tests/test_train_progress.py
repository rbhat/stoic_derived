"""Tests for train.py's pure, testable progress/preflight helpers.

CPU-only, no GPU, no network, and no torch/transformers import: VRAM and
allocator behaviour are exercised entirely through injected stubs/probes, as
train.py's own docstring requires for this heavy-import-deferred module.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stoic_training import train


# --- configure_allocator -----------------------------------------------------


def test_configure_allocator_sets_when_unset():
    env: dict[str, str] = {}
    result = train.configure_allocator(env)
    assert result == "expandable_segments:True"
    assert env["PYTORCH_CUDA_ALLOC_CONF"] == "expandable_segments:True"


def test_configure_allocator_respects_existing_value():
    env = {"PYTORCH_CUDA_ALLOC_CONF": "garbage_collection_threshold:0.8"}
    result = train.configure_allocator(env)
    assert result == "garbage_collection_threshold:0.8"
    assert env["PYTORCH_CUDA_ALLOC_CONF"] == "garbage_collection_threshold:0.8"


def test_configure_allocator_defaults_to_os_environ(monkeypatch):
    monkeypatch.delenv("PYTORCH_CUDA_ALLOC_CONF", raising=False)
    import os

    result = train.configure_allocator()
    assert result == "expandable_segments:True"
    assert os.environ["PYTORCH_CUDA_ALLOC_CONF"] == "expandable_segments:True"


# --- preflight_vram -----------------------------------------------------------


def make_config(min_free_vram_gib: float):
    """A minimal stand-in for QloraConfig: preflight_vram only reads
    config.resources.min_free_vram_bytes."""
    resources_stub = SimpleNamespace(
        min_free_vram_bytes=int(min_free_vram_gib * 1024**3)
    )
    return SimpleNamespace(resources=resources_stub)


def test_preflight_vram_ok_when_plenty_free():
    config = make_config(min_free_vram_gib=10.0)
    check = train.preflight_vram(
        config, allow_low_vram=False, probe=lambda: (12 * 1024**3, 16 * 1024**3)
    )
    assert check.ok is True


def test_preflight_vram_refuses_and_mentions_lm_studio():
    config = make_config(min_free_vram_gib=10.0)
    with pytest.raises(train.TrainingRefusalError) as excinfo:
        train.preflight_vram(
            config, allow_low_vram=False, probe=lambda: (4 * 1024**3, 16 * 1024**3)
        )
    assert "LM Studio" in str(excinfo.value)


def test_preflight_vram_cuda_unavailable_passes():
    config = make_config(min_free_vram_gib=10.0)
    check = train.preflight_vram(config, allow_low_vram=False, probe=lambda: None)
    assert check.ok is True
    assert "cuda unavailable" in check.reason


def test_preflight_vram_allow_low_vram_bypasses_refusal():
    config = make_config(min_free_vram_gib=10.0)
    check = train.preflight_vram(
        config, allow_low_vram=True, probe=lambda: (4 * 1024**3, 16 * 1024**3)
    )
    assert check.ok is False
    assert "LM Studio" in check.reason


# --- resolve_total_steps -------------------------------------------------------


def test_resolve_total_steps_prefers_state_max_steps_when_positive():
    assert train.resolve_total_steps(state_max_steps=42, fallback_total_steps=296) == 42


def test_resolve_total_steps_falls_back_when_state_max_steps_not_positive():
    assert train.resolve_total_steps(state_max_steps=0, fallback_total_steps=296) == 296
    assert train.resolve_total_steps(state_max_steps=-1, fallback_total_steps=296) == 296


# --- handle_log_event ----------------------------------------------------------


class StubWriter:
    """Records update() calls; return value mimics a ProgressSnapshot enough
    for handle_log_event's tests (identity is all that's checked)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def update(self, *, step, total_steps, loss=None):
        snapshot = SimpleNamespace(step=step, total_steps=total_steps, loss=loss)
        self.calls.append({"step": step, "total_steps": total_steps, "loss": loss})
        return snapshot


def test_handle_log_event_with_loss_present():
    writer = StubWriter()
    snapshot = train.handle_log_event(
        writer,
        step=5,
        state_max_steps=0,
        fallback_total_steps=100,
        logs={"loss": 1.25, "learning_rate": 0.0002},
    )
    assert snapshot is not None
    assert snapshot.step == 5
    assert snapshot.total_steps == 100
    assert snapshot.loss == pytest.approx(1.25)
    assert writer.calls == [{"step": 5, "total_steps": 100, "loss": 1.25}]


def test_handle_log_event_with_loss_absent_still_updates_with_none():
    writer = StubWriter()
    snapshot = train.handle_log_event(
        writer,
        step=10,
        state_max_steps=0,
        fallback_total_steps=100,
        logs={"eval_loss": 0.9},
    )
    assert snapshot is not None
    assert snapshot.loss is None
    assert writer.calls == [{"step": 10, "total_steps": 100, "loss": None}]


def test_handle_log_event_step_non_positive_returns_none_and_does_not_update():
    writer = StubWriter()
    assert train.handle_log_event(
        writer, step=0, state_max_steps=0, fallback_total_steps=100, logs={"loss": 1.0}
    ) is None
    assert train.handle_log_event(
        writer, step=-3, state_max_steps=0, fallback_total_steps=100, logs=None
    ) is None
    assert writer.calls == []


def test_handle_log_event_state_max_steps_overrides_fallback():
    writer = StubWriter()
    train.handle_log_event(
        writer,
        step=5,
        state_max_steps=42,
        fallback_total_steps=296,
        logs={"loss": 0.5},
    )
    assert writer.calls == [{"step": 5, "total_steps": 42, "loss": 0.5}]


def test_handle_log_event_logs_none_still_updates_with_loss_none():
    writer = StubWriter()
    snapshot = train.handle_log_event(
        writer, step=3, state_max_steps=0, fallback_total_steps=50, logs=None
    )
    assert snapshot is not None
    assert snapshot.loss is None
    assert writer.calls == [{"step": 3, "total_steps": 50, "loss": None}]
