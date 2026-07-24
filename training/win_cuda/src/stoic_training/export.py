"""Merge a QLoRA LoRA adapter into its base model, then (optionally) GGUF-convert.

Purpose guardrail: this exports an OFFLINE research-assistant model that
proposes cited rule candidates for human review; its output never touches
any live trading path.

Two steps:
  1. Merge (always runs): peft `merge_and_unload()` folds the LoRA adapter
     into the base model and saves safetensors to
     $STOIC_TRAIN_HOME/exports/<run_id>/merged/.
  2. GGUF convert (only if --llama-cpp-dir is given): this package does
     NOT vendor llama.cpp. It locates and invokes llama.cpp's
     `convert_hf_to_gguf.py` as a subprocess against the merged directory.
     Without --llama-cpp-dir, export stops after safetensors with a clear
     message. q4_K_M quantization for LM Studio is a SEPARATE step done
     with llama.cpp's own `llama-quantize` binary; this script only prints
     the follow-up command, it does not run llama-quantize itself.

Export artifacts (paths + sha256s) are recorded into the run's
manifest.json outputs.

Memory preflight: a merge once loaded the full bf16 8B with
max_memory={0:"13GiB","cpu":"10GiB"} hardcoded; combined with the Windows
desktop's own VRAM use, that hung the whole box (hard reboot required; see
resources.py's module docstring for the full incident). main() now computes
a host-specific MergeBudget (resources.plan_merge_budget via
plan_export_budget below) from config.resources.* and REFUSES -- rather
than thrashing the machine -- when the budget does not fit. Nothing in this
module is exercised end-to-end by the test suite; a real merge is exactly
what caused the incident, so it is covered by unit tests against pure
budgeting functions only.

Heavy imports (torch/transformers/peft) are deferred into functions so
importing this module stays cheap and does not require a GPU.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from stoic_training import manifest as manifest_mod
from stoic_training import progress
from stoic_training import resources
from stoic_training.config import default_train_home, ensure_hf_home, load_config
from stoic_training.resources import MemoryStatus, MergeBudget, PreflightError

# Mirrors resources.plan_merge_budget's own keyword defaults. Used only when
# --config does not exist and no explicit CLI cap override is given -- see
# main()'s config-sourcing note.
_FALLBACK_GPU_CAP_GIB = 12.0
_FALLBACK_VRAM_HEADROOM_GIB = 2.0
_FALLBACK_CPU_RESERVE_GIB = 4.0


class ExportError(RuntimeError):
    """Raised when a merge or GGUF conversion step cannot complete."""


def plan_export_budget(
    *,
    gpu_cap_bytes: int,
    vram_headroom_bytes: int,
    cpu_reserve_bytes: int,
    probe: Callable[[], tuple[int, int] | None] = resources.free_vram,
    meminfo: Callable[[], MemoryStatus] = resources.read_meminfo,
    required_bytes: int = resources.MERGE_MODEL_BYTES_QWEN3_8B,
) -> MergeBudget:
    """Build a MergeBudget from injectable VRAM/RAM probes.

    `probe` and `meminfo` default to the real hardware probes
    (resources.free_vram, resources.read_meminfo) but tests inject stubs so
    both the fitting and refusing paths are exercisable with zero hardware.
    """
    probed = probe()
    free_vram_bytes = probed[0] if probed is not None else None
    memory = meminfo()
    return resources.plan_merge_budget(
        free_vram_bytes=free_vram_bytes,
        memory=memory,
        required_bytes=required_bytes,
        gpu_cap_bytes=gpu_cap_bytes,
        vram_headroom_bytes=vram_headroom_bytes,
        cpu_reserve_bytes=cpu_reserve_bytes,
    )


def merge_lora(
    checkpoint: str | Path,
    *,
    base_repo_id: str,
    base_revision: str | None,
    output_dir: str | Path,
    max_memory: Mapping[str | int, str],
    writer: progress.ProgressWriter | None = None,
) -> Path:
    """Merge a LoRA adapter checkpoint into its base model, save safetensors.

    `max_memory` is a caller-computed accelerate cap (see plan_export_budget
    / MergeBudget.max_memory) -- it replaces what used to be a hardcoded
    {0: "13GiB", "cpu": "10GiB"} that hung the box once. The caps, not the
    offload_folder below, are what must prevent accelerate from ever
    spilling a layer to disk: peft cannot merge disk-offloaded modules.
    """
    import tempfile

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    checkpoint = Path(checkpoint)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def _log(message: str) -> None:
        if writer is not None:
            writer.log(message)

    with tempfile.TemporaryDirectory(prefix="stoic-export-offload-") as offload_dir:
        _log("loading base model shards")
        base_model = AutoModelForCausalLM.from_pretrained(
            base_repo_id,
            revision=base_revision,
            dtype=torch.bfloat16,
            device_map="auto",
            max_memory=dict(max_memory),
            offload_folder=offload_dir,
        )
        _log("loading LoRA adapter")
        model = PeftModel.from_pretrained(
            base_model, checkpoint, offload_folder=offload_dir
        )
        _log("merging adapter into base weights")
        merged = model.merge_and_unload()
        _log("saving merged safetensors")
        merged.save_pretrained(output_dir, safe_serialization=True)

    _log("saving tokenizer")
    tokenizer = AutoTokenizer.from_pretrained(base_repo_id, revision=base_revision)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def convert_to_gguf(
    merged_dir: str | Path,
    *,
    llama_cpp_dir: str | Path,
    output_path: str | Path,
    outtype: str = "auto",
) -> Path:
    """Invoke llama.cpp's convert_hf_to_gguf.py as a subprocess (not vendored here)."""
    llama_cpp_dir = Path(llama_cpp_dir)
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.is_file():
        raise ExportError(f"convert_hf_to_gguf.py not found under {llama_cpp_dir}")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(convert_script),
            str(merged_dir),
            "--outfile",
            str(output_path),
            "--outtype",
            outtype,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ExportError(f"GGUF conversion failed: {result.stderr}")
    return output_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge LoRA -> safetensors, optionally -> GGUF (llama.cpp convert step)."
    )
    parser.add_argument("--checkpoint", type=Path, required=True, help="LoRA adapter checkpoint dir")
    parser.add_argument("--base-repo-id", required=True)
    parser.add_argument("--base-revision", default=None)
    parser.add_argument("--run-id", required=True, help="Run id that keys the export/manifest paths")
    parser.add_argument("--train-home", type=Path, default=None, help="Defaults to $STOIC_TRAIN_HOME (<repo>/.artifacts/training)")
    parser.add_argument("--run-dir", type=Path, default=None, help="Run dir holding manifest.json (default: <train-home>/runs/<run-id>)")
    parser.add_argument("--llama-cpp-dir", type=Path, default=None, help="Local llama.cpp checkout; omit to stop after safetensors")
    parser.add_argument("--gguf-name", default="model.gguf")
    parser.add_argument(
        "--outtype",
        default="auto",
        help="convert_hf_to_gguf.py output type (e.g. auto, f16, q8_0)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/qlora.yaml"),
        help="qlora.yaml to source the resources.* cap knobs from; falls back to "
        "resources.py defaults (logged) if this file does not exist",
    )
    parser.add_argument(
        "--gpu-cap-gib", type=float, default=None, help="Override config.resources.export_gpu_cap_gib"
    )
    parser.add_argument(
        "--vram-headroom-gib",
        type=float,
        default=None,
        help="Override config.resources.export_vram_headroom_gib",
    )
    parser.add_argument(
        "--cpu-reserve-gib",
        type=float,
        default=None,
        help="Override config.resources.export_cpu_reserve_gib",
    )
    parser.add_argument(
        "--allow-unfit-budget",
        action="store_true",
        help="Downgrade a merge-budget refusal to a loud logged warning instead of "
        "raising -- this is what hung the box once, use only if you are certain.",
    )
    return parser.parse_args(argv)


