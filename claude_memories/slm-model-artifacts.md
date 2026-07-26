---
name: slm-model-artifacts
description: "Where the fine-tuned SLM lives on the Windows box, which file to move to the Mac, and the standing decision not to retrain it"
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

## Decision REOPENED 2026-07-26 — retrain after the visual re-extraction

The user reopened this: *"Once we re-extract the information, I think retraining would be useful -
maybe it picks up more/better info?"* This is a **strategy decision, recorded, not a measurement.**

What changed and why the old verdict does not bind: the "do not retrain" reasoning below was
reached against a corpus that **did not contain the on-screen material** — slides carrying the
actual rule definitions were never extracted ([[slide-text-not-in-transcripts]]). A model cannot
learn what was never in its training data, so a verdict measured on that corpus says nothing about
a corpus that now includes it.

Sequence, do not reorder: WP-V extraction lands and passes its audit gate → rebuild
`edu/derived/dataset.jsonl` → **measure the delta on the existing eval harness first** (counts, not
verdicts) → only then decide on a training run. Plan:
`docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`. GPU traps:
[[win-cuda-training-package]].

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
