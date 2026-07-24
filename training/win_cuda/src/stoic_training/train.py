"""QLoRA SFT training entrypoint for the offline research-assistant SLM.

Purpose guardrail: this trains an OFFLINE research assistant that proposes
cited rule candidates for human review; its output never touches any live
trading path.

CLI: python -m stoic_training.train --config config/qlora.yaml [--smoke] [--resume]
                                     [--allow-low-vram]

A non-smoke run REFUSES to start while config.model.revision is null
(model.revision must be hand-pinned to an exact HuggingFace commit; see
MODEL_CARD.md). --smoke allows a null revision, but prints a loud warning,
since a smoke run is a bounded, tiny-step loop check, never a real
fine-tune.

Every run writes a content-addressed manifest.json to its run dir before
training starts (dataset digest, config hash, code git rev, base model,
library versions), and fills in `outputs.checkpoints` after training
completes.

Tailable progress: every run creates a ProgressWriter (see progress.py)
that appends human-readable lines to <run_dir>/train.log and rewrites
<run_dir>/progress.json on every logging step, so a run launched with
nohup can be followed with `tail -f <run_dir>/train.log` and has a live
ETA. The run_id/run_dir/log paths are printed (and logged) in the first
lines of output.

VRAM preflight: before any heavy import, main() checks free VRAM against
config.resources.min_free_vram_gib and REFUSES to start training (raising
TrainingRefusalError) when there is not enough headroom -- pass
--allow-low-vram to skip that refusal when you know what else is using the
GPU. See resources.py's module docstring for the incident this class of
check exists to prevent.

Heavy imports (torch/transformers/peft/trl/datasets/bitsandbytes) are
deferred into main() so importing this module stays cheap and does not
require a GPU.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any

from stoic_training import manifest as manifest_mod
from stoic_training import progress
from stoic_training import resources
from stoic_training.config import QloraConfig, ensure_hf_home, load_config

# src/stoic_training/train.py -> stoic_training -> src -> win_cuda -> training -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]


class TrainingRefusalError(RuntimeError):
    """Raised when a non-smoke run is attempted without a pinned base-model revision,
    or when the VRAM preflight check refuses to start training."""


def configure_allocator(env: MutableMapping[str, str] | None = None) -> str:
    """Set PYTORCH_CUDA_ALLOC_CONF to "expandable_segments:True" if unset.

    Set-if-unset: a value the user already exported is respected as-is.
    Must be called before torch is imported -- torch's CUDA allocator reads
    this env var once, at first CUDA use. Defaults to os.environ; tests pass
    a plain dict so this is exercisable without touching the real process
    environment.
    """
    target: MutableMapping[str, str] = os.environ if env is None else env
    target.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    return target["PYTORCH_CUDA_ALLOC_CONF"]


def preflight_vram(
    config: QloraConfig,
    *,
    allow_low_vram: bool,
    probe: Callable[[], tuple[int, int] | None] = resources.free_vram,
) -> resources.VramCheck:
    """Refuse to start training when free VRAM is below config's threshold.

    Raises TrainingRefusalError(check.reason) when the check fails and
    allow_low_vram is False. `probe` defaults to resources.free_vram (which
    imports torch lazily); tests inject a stub so this is exercisable with
    no GPU and no torch import.
    """
    probed = probe()
    free_bytes, total_bytes = probed if probed is not None else (None, None)
    check = resources.check_train_vram(
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        required_bytes=config.resources.min_free_vram_bytes,
    )
    if not check.ok and not allow_low_vram:
        raise TrainingRefusalError(check.reason)
    return check


def resolve_total_steps(*, state_max_steps: int, fallback_total_steps: int) -> int:
    """state.max_steps from the live TrainerState is authoritative when > 0.

    The tokenized/packed dataset length the trainer resolves internally can
    differ from the raw example count used to precompute fallback_total_steps,
    so prefer the trainer's own number whenever it has settled on one.
    """
    if state_max_steps > 0:
        return state_max_steps
    return fallback_total_steps


def handle_log_event(
    writer: progress.ProgressWriter,
    *,
    step: int,
    state_max_steps: int,
    fallback_total_steps: int,
    logs: Mapping[str, Any] | None,
) -> progress.ProgressSnapshot | None:
    """Turn one Trainer on_log() callback into a progress.json/train.log update.

    Returns None (no-op) for step <= 0 (e.g. a pre-training log event).
    Eval-only log dicts carry no "loss" key; those still update progress
    with loss=None rather than being skipped, so the step/ETA stay current.
    """
    if step <= 0:
        return None
    loss: float | None = None
    if logs is not None and "loss" in logs:
        try:
            loss = float(logs["loss"])
        except (TypeError, ValueError):
            loss = None
    total_steps = resolve_total_steps(
        state_max_steps=state_max_steps, fallback_total_steps=fallback_total_steps
    )
    return writer.update(step=step, total_steps=total_steps, loss=loss)


def make_progress_callback(writer: progress.ProgressWriter, *, fallback_total_steps: int):
    """Build a transformers TrainerCallback that drives `writer` from trainer events.

    Imports TrainerCallback lazily so this function (and this module) stays
    importable without transformers installed.
    """
    from transformers import TrainerCallback

    class _ProgressCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):  # noqa: ANN001
            handle_log_event(
                writer,
                step=state.global_step,
                state_max_steps=state.max_steps,
                fallback_total_steps=fallback_total_steps,
                logs=logs,
            )
            return control

        def on_evaluate(self, args, state, control, metrics=None, **kwargs):  # noqa: ANN001
            metrics = metrics or {}
            eval_loss = metrics.get("eval_loss")
            if eval_loss is not None:
                writer.log(f"eval at step {state.global_step}: eval_loss={eval_loss:.4f}")
            else:
                writer.log(f"eval at step {state.global_step}")
            return control

        def on_save(self, args, state, control, **kwargs):  # noqa: ANN001
            writer.log(f"checkpoint saved at step {state.global_step}")
            return control

        def on_train_end(self, args, state, control, **kwargs):  # noqa: ANN001
            writer.log("training loop finished")
            return control

    return _ProgressCallback()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QLoRA SFT training for the research-assistant SLM.")
    parser.add_argument("--config", type=Path, default=Path("config/qlora.yaml"))
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Bounded, tiny-step smoke run (proves the loop works; never a real fine-tune).",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from the run's latest checkpoint.")
    parser.add_argument(
        "--allow-low-vram",
        action="store_true",
        help="Skip the VRAM preflight refusal (only when you know what else is using the GPU).",
    )
    return parser.parse_args(argv)


def require_pinned_revision(config: QloraConfig, *, smoke: bool) -> None:
    if config.model.revision is not None:
        return
    if not smoke:
        raise TrainingRefusalError(
            "model.revision is null in qlora.yaml. Refusing to run a non-smoke training "
            "run against an unpinned base model. Pin the exact HuggingFace revision "
            "(record it in MODEL_CARD.md) before launching a real fine-tune, or pass "
            "--smoke for a bounded loop check."
        )
    print(
        "WARNING: model.revision is null -- this smoke run is NOT pinned to an exact "
        "base-model commit. Never use an unpinned revision for a real fine-tune.",
        flush=True,
    )


def build_manifest(config: QloraConfig, *, smoke: bool) -> dict:
    dataset_ref = manifest_mod.load_dataset_ref(config.paths.dataset_dir)
    code_rev = manifest_mod.git_rev(REPO_ROOT)
    resolved = config.resolved_dict(smoke=smoke)
    base_model = {"repo_id": config.model.repo_id, "revision": config.model.revision}
    return manifest_mod.build_run_manifest(
        dataset_ref=dataset_ref,
        config_resolved=resolved,
        code_rev=code_rev,
        base_model=base_model,
    )


def main(argv: Sequence[str] | None = None) -> int:
    # Must run before the deferred torch import: torch's CUDA allocator reads
    # PYTORCH_CUDA_ALLOC_CONF once, at first CUDA use.
    configure_allocator()
    # Must also run before the deferred transformers import, which reads
    # HF_HOME at import time. Without this the migrated base-model cache
    # under the train home is ignored and the 16 GB base is re-downloaded.
    hf_home = ensure_hf_home()

    args = parse_args(argv)
    config = load_config(args.config)
    require_pinned_revision(config, smoke=args.smoke)

    run_manifest = build_manifest(config, smoke=args.smoke)
    run_dir = config.paths.run_dir / run_manifest["run_id"]
    manifest_mod.write_manifest(run_manifest, run_dir)

    writer = progress.ProgressWriter(
        run_dir, run_manifest["run_id"], log_name="train.log", phase="startup"
    )

    training = config.training
    max_seq_len = config.smoke.max_seq_len if args.smoke else training.max_seq_len
    max_steps = config.smoke.max_steps if args.smoke else -1
    mode = "smoke" if args.smoke else "real"

    startup_lines = [
        f"run_id={run_manifest['run_id']}",
        f"run_dir={run_dir}",
        f"train.log={writer.log_path}",
        f"progress.json={writer.progress_path}",
        f"mode={mode} max_seq_len={max_seq_len} max_steps={max_steps}",
        f"hf_home={hf_home}",
        f"dataset_dir={config.paths.dataset_dir}",
        "tail -f " + str(writer.log_path) + " to follow this run",
    ]
    for line in startup_lines:
        print(line, flush=True)
        writer.log(line)

    # VRAM preflight, before any heavy import: see resources.py's module
    # docstring for the hang this class of check exists to prevent.
    try:
        check = preflight_vram(config, allow_low_vram=args.allow_low_vram)
    except TrainingRefusalError as exc:
        writer.log(f"VRAM preflight REFUSED: {exc}")
        raise
    print(check.reason, flush=True)
    writer.log(check.reason)

    import torch
    from datasets import load_dataset
    from peft import LoraConfig as PeftLoraConfig
    from peft import get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    from trl import SFTConfig, SFTTrainer

    set_seed(training.seed)

    dataset_files = {
        "train": str(config.paths.dataset_dir / "train.jsonl"),
        "validation": str(config.paths.dataset_dir / "eval.jsonl"),
    }
    dataset = load_dataset("json", data_files=dataset_files)

    num_examples = len(dataset["train"])
    fallback_total_steps = progress.compute_total_steps(
        num_examples=num_examples,
        per_device_train_batch_size=training.per_device_train_batch_size,
        gradient_accumulation_steps=training.gradient_accumulation_steps,
        num_train_epochs=training.num_train_epochs,
        max_steps=max_steps,
    )
    step_line = f"train examples={num_examples} projected_total_steps={fallback_total_steps}"
    print(step_line, flush=True)
    writer.log(step_line)
    # Publish the projected denominator before the (slow) base-model load, so
    # `status` shows a meaningful total during the minutes before step 1.
    writer.update(step=0, total_steps=fallback_total_steps, phase="load", log=False)

    tokenizer = AutoTokenizer.from_pretrained(config.model.repo_id, revision=config.model.revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = config.quantization
    compute_dtype = torch.bfloat16 if quant.bnb_4bit_compute_dtype == "bfloat16" else torch.float16
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=quant.load_in_4bit,
        bnb_4bit_quant_type=quant.bnb_4bit_quant_type,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=quant.bnb_4bit_use_double_quant,
    )
    model = AutoModelForCausalLM.from_pretrained(
        config.model.repo_id,
        revision=config.model.revision,
        quantization_config=bnb_config,
        dtype=compute_dtype,
        attn_implementation=training.attn_implementation,
    )
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=training.gradient_checkpointing
    )

    lora = config.lora
    peft_config = PeftLoraConfig(
        r=lora.r,
        lora_alpha=lora.alpha,
        lora_dropout=lora.dropout,
        target_modules=list(lora.target_modules),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)

    checkpoint_dir = run_dir / "checkpoint"
    sft_args = SFTConfig(
        output_dir=str(checkpoint_dir),
        max_length=max_seq_len,
        per_device_train_batch_size=training.per_device_train_batch_size,
        per_device_eval_batch_size=training.per_device_eval_batch_size,
        gradient_accumulation_steps=training.gradient_accumulation_steps,
        gradient_checkpointing=training.gradient_checkpointing,
        optim=training.optim,
        learning_rate=training.learning_rate,
        lr_scheduler_type=training.lr_scheduler_type,
        warmup_ratio=training.warmup_ratio,
        num_train_epochs=training.num_train_epochs,
        max_steps=max_steps,
        seed=training.seed,
        logging_steps=training.logging_steps,
        save_steps=training.save_steps,
        save_total_limit=training.save_total_limit,
        eval_steps=training.eval_steps,
        eval_strategy="steps",
        bf16=training.bf16,
        dataloader_pin_memory=config.resources.dataloader_pin_memory,
        dataloader_num_workers=config.resources.dataloader_num_workers,
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        processing_class=tokenizer,
        callbacks=[make_progress_callback(writer, fallback_total_steps=fallback_total_steps)],
    )

    writer.set_phase("train")
    trainer.train(resume_from_checkpoint=True if args.resume else None)

    writer.set_phase("save")
    writer.log("saving final adapter")
    final_checkpoint_dir = checkpoint_dir / "final"
    trainer.save_model(str(final_checkpoint_dir))
    tokenizer.save_pretrained(str(final_checkpoint_dir))

    writer.log("hashing checkpoint")
    checkpoints = [
        {"path": str(final_checkpoint_dir), "sha256": manifest_mod.sha256_dir(final_checkpoint_dir)}
    ]
    manifest_mod.update_manifest_outputs(run_dir, checkpoints)
    writer.log("manifest finalized")

    writer.finish("training complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
