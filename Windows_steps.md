# Windows Steps — SLM retrain (Stage C)

WSL, GPU box, RTX 5070 Ti / 16 GB. Plan: `docs/notes/2026-07-26-slm-retrain-plan.md`.

This box runs **only** the training chain. WP-V §3.2 (the VLM extraction) runs on the Mac — the 30B
VL extractor needs ~17 GB and does not fit this card. Do not swap in a smaller VL model to work
around that; ask first.

## 1. Preconditions — check these before anything else

**Stage A must have landed on the Mac and been pushed.** `.artifacts/` is gitignored, so the
extraction's own records never travel. The one artifact that does is `edu/derived/dataset.jsonl`,
rebuilt from them.

```bash
git pull --ff-only origin main
git log --oneline -1 -- edu/derived/dataset.jsonl   # must NOT be 9cbfb26
wc -l < edu/derived/dataset.jsonl                   # baseline is 2233; expect ~10k
```

- `9cbfb26` (Initial commit) means **Stage A has not landed**. Stop — there is nothing new to train
  on. The old 2,233 rows are the drift-sampled keyframe labels this work exists to replace, and one
  of them is a known hallucinated caption.
- Also confirm the §3.3 audit result is recorded in
  `docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`. If OCR failed its gate, the fix is
  the extractor, not a text retrain on bad text.

**Nothing may already be on the GPU.** Two 8B models on one card is OOM and hours lost.

```bash
pgrep -af "venv/bin/python3 -m stoic_training"   # bare "stoic_training" matches your own shell
scripts/launch_bg.sh --list
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

## 2. Build the chain

Write `training/win_cuda/scripts/chain_retrain.sh`, following the style of
`training/win_cuda/scripts/health.sh`. Resumable, one stage at a time, rc checked between stages:

1. **Eval delta** on the rebuilt corpus against the existing fine-tune `adb3c96ab6020c23` and the
   instructed base — `cited_qa` and `rule_candidate`. Counts, not verdicts.
2. **QLoRA retrain**. `training/win_cuda/config/qlora.yaml`, same LoRA geometry as
   `adb3c96ab6020c23` (r=16 / α=32 / dropout 0.05, all seven attn+MLP projections) unless there is a
   stated reason to change it. **Non-thinking targets** — thinking stays OFF at inference or the
   eval will not reproduce.
3. **Eval the new run**, then compare all three. Disaggregate by task; ADR-0021 applies to every
   number.

Per the user's call: **measure, then train regardless.** The delta is the record of what changed,
not a gate — nothing waits overnight.

### Venv traps — non-negotiable

- `export UV_PROJECT_ENVIRONMENT=<repo>/.artifacts/training/venv` before any `uv run`.
- `uv run` must have cwd `training/win_cuda`. The root `pyproject.toml` is 3.14 and destroys the
  3.12 CUDA venv.
- `uv run` must never run while a GPU job is live — it resyncs the venv. Prefer
  `.artifacts/training/venv/bin/python3 -m stoic_training.<cmd>` directly.
- `uvx ruff check --fix`, never a bare `ruff check`. Line length 100.

## 3. Launch and hand off

```bash
scripts/launch_bg.sh slm-retrain -- training/win_cuda/scripts/chain_retrain.sh
```

Detaches, holds the machine awake for exactly the job's lifetime (Windows-side
`SetThreadExecutionState` keeper, no admin, released when the job exits), refuses to launch over a
job that is already alive, and prints a pid.

**Report that pid.** It is all a later session needs:

```bash
scripts/job_status.sh <pid>
```

Returns **0** running or clean · **1** crashed · **2** stalled. Stalled — alive but nothing written
for 25 min — is the one that matters; a wedged CUDA job stays "alive" indefinitely. Diagnose a
stall, never launch a second copy over it.

## 4. What would make this the wrong call

- The §3.3 audit shows OCR is unreliable → fix the extractor, not the text model.
- The rebuilt dataset is barely different from the 2,233-row baseline → there is nothing new to
  learn. Say so rather than spending GPU hours.
