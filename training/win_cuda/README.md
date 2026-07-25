# win_cuda — Windows/WSL QLoRA training package

Reproducible fine-tuning environment for the offline research-assistant SLM.
The model this package trains **proposes cited rule candidates for human
review only** — its output never touches the live signal path (VISION.md).

Runs on WSL2 Ubuntu with an NVIDIA Blackwell GPU (RTX 5070 Ti, 16 GB,
sm_120). CUDA pins live entirely in this subproject's `pyproject.toml` +
`uv.lock`; the repo's portable dev environment must never gain CUDA deps.

## Layout rule: everything relative to the repo

All run artifacts live under the repo working directory in the git-ignored
`.artifacts/` folder (user directive 2026-07-24 — artifacts stay next to
the work, never in `~`, system temp, or another drive; the WSL VHD sits on
the nearly-full C: while the repo drive has room to spare). Default
`STOIC_TRAIN_HOME` is `<repo>/.artifacts/training/`:

```
<repo>/.artifacts/training/
  venv/          # uv project environment (UV_PROJECT_ENVIRONMENT)
  hf/            # HuggingFace cache (HF_HOME, auto-set by config.py)
  datasets/      # built SFT datasets (train/eval jsonl + digest manifest)
  runs/          # checkpoints + run manifests + train.log/progress.json
  exports/       # merged safetensors + GGUF (~25 GB per export)
  logs/          # bootstrap logs from detached launches
  llama.cpp/     # shallow clone, used only for GGUF conversion
```

Accepted trade-off: drvfs I/O on `/mnt/f` is slower than ext4 for
many-small-file workloads (venv, HF cache) and checkpoint saves. Trainer
checkpoints land under `$STOIC_TRAIN_HOME/runs/<run_id>/checkpoint/` with
the final adapter in `checkpoint/final/` — that is the dir to pass to
`export.py --checkpoint`.

## Environment variables

None are required: `STOIC_TRAIN_HOME` defaults to
`<repo>/.artifacts/training` and `config.py` auto-points `HF_HOME` at
`$STOIC_TRAIN_HOME/hf` unless you already set it. To keep the venv in the
same tree, export (per-shell or in `~/.bashrc`):

```bash
export UV_PROJECT_ENVIRONMENT="/mnt/f/dev/stoic_derived/.artifacts/training/venv"
```

Only set `STOIC_TRAIN_HOME` explicitly to relocate the whole artifact tree.
If your `~/.bashrc` still exports the old `~/stoic-training` values from an
earlier revision of this README, remove them.

## Setup

```bash
cd training/win_cuda
uv sync --all-groups     # installs torch cu128 + bitsandbytes into $UV_PROJECT_ENVIRONMENT
uv run pytest            # GPU smoke tests run on this box; skip cleanly elsewhere
```

The pin set is Blackwell-verified: torch built for cu128 with sm_120 kernels,
bitsandbytes with 4-bit (nf4) support on sm_120. Do not bump these pins
without re-running `tests/test_gpu_smoke.py` on the GPU box.

## Commands

```bash
uv run python -m stoic_training.build_dataset   # dataset.jsonl -> SFT pairs + digest (frozen split in splits/)
uv run python -m stoic_training.train           # QLoRA SFT, seeded, resumable
uv run python -m stoic_training.evaluate        # citation fidelity + held-out + conflict surfacing
uv run python -m stoic_training.infer           # offline inference against a local checkpoint
uv run python -m stoic_training.export          # merge LoRA -> safetensors -> GGUF (LM Studio)
```

Every run writes a content-addressed manifest (dataset digest, code rev,
config hash, base-model revision, outputs) under `$STOIC_TRAIN_HOME/runs/`.

## Long runs: launch, tail, status

Training, export, and generation-mode evaluation can all run for hours.
Launch them detached so a dropped terminal (SSH drop, closed window) never
kills the run, tail their output live, and poll status without waiting on
the run to finish.

### Detached launch

The run dir (and therefore its `train.log`) is not known until train.py
actually starts, so the detached-launch pattern captures stdout/stderr to a
timestamped **bootstrap log** first:

```bash
cd /mnt/f/dev/stoic_derived/training/win_cuda
mkdir -p ../../.artifacts/training/logs
nohup uv run python -m stoic_training.train --config config/qlora.yaml \
  >> ../../.artifacts/training/logs/train-$(date +%Y%m%dT%H%M%S).log 2>&1 &
```

