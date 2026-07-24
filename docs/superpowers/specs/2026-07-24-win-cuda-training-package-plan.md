# Windows CUDA Training Package — Implementation Plan

Date: 2026-07-24. Status: approved to build (user said "go"; base model decision
made). This plan is self-contained so work can resume after a context clear.

## Goal

Build the reproducible Windows QLoRA training package required by
`Windows_setup.md` ("When fine-tuning starts" checklist). Until this package is
committed and pushed, no fine-tune may launch. The fine-tuned SLM is an
**offline research assistant only** — it proposes cited rule candidates for
human review. No model output ever touches the live signal path (VISION.md
lines 12–16; roadmap §1 guardrails).

## Decisions already made (do not re-litigate)

1. **Base model: Qwen3-8B** (user-selected 2026-07-24). Apache-2.0. Pin the
   exact HuggingFace repo id + revision (commit hash) + license record at build
   time. ~5 GB download, no HF token needed.
2. **Text-only v1.** Train on narration + label/why with citations. Keyframe
   images stay on the Mac VLM mining side (VISION environment strategy: Mac
   mines & infers, Windows trains).
3. **Split by video, not by record** — held-out videos give honest citation
   fidelity / generalization eval. Immutable split + content digest committed.
4. **Standalone training project at `training/win_cuda/`** with its own
   `pyproject.toml` + `uv.lock`, so CUDA pins never pollute the portable dev
   environment (portability contract).
5. **SUPERSEDED 2026-07-24 (user directive): all run artifacts stay relative
   to the repo working directory.** The original choice (`~/stoic-training/`
   on ext4) hid logs on another drive and inflates the WSL VHD on C: (92%
   full); the repo lives on F: (~649 GB free). New default for
   `STOIC_TRAIN_HOME`: `<repo>/.artifacts/training/` (git-ignored — add to
   .gitignore), env-var override still allowed. Migration before the real
   run: `mv ~/stoic-training/{hf,datasets,runs,llama.cpp,venv}` into
   `.artifacts/training/` (or rebuild venv there), update README/config
   defaults + tests, re-point HF_HOME. Accepted trade-off: drvfs I/O is
   slower for checkpoint saves.

## Environment facts (verified 2026-07-24 on this box)

- WSL2 Ubuntu; repo at `/mnt/f/dev/stoic_derived`; uv 0.11.32.
- RTX 5070 Ti, 16 GB VRAM, visible via `nvidia-smi` in WSL; driver CUDA 13.3.
- GPU is **Blackwell (sm_120)** → requires PyTorch ≥ 2.7 built for cu128 (extra
  index `https://download.pytorch.org/whl/cu128`) and a Blackwell-capable
  bitsandbytes. Verify exact versions during build and pin them; this is the
  highest-risk pin.
- All portable SP0/SP1/SP2 checks pass on this machine (captured in
  `.scratch/windows/`). Strict rulebook source verification passes → full
  `edu/` corpus is present locally.
- LM Studio installed (`/mnt/c/Users/rajee/.lmstudio/`, `lms.exe` in `bin/`,
  models at `C:\Users\rajee\.cache\lm-studio\models`). Local models
  (Qwen3-Coder-30B, Qwen3.5-4B) are **GGUF = inference-only; not usable as a
  training base**. LM Studio's role: run the exported fine-tuned GGUF offline.

## Dataset facts

`edu/derived/dataset.jsonl`: 2,233 keyframe records, 16 videos, 1.6 MB.
Schema per record: `video_id, category, title, t, hms, image, source, label,
why, narration, caption`. Fill rates: narration 2233/2233; label+why 1526/2233
(source=llm, the Mac mining output); caption 0. Categories: concept 860,
live_session 797, case_study 576.

## Package layout to build

```
training/win_cuda/
  pyproject.toml          # pinned: torch cu128, transformers, peft, trl,
  uv.lock                 #   bitsandbytes, datasets, accelerate (exact pins)
  README.md               # setup + commands + env vars (STOIC_TRAIN_HOME etc.)
  MODEL_CARD.md           # base model id, revision hash, license record
  config/
    qlora.yaml            # r, alpha, target modules, seed, max_len,
                          #   batch/grad-accum bounded for 16 GB
  src/stoic_training/
    build_dataset.py      # dataset.jsonl -> SFT pairs; emits digest + frozen
                          #   by-video train/eval split (committed)
    train.py              # QLoRA SFT, fixed seeds, resumable
    evaluate.py           # citation fidelity + held-out + conflict surfacing
    infer.py              # offline inference against local checkpoint
    export.py             # merge LoRA -> safetensors -> GGUF for LM Studio
    manifest.py           # content-addressed run manifest (dataset digest,
                          #   code rev, config hash, base revision, outputs)
  splits/
    split-v1.json         # immutable video-level split + corpus digest
  tests/                  # deterministic unit tests (no GPU needed)
```

SFT task formats produced by `build_dataset.py` (deterministic templates):
1. **Rule-candidate extraction**: narration window (+ label/why) → structured
   candidate (setup, entry, stop, target, invalidation, confluence semantics)
   with `video_id + hms` citation.
2. **Cited concept QA**: question about a concept → answer citing source
   timestamps.
3. **Conflict surfacing**: contradictory excerpts → flag ambiguity /
   unresolved question (feeds the rulebook decision queue).

Evaluation (`evaluate.py`, deterministic scoring):
- **Citation fidelity**: every cited `video_id:hms` must exist in the corpus
  and the cited narration must support the claim (string/fuzzy match against
  source records — checkable without a model judge).
- **Held-out behavior**: task metrics on held-out videos vs train videos.
- **Conflict handling**: known contradictory pairs must be flagged, not
  averaged away.

## Execution steps (VISION agent process: Fable designs + closes loop, Sonnet
subagents execute, Opus subagent audits)

1. **[Fable] Scaffold + pins spike**: create `training/win_cuda/` skeleton;
   resolve the Blackwell pin set (torch cu128 + bitsandbytes) with a minimal
   GPU smoke check (`torch.cuda.is_available()`, 4-bit load of a tiny model);
   lock. Highest risk first.
2. **[Sonnet] Dataset builder**: `build_dataset.py` + `splits/split-v1.json` +
   digest + unit tests. Pure CPU, deterministic.
3. **[Sonnet] Train/eval/infer/export scripts** + `qlora.yaml` + `manifest.py`
   + unit tests (config validation, manifest hashing; no GPU in tests).
4. **[Fable] Pin base model revision**: fetch Qwen3-8B, record repo id +
   revision hash + license in `MODEL_CARD.md`.
5. **[Fable] Bounded smoke run**: tiny-step QLoRA run (e.g. 10 steps) to prove
   the loop works end-to-end on 16 GB; not a real fine-tune. Verify manifest +
   export path (GGUF loads in LM Studio via `lms.exe`).
6. **[Opus] Audit** against Windows_setup.md checklist + VISION guardrails
   (offline-only, no live-path coupling, reproducibility).
7. **[Fable] Close loop**: run portable checks, commit, push. Only after the
   push is the real fine-tune authorized to launch.

## Constraints / reminders

- Do NOT modify VISION.md. Do not touch `edu/` content (education is
  immutable source; ADR 0004 authority order).
- No secrets in repo. No HF token required for Qwen3-8B.
- Repo-side code must keep portable checks green: the root dev env must not
  gain CUDA deps; `training/win_cuda` tests must skip cleanly without GPU.
- Use `.scratch/` for throwaway work; bash is pre-authorized in this repo.
- Minimize expensive tokens: Sonnet for execution, Opus only for the audit.