def _resolve_cap_gib(
    args: argparse.Namespace, *, writer: progress.ProgressWriter
) -> tuple[float, float, float]:
    """Resolve (gpu_cap_gib, vram_headroom_gib, cpu_reserve_gib) from CLI overrides,
    falling back to --config's resources.* section, falling back in turn to
    resources.py's own defaults (logged) when --config does not exist."""
    gpu_cap_gib = args.gpu_cap_gib
    vram_headroom_gib = args.vram_headroom_gib
    cpu_reserve_gib = args.cpu_reserve_gib
    if gpu_cap_gib is not None and vram_headroom_gib is not None and cpu_reserve_gib is not None:
        return gpu_cap_gib, vram_headroom_gib, cpu_reserve_gib

    if args.config.is_file():
        resolved = load_config(args.config).resources
        if gpu_cap_gib is None:
            gpu_cap_gib = resolved.export_gpu_cap_gib
        if vram_headroom_gib is None:
            vram_headroom_gib = resolved.export_vram_headroom_gib
        if cpu_reserve_gib is None:
            cpu_reserve_gib = resolved.export_cpu_reserve_gib
    else:
        note = (
            f"no config file at {args.config}; using resources.py hardcoded defaults "
            "for any unset cap knob"
        )
        print(note, flush=True)
        writer.log(note)
        if gpu_cap_gib is None:
            gpu_cap_gib = _FALLBACK_GPU_CAP_GIB
        if vram_headroom_gib is None:
            vram_headroom_gib = _FALLBACK_VRAM_HEADROOM_GIB
        if cpu_reserve_gib is None:
            cpu_reserve_gib = _FALLBACK_CPU_RESERVE_GIB

    return gpu_cap_gib, vram_headroom_gib, cpu_reserve_gib