`setsid uv run python -m stoic_training.train ...` is an equivalent
alternative to `nohup ... &` if you'd rather fully detach from the
controlling terminal's process group. Either way, train.py's first lines of
output print (and log) the run_id, run_dir, and the absolute paths of
`train.log` and `progress.json` -- read the bootstrap log once at startup to
learn exactly what to tail next.

### Tailing

```bash
# raw stdout/stderr from the detached process (crashes, tracebacks, warnings)
tail -f ../../.artifacts/training/logs/<bootstrap-log-name>.log

# structured, human-readable progress lines with a live ETA
tail -f <run_dir>/train.log
```

### Status, without tailing

```bash
uv run python -m stoic_training.status                       # newest run, auto-selected
uv run python -m stoic_training.status --run-id <run_id>
uv run python -m stoic_training.status --run-dir <run_dir>
```

Prints the run dir, a formatted snapshot of `progress.json` (phase, step,
loss, rate, ETA, staleness), and a `tail -f` reminder. Exits 1 with a clear
message (no traceback) if nothing has run yet.

### Watcher discipline (don't self-match, don't wait forever)

Two hard rules for anything (human, agent, or script) that watches a
detached run:

1. **The pgrep self-match trap.** `pgrep -f stoic_training.train` matches
   the watcher's *own shell* whenever the pattern appears in its command
   line, so a `while pgrep ...; do sleep ...; done` loop never exits (this
   cost a real run 2.5 idle hours). Always break self-matching with a
   character class: `pgrep -f "[s]toic_training.train"`.
2. **Liveness is not progress.** Pair every process check with stall
   detection (log mtime / progress.json age) and a crash scan (traceback in
   the newest bootstrap log). "No news" must resolve to RUNNING, STALLED,
   CRASHED, or DONE — never to "keep waiting".

Both rules are packaged in `scripts/health.sh`:

```bash
scripts/health.sh                  # one-shot: status of train/evaluate/export
scripts/health.sh export           # one-shot, single phase
scripts/health.sh --wait export    # block until exit/crash/stall
                                   # exit 0=clean exit, 1=crash, 2=stalled
```

Use `--wait` as the canonical wake-on-event watcher for detached launches
(including from agents): it returns the moment there is something to act
on, with the reason in its last output lines.

### Same pattern for export and evaluate

```bash
nohup uv run python -m stoic_training.export --checkpoint <checkpoint> \
    --base-repo-id Qwen/Qwen3-8B --run-id <run_id> \
  >> ../../.artifacts/training/logs/export-$(date +%Y%m%dT%H%M%S).log 2>&1 &
tail -f <run_dir>/export.log

nohup uv run python -m stoic_training.evaluate --run-dir <run_dir> \
    --checkpoint <checkpoint> --eval-jsonl <path/to/eval.jsonl> \
  >> ../../.artifacts/training/logs/evaluate-$(date +%Y%m%dT%H%M%S).log 2>&1 &
tail -f <run_dir>/evaluate.log
```

`evaluate.py`'s progress log/`progress.json` are opt-in via `--run-dir`; the
default scoring-only invocation (no `--run-dir`) is unchanged.

### Memory guardrails on this box

- The RTX 5070 Ti's 16 GB VRAM is shared with the Windows desktop (~2 GB
  used at idle). `train.py` refuses to start when free VRAM falls below
  `resources.min_free_vram_gib` -- if it refuses, eject any model loaded in
  LM Studio and retry (`--allow-low-vram` overrides this, only when you know
  what else is using the GPU).
- `export.py`'s merge step computes a host-specific memory budget from
  `config.resources.*` and **refuses rather than thrashing the machine**
  when the budget does not fit, instead of the hardcoded
  `max_memory={0:"13GiB","cpu":"10GiB"}` that once hung the whole box and
  required a hard reboot (`--allow-unfit-budget` downgrades that refusal to
  a loud warning; use only if you are certain).
- WSL's RAM/swap ceiling is governed by `/mnt/c/Users/rajee/.wslconfig`.
  Changes there only take effect after running `wsl --shutdown` from
  PowerShell (not just closing the WSL terminal).

## Base model

See `MODEL_CARD.md` for the pinned repo id, revision hash, and license
record. No HF token is required.
