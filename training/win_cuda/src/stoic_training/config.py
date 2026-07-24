"""Strict schema loading and validation for config/qlora.yaml.

Purpose guardrail: this configures training for an OFFLINE research
assistant that proposes cited rule candidates for human review; its output
never touches any live trading path.

Validation is fail-closed: unknown keys, wrong types, and out-of-range
values are all rejected rather than coerced. Paths expand `${VAR}`
references (in particular `${STOIC_TRAIN_HOME}`, which defaults to
`<repo>/.artifacts/training` when unset) so the repo config never
hardcodes a host path.

Artifact locality (user directive 2026-07-24): run artifacts live
relative to the repo working directory, not `~`. The previous default
(`~/stoic-training`) hid logs on another drive and inflated the WSL VHD
on C:; the repo lives on F: with room to spare. `.artifacts/` is
git-ignored. Setting $STOIC_TRAIN_HOME still overrides this default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

import yaml

QUANT_TYPES = frozenset({"nf4", "fp4"})
COMPUTE_DTYPES = frozenset({"bfloat16", "float16"})

_TOP_LEVEL_FIELDS = frozenset(
    {"model", "quantization", "lora", "training", "paths", "smoke", "resources"}
)


class ConfigError(ValueError):
    """Raised when qlora.yaml is missing, malformed, or out of range."""


# src/stoic_training/config.py -> stoic_training -> src -> win_cuda -> training -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]


def default_train_home() -> Path:
    """Default artifact root: `<repo>/.artifacts/training` (git-ignored).

    Overridden by $STOIC_TRAIN_HOME. Keeping artifacts under the repo
    working directory is a user directive: it keeps run logs where the
    work is instead of on another drive, and keeps ~17 GB of cache and
    checkpoints out of the WSL VHD on C:.
    """
    return REPO_ROOT / ".artifacts" / "training"


def default_hf_home() -> Path:
    """HuggingFace cache location under the active train home."""
    env = os.environ.get("STOIC_TRAIN_HOME")
    base = Path(env).expanduser() if env else default_train_home()
    return base / "hf"


def ensure_hf_home() -> Path:
    """Point $HF_HOME at the train-home cache unless the caller already set it.

    Entrypoints call this before importing transformers (which reads
    HF_HOME at import time) so the migrated 16 GB base-model cache is
    reused instead of silently re-downloaded into ~/.cache/huggingface.
    """
    existing = os.environ.get("HF_HOME")
    if existing:
        return Path(existing).expanduser()
    resolved = default_hf_home()
    os.environ["HF_HOME"] = str(resolved)
    return resolved


def expand_path(raw: str, *, name: str) -> Path:
    """Expand `${VAR}` references, defaulting STOIC_TRAIN_HOME if unset."""
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"{name} must be a non-empty string")
    env = dict(os.environ)
    env.setdefault("STOIC_TRAIN_HOME", str(default_train_home()))
    expanded = Template(raw).safe_substitute(env)
    return Path(expanded).expanduser()


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ConfigError(f"{name} must be a mapping with string keys")
    return value


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unknown {', '.join(extra)}")
        raise ConfigError(f"{name} fields are invalid: {'; '.join(detail)}")


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _require_optional_str(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, name)


def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be a boolean")
    return value


def _require_int(
    value: object, name: str, *, minimum: int | None = None, maximum: int | None = None
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}")
    return value


def _require_float(
    value: object,
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_min: bool = False,
    exclusive_max: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    result = float(value)
    if minimum is not None:
        if exclusive_min and result <= minimum:
            raise ConfigError(f"{name} must be > {minimum}")
        if not exclusive_min and result < minimum:
            raise ConfigError(f"{name} must be >= {minimum}")
    if maximum is not None:
        if exclusive_max and result >= maximum:
            raise ConfigError(f"{name} must be < {maximum}")
        if not exclusive_max and result > maximum:
            raise ConfigError(f"{name} must be <= {maximum}")
    return result


def _require_str_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{name} must be a non-empty list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"{name} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ConfigError(f"{name} must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class ModelConfig:
    repo_id: str
    revision: str | None

    @classmethod
    def from_dict(cls, raw: object, name: str = "model") -> ModelConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(payload, frozenset({"repo_id", "revision"}), name)
        return cls(
            repo_id=_require_str(payload["repo_id"], f"{name}.repo_id"),
            revision=_require_optional_str(payload["revision"], f"{name}.revision"),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {"repo_id": self.repo_id, "revision": self.revision}


@dataclass(frozen=True, slots=True)
class QuantizationConfig:
    load_in_4bit: bool
    bnb_4bit_quant_type: str
    bnb_4bit_compute_dtype: str
    bnb_4bit_use_double_quant: bool

    @classmethod
    def from_dict(cls, raw: object, name: str = "quantization") -> QuantizationConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(
            payload,
            frozenset(
                {
                    "load_in_4bit",
                    "bnb_4bit_quant_type",
                    "bnb_4bit_compute_dtype",
                    "bnb_4bit_use_double_quant",
                }
            ),
            name,
        )
        quant_type = _require_str(payload["bnb_4bit_quant_type"], f"{name}.bnb_4bit_quant_type")
        if quant_type not in QUANT_TYPES:
            raise ConfigError(f"{name}.bnb_4bit_quant_type must be one of {sorted(QUANT_TYPES)}")
        compute_dtype = _require_str(
            payload["bnb_4bit_compute_dtype"], f"{name}.bnb_4bit_compute_dtype"
        )
        if compute_dtype not in COMPUTE_DTYPES:
            raise ConfigError(
                f"{name}.bnb_4bit_compute_dtype must be one of {sorted(COMPUTE_DTYPES)}"
            )
        return cls(
            load_in_4bit=_require_bool(payload["load_in_4bit"], f"{name}.load_in_4bit"),
            bnb_4bit_quant_type=quant_type,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=_require_bool(
                payload["bnb_4bit_use_double_quant"], f"{name}.bnb_4bit_use_double_quant"
            ),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "load_in_4bit": self.load_in_4bit,
            "bnb_4bit_quant_type": self.bnb_4bit_quant_type,
            "bnb_4bit_compute_dtype": self.bnb_4bit_compute_dtype,
            "bnb_4bit_use_double_quant": self.bnb_4bit_use_double_quant,
        }


@dataclass(frozen=True, slots=True)
class LoraConfig:
    r: int
    alpha: int
    dropout: float
    target_modules: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: object, name: str = "lora") -> LoraConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(
            payload, frozenset({"r", "alpha", "dropout", "target_modules"}), name
        )
        return cls(
            r=_require_int(payload["r"], f"{name}.r", minimum=1),
            alpha=_require_int(payload["alpha"], f"{name}.alpha", minimum=1),
            dropout=_require_float(
                payload["dropout"], f"{name}.dropout", minimum=0.0, maximum=1.0, exclusive_max=True
            ),
            target_modules=_require_str_list(payload["target_modules"], f"{name}.target_modules"),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "r": self.r,
            "alpha": self.alpha,
            "dropout": self.dropout,
            "target_modules": list(self.target_modules),
        }


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    max_seq_len: int
    per_device_train_batch_size: int
    per_device_eval_batch_size: int
    gradient_accumulation_steps: int
    gradient_checkpointing: bool
    optim: str
    learning_rate: float
    lr_scheduler_type: str
    warmup_ratio: float
    num_train_epochs: int
    seed: int
    logging_steps: int
    save_steps: int
    save_total_limit: int
    eval_steps: int
    attn_implementation: str
    bf16: bool

    @classmethod
    def from_dict(cls, raw: object, name: str = "training") -> TrainingConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(
            payload,
            frozenset(
                {
                    "max_seq_len",
                    "per_device_train_batch_size",
                    "per_device_eval_batch_size",
                    "gradient_accumulation_steps",
                    "gradient_checkpointing",
                    "optim",
                    "learning_rate",
                    "lr_scheduler_type",
                    "warmup_ratio",
                    "num_train_epochs",
                    "seed",
                    "logging_steps",
                    "save_steps",
                    "save_total_limit",
                    "eval_steps",
                    "attn_implementation",
                    "bf16",
                }
            ),
            name,
        )
        return cls(
            max_seq_len=_require_int(payload["max_seq_len"], f"{name}.max_seq_len", minimum=1),
            per_device_train_batch_size=_require_int(
                payload["per_device_train_batch_size"],
                f"{name}.per_device_train_batch_size",
                minimum=1,
            ),
            per_device_eval_batch_size=_require_int(
                payload["per_device_eval_batch_size"],
                f"{name}.per_device_eval_batch_size",
                minimum=1,
            ),
            gradient_accumulation_steps=_require_int(
                payload["gradient_accumulation_steps"],
                f"{name}.gradient_accumulation_steps",
                minimum=1,
            ),
            gradient_checkpointing=_require_bool(
                payload["gradient_checkpointing"], f"{name}.gradient_checkpointing"
            ),
            optim=_require_str(payload["optim"], f"{name}.optim"),
            learning_rate=_require_float(
                payload["learning_rate"], f"{name}.learning_rate", minimum=0.0, exclusive_min=True
            ),
            lr_scheduler_type=_require_str(
                payload["lr_scheduler_type"], f"{name}.lr_scheduler_type"
            ),
            warmup_ratio=_require_float(
                payload["warmup_ratio"], f"{name}.warmup_ratio", minimum=0.0, maximum=1.0
            ),
            num_train_epochs=_require_int(
                payload["num_train_epochs"], f"{name}.num_train_epochs", minimum=1
            ),
            seed=_require_int(payload["seed"], f"{name}.seed", minimum=0),
            logging_steps=_require_int(payload["logging_steps"], f"{name}.logging_steps", minimum=1),
            save_steps=_require_int(payload["save_steps"], f"{name}.save_steps", minimum=1),
            save_total_limit=_require_int(
                payload["save_total_limit"], f"{name}.save_total_limit", minimum=1
            ),
            eval_steps=_require_int(payload["eval_steps"], f"{name}.eval_steps", minimum=1),
            attn_implementation=_require_str(
                payload["attn_implementation"], f"{name}.attn_implementation"
            ),
            bf16=_require_bool(payload["bf16"], f"{name}.bf16"),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "max_seq_len": self.max_seq_len,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "per_device_eval_batch_size": self.per_device_eval_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "gradient_checkpointing": self.gradient_checkpointing,
            "optim": self.optim,
            "learning_rate": self.learning_rate,
            "lr_scheduler_type": self.lr_scheduler_type,
            "warmup_ratio": self.warmup_ratio,
            "num_train_epochs": self.num_train_epochs,
            "seed": self.seed,
            "logging_steps": self.logging_steps,
            "save_steps": self.save_steps,
            "save_total_limit": self.save_total_limit,
            "eval_steps": self.eval_steps,
            "attn_implementation": self.attn_implementation,
            "bf16": self.bf16,
        }


@dataclass(frozen=True, slots=True)
class PathsConfig:
    dataset_dir: Path
    run_dir: Path

    @classmethod
    def from_dict(cls, raw: object, name: str = "paths") -> PathsConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(payload, frozenset({"dataset_dir", "run_dir"}), name)
        return cls(
            dataset_dir=expand_path(payload["dataset_dir"], name=f"{name}.dataset_dir"),
            run_dir=expand_path(payload["run_dir"], name=f"{name}.run_dir"),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {"dataset_dir": str(self.dataset_dir), "run_dir": str(self.run_dir)}


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    max_steps: int
    max_seq_len: int

    @classmethod
    def from_dict(cls, raw: object, name: str = "smoke") -> SmokeConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(payload, frozenset({"max_steps", "max_seq_len"}), name)
        return cls(
            max_steps=_require_int(payload["max_steps"], f"{name}.max_steps", minimum=1),
            max_seq_len=_require_int(payload["max_seq_len"], f"{name}.max_seq_len", minimum=1),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {"max_steps": self.max_steps, "max_seq_len": self.max_seq_len}


@dataclass(frozen=True, slots=True)
class ResourcesConfig:
    """Memory/VRAM budget knobs consumed by resources.py's preflight helpers.

    Real incident this fixes: export.py once merged an 8B bf16 model with a
    hardcoded max_memory cap that, combined with the Windows desktop's own
    VRAM use, hung the whole box (see resources.py's module docstring). These
    fields let train.py and export.py compute safe, host-specific caps
    instead of hardcoding them.
    """

    min_free_vram_gib: float
    export_gpu_cap_gib: float
    export_vram_headroom_gib: float
    export_cpu_reserve_gib: float
    dataloader_num_workers: int
    dataloader_pin_memory: bool

    @classmethod
    def from_dict(cls, raw: object, name: str = "resources") -> ResourcesConfig:
        payload = _require_mapping(raw, name)
        _require_exact_fields(
            payload,
            frozenset(
                {
                    "min_free_vram_gib",
                    "export_gpu_cap_gib",
                    "export_vram_headroom_gib",
                    "export_cpu_reserve_gib",
                    "dataloader_num_workers",
                    "dataloader_pin_memory",
                }
            ),
            name,
        )
        return cls(
            min_free_vram_gib=_require_float(
                payload["min_free_vram_gib"], f"{name}.min_free_vram_gib", minimum=0.0
            ),
            export_gpu_cap_gib=_require_float(
                payload["export_gpu_cap_gib"], f"{name}.export_gpu_cap_gib", minimum=0.0
            ),
            export_vram_headroom_gib=_require_float(
                payload["export_vram_headroom_gib"],
                f"{name}.export_vram_headroom_gib",
                minimum=0.0,
            ),
            export_cpu_reserve_gib=_require_float(
                payload["export_cpu_reserve_gib"], f"{name}.export_cpu_reserve_gib", minimum=0.0
            ),
            dataloader_num_workers=_require_int(
                payload["dataloader_num_workers"], f"{name}.dataloader_num_workers", minimum=0
            ),
            dataloader_pin_memory=_require_bool(
                payload["dataloader_pin_memory"], f"{name}.dataloader_pin_memory"
            ),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "min_free_vram_gib": self.min_free_vram_gib,
            "export_gpu_cap_gib": self.export_gpu_cap_gib,
            "export_vram_headroom_gib": self.export_vram_headroom_gib,
            "export_cpu_reserve_gib": self.export_cpu_reserve_gib,
            "dataloader_num_workers": self.dataloader_num_workers,
            "dataloader_pin_memory": self.dataloader_pin_memory,
        }

    @property
    def min_free_vram_bytes(self) -> int:
        return int(self.min_free_vram_gib * 1024**3)

    @property
    def export_gpu_cap_bytes(self) -> int:
        return int(self.export_gpu_cap_gib * 1024**3)

    @property
    def export_vram_headroom_bytes(self) -> int:
        return int(self.export_vram_headroom_gib * 1024**3)

    @property
    def export_cpu_reserve_bytes(self) -> int:
        return int(self.export_cpu_reserve_gib * 1024**3)


@dataclass(frozen=True, slots=True)
class QloraConfig:
    model: ModelConfig
    quantization: QuantizationConfig
    lora: LoraConfig
    training: TrainingConfig
    paths: PathsConfig
    smoke: SmokeConfig
    resources: ResourcesConfig

    @classmethod
    def from_dict(cls, raw: object) -> QloraConfig:
        payload = _require_mapping(raw, "qlora")
        _require_exact_fields(payload, _TOP_LEVEL_FIELDS, "qlora")
        return cls(
            model=ModelConfig.from_dict(payload["model"]),
            quantization=QuantizationConfig.from_dict(payload["quantization"]),
            lora=LoraConfig.from_dict(payload["lora"]),
            training=TrainingConfig.from_dict(payload["training"]),
            paths=PathsConfig.from_dict(payload["paths"]),
            smoke=SmokeConfig.from_dict(payload["smoke"]),
            resources=ResourcesConfig.from_dict(payload["resources"]),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.canonical_dict(),
            "quantization": self.quantization.canonical_dict(),
            "lora": self.lora.canonical_dict(),
            "training": self.training.canonical_dict(),
            "paths": self.paths.canonical_dict(),
            "smoke": self.smoke.canonical_dict(),
            "resources": self.resources.canonical_dict(),
        }

    def resolved_dict(self, *, smoke: bool) -> dict[str, Any]:
        """Canonical config actually applied to a run, smoke overrides folded in."""
        payload = self.canonical_dict()
        payload["smoke_mode"] = smoke
        if smoke:
            training = dict(payload["training"])
            training["max_seq_len"] = self.smoke.max_seq_len
            training["max_steps"] = self.smoke.max_steps
            payload["training"] = training
        return payload


def load_config(path: str | Path) -> QloraConfig:
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    return QloraConfig.from_dict(raw)


__all__ = [
    "REPO_ROOT",
    "ConfigError",
    "LoraConfig",
    "ModelConfig",
    "PathsConfig",
    "QloraConfig",
    "QuantizationConfig",
    "ResourcesConfig",
    "SmokeConfig",
    "TrainingConfig",
    "default_hf_home",
    "default_train_home",
    "ensure_hf_home",
    "expand_path",
    "load_config",
]
