---
name: opus-expanded-role
description: "User wants Opus subagents given broad responsibilities (orchestrate + audit + verify), not just final audits"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6ffef739-fb7c-4962-aca7-e774e35a8ec1
  modified: 2026-07-25T04:59:18.382Z
---

User directive (2026-07-24, during the QLoRA run): "give opus 5 more
responsibilities - it has the processing power."

**Why:** VISION.md line 72 already assigns Opus "orchestrate, coordinate and
audit" with Sonnets under it for execution; early sessions were using Opus
only for the final audit and running Sonnets directly from top level.

**How to apply:** For multi-step work in this repo, hand Opus subagents whole
phases (verification, close-out orchestration, audits, cross-checking Sonnet
output); Opus may drive Sonnet subagents itself. Top-level (Fable) still
designs, makes final decisions, commits/pushes. Keep raw bulk execution on
Sonnet for token economy. See also [[win-cuda-training-package]].
