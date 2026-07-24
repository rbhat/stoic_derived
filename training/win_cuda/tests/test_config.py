"""Tests for qlora.yaml schema loading and validation.

CPU-only, no network, no GPU: config.py imports only stdlib + PyYAML.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from stoic_training.config import REPO_ROOT, ConfigError, load_config

VALID_CONFIG = {
    "model": {"repo_id": "Qwen/Qwen3-8B", "revision": None},
    "quantization": {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "bfloat16",
        "bnb_4bit_use_double_quant": True,
    },
    "lora": {
        "r": 16,
        "alpha": 32,
        "dropout": 0.05,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    },
    "training": {
        "max_seq_len": 1024,
        "per_device_train_batch_size": 1,
        "per_device_eval_batch_size": 2,
        "gradient_accumulation_steps": 16,
        "gradient_checkpointing": True,
        "optim": "paged_adamw_8bit",
        "learning_rate": 0.0002,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.03,
        "num_train_epochs": 2,
        "seed": 20260724,
        "logging_steps": 10,
        "save_steps": 50,
        "save_total_limit": 2,
        "eval_steps": 200,
        "attn_implementation": "sdpa",
        "bf16": True,
    },
    "paths": {
        "dataset_dir": "${STOIC_TRAIN_HOME}/datasets/v1",
        "run_dir": "${STOIC_TRAIN_HOME}/runs",
    },
    "smoke": {"max_steps": 10, "max_seq_len": 512},
    "resources": {
        "min_free_vram_gib": 10.0,
        "export_gpu_cap_gib": 12.0,
        "export_vram_headroom_gib": 2.0,
        "export_cpu_reserve_gib": 4.0,
        "dataloader_num_workers": 0,
        "dataloader_pin_memory": False,
    },
}


def write_yaml(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "qlora.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def deep_copy(payload):
    return yaml.safe_load(yaml.safe_dump(payload))


def test_loads_valid_config_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path / "train-home"))
    path = write_yaml(tmp_path, VALID_CONFIG)

    config = load_config(path)

    assert config.model.repo_id == "Qwen/Qwen3-8B"
    assert config.model.revision is None
    assert config.quantization.bnb_4bit_quant_type == "nf4"
    assert config.lora.r == 16
    assert config.lora.target_modules == (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )
    assert config.training.max_seq_len == 1024
    assert config.training.learning_rate == pytest.approx(0.0002)
    assert config.training.per_device_eval_batch_size == 2
    assert config.training.save_total_limit == 2
    assert config.paths.dataset_dir == tmp_path / "train-home" / "datasets" / "v1"
    assert config.paths.run_dir == tmp_path / "train-home" / "runs"
    assert config.smoke.max_steps == 10
    assert config.resources.min_free_vram_gib == pytest.approx(10.0)
    assert config.resources.export_gpu_cap_gib == pytest.approx(12.0)
    assert config.resources.export_vram_headroom_gib == pytest.approx(2.0)
    assert config.resources.export_cpu_reserve_gib == pytest.approx(4.0)
    assert config.resources.dataloader_num_workers == 0
    assert config.resources.dataloader_pin_memory is False
    assert config.resources.min_free_vram_bytes == int(10.0 * 1024**3)
    assert config.resources.export_gpu_cap_bytes == int(12.0 * 1024**3)
    assert config.resources.export_vram_headroom_bytes == int(2.0 * 1024**3)
    assert config.resources.export_cpu_reserve_bytes == int(4.0 * 1024**3)


def test_dataset_dir_defaults_under_repo_when_train_home_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("STOIC_TRAIN_HOME", raising=False)
    path = write_yaml(tmp_path, VALID_CONFIG)

    config = load_config(path)

    assert config.paths.dataset_dir == REPO_ROOT / ".artifacts" / "training" / "datasets" / "v1"


def test_resolved_dict_applies_smoke_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    path = write_yaml(tmp_path, VALID_CONFIG)
    config = load_config(path)

    resolved = config.resolved_dict(smoke=True)
    assert resolved["smoke_mode"] is True
    assert resolved["training"]["max_seq_len"] == 512
    assert resolved["training"]["max_steps"] == 10

    not_smoke = config.resolved_dict(smoke=False)
    assert not_smoke["smoke_mode"] is False
    assert not_smoke["training"]["max_seq_len"] == 1024
    assert "max_steps" not in not_smoke["training"]


def test_rejects_unknown_top_level_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload["unexpected_section"] = {"foo": "bar"}
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="unknown"):
        load_config(path)


def test_rejects_missing_required_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    del payload["lora"]["dropout"]
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)


def test_rejects_unknown_nested_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload["lora"]["extra_field"] = 1
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="unknown"):
        load_config(path)


def test_rejects_missing_top_level_resources_section(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    del payload["resources"]
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)


def test_rejects_missing_resources_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    del payload["resources"]["export_gpu_cap_gib"]
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)


def test_rejects_unknown_resources_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload["resources"]["extra_field"] = 1
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="unknown"):
        load_config(path)


def test_rejects_missing_training_per_device_eval_batch_size(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    del payload["training"]["per_device_eval_batch_size"]
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)


def test_rejects_missing_training_save_total_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    del payload["training"]["save_total_limit"]
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("lora", "r", 0),
        ("lora", "r", -1),
        ("lora", "r", 1.5),
        ("lora", "dropout", 1.0),
        ("lora", "dropout", -0.1),
        ("training", "max_seq_len", 0),
        ("training", "per_device_train_batch_size", 0),
        ("training", "gradient_accumulation_steps", 0),
        ("training", "learning_rate", 0.0),
        ("training", "learning_rate", -0.1),
        ("training", "warmup_ratio", 1.5),
        ("training", "warmup_ratio", -0.1),
        ("training", "num_train_epochs", 0),
        ("training", "gradient_checkpointing", "true"),
        ("training", "per_device_eval_batch_size", 0),
        ("training", "per_device_eval_batch_size", 1.5),
        ("training", "save_total_limit", 0),
        ("training", "save_total_limit", -1),
        ("quantization", "bnb_4bit_quant_type", "int8"),
        ("quantization", "bnb_4bit_compute_dtype", "float32"),
        ("smoke", "max_steps", 0),
        ("smoke", "max_seq_len", -1),
        ("resources", "min_free_vram_gib", -1.0),
        ("resources", "min_free_vram_gib", "10.0"),
        ("resources", "export_gpu_cap_gib", -0.1),
        ("resources", "export_vram_headroom_gib", -0.1),
        ("resources", "export_cpu_reserve_gib", -0.1),
        ("resources", "dataloader_num_workers", -1),
        ("resources", "dataloader_num_workers", 1.5),
        ("resources", "dataloader_pin_memory", "false"),
    ],
)
def test_rejects_out_of_range_or_wrong_type_values(tmp_path, monkeypatch, section, key, value):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload[section][key] = value
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_empty_target_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload["lora"]["target_modules"] = []
    path = write_yaml(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_non_mapping_top_level(tmp_path):
    path = tmp_path / "qlora.yaml"
    path.write_text(yaml.safe_dump(["not", "a", "mapping"]), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)


def test_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "qlora.yaml"
    path.write_text("model: [unterminated", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)


def test_model_revision_accepts_pinned_string(tmp_path, monkeypatch):
    monkeypatch.setenv("STOIC_TRAIN_HOME", str(tmp_path))
    payload = deep_copy(VALID_CONFIG)
    payload["model"]["revision"] = "b968826d9c46dd6066d109eabc6255188de91218"
    path = write_yaml(tmp_path, payload)

    config = load_config(path)
    assert config.model.revision == "b968826d9c46dd6066d109eabc6255188de91218"
