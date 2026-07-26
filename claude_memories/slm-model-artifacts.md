---
name: slm-model-artifacts
description: "Where the fine-tuned SLM lives on the Windows box, which file to move to the Mac, and the 2026-07-26 decision to retrain it after the visual extraction"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 55875ae9-8877-4cbf-92fe-1c4e67ee40a4
  modified: 2026-07-26T03:45:38.089Z
---

Fine-tuned run **`adb3c96ab6020c23`** — Qwen3-8B (`Qwen/Qwen3-8B` @ `b968826d9c46dd6066`), LoRA
r=16 / alpha=32 / dropout 0.05, targeting all seven attn+MLP projections
(q,k,v,o,gate,up,down_proj). Trained on **non-thinking targets** — keep thinking OFF at inference
or the eval behaviour will not reproduce.

All paths relative to the repo; **`.artifacts/` is gitignored, so none of this travels via git**
(Google Drive is the transfer route per VISION).

| artifact | path | size |
|---|---|---|
| GGUF q4_K_M — **take this to the Mac** | `.artifacts/training/exports/adb3c96ab6020c23/gguf/model.q4_K_M.gguf` | 4.7 GB |
| GGUF f16 | `.artifacts/training/exports/adb3c96ab6020c23/gguf/model.gguf` | 15.3 GB |
| Merged HF (for MLX conversion) | `.artifacts/training/exports/adb3c96ab6020c23/merged/` | 15.3 GB |
| LoRA adapter only (needs base) | `.artifacts/training/runs/adb3c96ab6020c23/checkpoint/final/` | 95 MB |
| Base model cache | `.artifacts/training/hf/hub/models--Qwen--Qwen3-8B` | 16 GB |

`chat_template.jinja` ships alongside the merged and adapter exports. Intermediate checkpoints
`checkpoint-250` / `checkpoint-298` are also under the run dir.

## On the Mac (2026-07-26)

The transferred copies are under **`artifacts/`** — note: **no leading dot**, and renamed:

| file | size |
|---|---|
| `artifacts/training/exports/adb3c96ab6020c23/gguf/stoic_derived_model.q4_K_M.gguf` | 5.0 GB |
| `artifacts/training/exports/adb3c96ab6020c23/gguf/stoic_derived_model.gguf` (f16) | 16.4 GB |

This violates [[artifact-locality]] (everything belongs under `.artifacts/`) and `artifacts/` shows
as untracked in git status. Worth moving. **No runner is installed** — `llama-cli`, `llama-server`
and `ollama` are all absent, so llama.cpp must be built before this model can be run here.

## DECIDED 2026-07-26 — retrain, after the visual extraction

The user decided it outright: ***"we need to redo the SLM."*** Earlier the same day:
*"Once we re-extract the information, I think retraining would be useful - maybe it picks up
more/better info?"* This is a **strategy decision, recorded, not a measurement.** Do not re-litigate
it; the open questions are execution, not whether.

**Explicit plan: `docs/notes/2026-07-26-slm-retrain-plan.md`.** Read it before starting anything.

**The chain spans two machines and the split is forced, not a preference.** The Windows box is a
**16 GB RTX 5070 Ti**; `qwen3-vl-30b-a3b-instruct-mlx` needs ~17 GB even at 4-bit and **cannot run
there**. So:

- **Mac** — WP-V §3.2 VLM extraction of the 10,120 states (≈16.9 h), §3.3 audit, rebuild
  `edu/derived/dataset.jsonl`. Then push.
- **WSL** — eval delta → QLoRA retrain → eval. **Cannot start until the Mac stage is pushed.**

User's call on sequencing: **measure the eval delta, then train regardless** — the delta is the
record of what changed, not a gate; nothing waits overnight for a human.

Launch both through `scripts/launch_bg.sh <name> -- <cmd>` (detaches, inhibits machine sleep,
prints a pid) and monitor a later session's job with `scripts/job_status.sh <pid>` — see
[[check-dont-relaunch-detached-jobs]].

What changed and why the old verdict does not bind: the "do not retrain" reasoning below was
reached against a corpus that **did not contain the on-screen material** — slides carrying the
actual rule definitions were never extracted ([[slide-text-not-in-transcripts]]). A model cannot
learn what was never in its training data, so a verdict measured on that corpus says nothing about
a corpus that now includes it.

Sequence, do not reorder: WP-V extraction lands and passes its audit gate → rebuild
`edu/derived/dataset.jsonl` → measure the delta on the existing eval harness → train. Plans:
`docs/notes/2026-07-26-slm-retrain-plan.md` (execution) and
`docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md` (the §3.2 spec, still binding).
GPU traps: [[win-cuda-training-package]].

**What would make this the wrong call**, recorded now so it is not rationalised later: the §3.3
audit shows OCR is unreliable (then fix the extractor, not the text model), or the rebuilt dataset
is barely different from the current one (then there is nothing new to learn — say so). Neither is
a reason to skip the extraction; both are reasons to stop before the GPU stage.

## Superseded standing decision (2026-07-25): do NOT retrain or rebuild

Kept because the reasoning is still correct *for the old corpus*, and item 3 still constrains
sequencing:

1. The fine-tune's **only** real win is *closed-book* grounding — citing from memory with no corpus
   in the prompt (`cited_qa`: 240/240 real corpus videos vs the instructed base's 297/297
   invented). See [[eval-comparison-wp-progress]] for the full audited verdict.
2. Both tasks the SLM now serves — resolving `unresolved_decisions`, and building fixtures from
   `edu/derived/` — are **open-book**: the source goes in the prompt. That is the `rule_candidate`
   regime, where the fine-tune is neutral on citations (349/349 vs 346/349, p=0.25) and materially
   **worse** on body text (.395 vs .630).
3. You cannot train toward the new objective anyway — its training signal is *labelled fixtures*,
   which do not exist yet. Building them is the work ([[case-study-fixture-track]]).

The trigger that would reopen a model decision: if chart reading proves unreliable during the
fixture pass. That would call for a **vision** model change (the Mac's `qwen3-vl-30b-a3b-instruct-mlx`,
which already produced `moments.json`), not another text fine-tune on citations.

**That trigger fired on 2026-07-26** — a keyframe caption was found describing a chart that was not
on screen, and slide text was absent corpus-wide. Hence WP-V above: the vision pass comes first,
the text retrain is downstream of it.
