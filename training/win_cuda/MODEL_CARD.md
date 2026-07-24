# Base model record

Pinned at package-build time (2026-07-24). All training and export runs must
use exactly this revision; `train.py` refuses non-smoke runs without it.

- **Repo id**: `Qwen/Qwen3-8B` (HuggingFace Hub)
- **Revision (commit hash)**: `b968826d9c46dd6066d109eabc6255188de91218`
- **Upstream last modified**: 2025-07-26
- **License**: Apache-2.0 (permits fine-tuning and local redistribution of
  derivatives with attribution; see upstream LICENSE in the pinned revision)
- **Access**: public, no HF token required
- **Local cache**: `$HF_HOME` (default `<repo>/.artifacts/training/hf`, auto-set by `config.py`)

## Role of the fine-tuned derivative

The QLoRA fine-tune produced from this base is an **offline research
assistant only**: it proposes rule candidates with `video_id + hms` citations
into the human review queue. It is never wired into the live signal path
(VISION.md guardrails). Export target is GGUF for local LM Studio inference.
