---
name: opus-expanded-role
description: "User wants Opus subagents given broad responsibilities (orchestrate + audit + verify), not just final audits"
metadata:
  type: feedback
---

User directive (2026-07-24, during the QLoRA run): "give opus 5 more
responsibilities - it has the processing power."

**Why:** VISION.md already assigns Opus "orchestrate, coordinate and audit"
with Sonnets under it for execution (the Claude line of the agent-roles
section — line 87 as of 2026-07-29; it was line 72 when this was written, so
grep for "orchestrate, coordinate and audit" rather than trusting the number);
early sessions were using Opus only for the final audit and running Sonnets
directly from top level.

**How to apply:** For multi-step work in this repo, hand Opus subagents whole
phases (verification, close-out orchestration, audits, cross-checking Sonnet
output); Opus may drive Sonnet subagents itself. Top-level (Fable) still
designs, makes final decisions, commits/pushes. Keep raw bulk execution on
Sonnet for token economy. See also [[win-cuda-training-package]] (archived —
on the `stoic_legacy` branch, not on `main`).
