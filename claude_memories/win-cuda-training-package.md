---
name: win-cuda-training-package
description: DONE — the Windows/WSL QLoRA training package, its environment traps, and the residual audit warts (kept for the traps, not as an active task)
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f026b50-4df5-449e-948a-302bd74a696e
  modified: 2026-07-26T02:59:09.391Z
---

**Status: COMPLETE, not an active task.** Package committed and pushed 2026-07-24
(`c3b1204` + `d0d1c06` on main, rebased atop the Mac's SP4 ledger + SP5 dashboard); Opus audit
passed all 7 `Windows_setup.md` checklist items. The real fine-tune subsequently ran to completion
— run `adb3c96ab6020c23`, plus three baselines under `.artifacts/training/runs/`. Results and the
verdict on what the fine-tune actually bought live in [[eval-comparison-wp-progress]].

Stack: Qwen3-8B rev b968826d, torch 2.11.0+cu128, bnb 0.49.2. Plan doc:
`docs/superpowers/specs/2026-07-24-win-cuda-training-package-plan.md`.

## The 16 GB ceiling — what this box cannot do

**RTX 5070 Ti, 16 GB VRAM.** That rules out running the WP-V §3.2 extractor here:
`qwen3-vl-30b-a3b-instruct-mlx` needs ~17 GB even at 4-bit. The visual pass therefore runs on the
Mac and only the training chain runs here — see [[slm-model-artifacts]] and
`docs/notes/2026-07-26-slm-retrain-plan.md`. Do not "solve" this by swapping in a smaller VL model
without asking; the extraction quality is the whole point of that work package.

## The environment traps — this is why the memory is kept

- Per [[artifact-locality]] everything lives under `<repo>/.artifacts/training/` (venv, hf cache,
  datasets, runs, logs); `~/stoic-training` was migrated and deleted.
- Always `export UV_PROJECT_ENVIRONMENT=<repo>/.artifacts/training/venv` before `uv run` in
  `training/win_cuda`, or uv silently builds a fresh CUDA venv. `uv run` must also have
  cwd = `training/win_cuda` (the root pyproject is 3.14 and destroys the 3.12 CUDA venv), and must
  never run while a GPU job is live. Safer: call
  `.artifacts/training/venv/bin/python3 -m stoic_training.<cmd>` directly.
- `/mnt/c/Users/rajee/.wslconfig` (24 GB RAM / 32 GB swap) is **now active** — verified
  2026-07-26, `free -g` reports 23 GB mem + 32 GB swap. It was written 2026-07-24 but needed a
  `wsl --shutdown`, which has since happened. A bf16 8B merge once hung the machine without it;
  preflights now refuse rather than hang.

## Residual audit warts (never closed)

- Export manifest schema wart (F3).
- The citation check is corpus-wide, not split-scoped.

Follow the VISION.md agent process; never modify VISION.md or `edu/`; the model is offline
research only.