def main(argv: Sequence[str] | None = None) -> int:
    # Before the deferred transformers import (it reads HF_HOME at import
    # time): the base model reloaded for the merge must come from the
    # train-home cache, not a fresh 16 GB download.
    ensure_hf_home()
    args = parse_args(argv)
    train_home = args.train_home or default_train_home()
    export_dir = train_home / "exports" / args.run_id
    merged_dir = export_dir / "merged"
    run_dir = args.run_dir or (train_home / "runs" / args.run_id)

    writer = progress.ProgressWriter(run_dir, args.run_id, log_name="export.log", phase="preflight")
    startup_line = (
        f"run_dir={run_dir} export.log={writer.log_path} progress.json={writer.progress_path}"
    )
    print(startup_line, flush=True)
    writer.log(startup_line)

    gpu_cap_gib, vram_headroom_gib, cpu_reserve_gib = _resolve_cap_gib(args, writer=writer)
    budget = plan_export_budget(
        gpu_cap_bytes=int(gpu_cap_gib * 1024**3),
        vram_headroom_bytes=int(vram_headroom_gib * 1024**3),
        cpu_reserve_bytes=int(cpu_reserve_gib * 1024**3),
    )
    print(budget.summary(), flush=True)
    writer.log(budget.summary())

    try:
        resources.require_merge_budget(budget)
    except PreflightError as exc:
        if args.allow_unfit_budget:
            warning = (
                f"WARNING: merge budget does not fit but --allow-unfit-budget was given; "
                f"proceeding anyway: {exc}"
            )
            print(warning, flush=True)
            writer.log(warning)
        else:
            writer.log(f"merge budget REFUSED: {exc}")
            raise

    writer.set_phase("merge")
    merge_lora(
        args.checkpoint,
        base_repo_id=args.base_repo_id,
        base_revision=args.base_revision,
        output_dir=merged_dir,
        max_memory=budget.max_memory,
        writer=writer,
    )
    print(f"merged safetensors written to {merged_dir}")
    writer.log(f"merged safetensors written to {merged_dir}")

    writer.set_phase("hash")
    export_outputs = [{"path": str(merged_dir), "sha256": manifest_mod.sha256_dir(merged_dir)}]
    writer.log("hashed merged safetensors")

    if args.llama_cpp_dir is None:
        note = (
            "No --llama-cpp-dir given; stopping after safetensors. To produce a GGUF for "
            "LM Studio, re-run with --llama-cpp-dir pointing at a local llama.cpp checkout."
        )
        print(note)
        writer.log(note)
    else:
        writer.set_phase("gguf")
        gguf_path = export_dir / "gguf" / args.gguf_name
        convert_to_gguf(
            merged_dir,
            llama_cpp_dir=args.llama_cpp_dir,
            output_path=gguf_path,
            outtype=args.outtype,
        )
        print(f"GGUF written to {gguf_path}")
        writer.log(f"GGUF written to {gguf_path}")
        quantized_path = gguf_path.with_name(f"{gguf_path.stem}.q4_K_M.gguf")
        print(
            "Quantize for LM Studio with llama.cpp's llama-quantize binary (not run by this "
            f"script), e.g.: llama-quantize {gguf_path} {quantized_path} Q4_K_M"
        )
        export_outputs.append({"path": str(gguf_path), "sha256": manifest_mod.sha256_file(gguf_path)})

    if (run_dir / "manifest.json").is_file():
        existing = manifest_mod.read_manifest(run_dir)
        checkpoints = existing.get("outputs", {}).get("checkpoints", [])
        manifest_mod.update_manifest_outputs(
            run_dir, [*checkpoints, {"export": export_outputs}]
        )
        writer.log("manifest updated with export outputs")
    else:
        note = f"no manifest.json found at {run_dir}; export outputs were not recorded"
        print(note)
        writer.log(note)

    writer.finish("export complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
