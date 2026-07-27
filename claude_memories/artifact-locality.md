---
name: artifact-locality
description: "User directive — all run artifacts stay under the repo working directory, never in ~ or other drives"
metadata:
  type: feedback
---

On 2026-07-24 the user directed that everything a run writes (logs,
checkpoints, caches, datasets, exports) must live under the repo working
directory in git-ignored folders (`.artifacts/`), never in `~`, system temp,
or another drive; env-var override is the only sanctioned relocation.

**Why:** logs in `~` were invisible on another drive, and the WSL ext4 VHD
lives on C: which is 92% full — heavy caches there silently inflate it; the
repo drive (F:) has ample space.

**How to apply:** default workspace paths to `<repo>/.artifacts/...`
(see [[win-cuda-training-package]] — `STOIC_TRAIN_HOME` defaults to
`<repo>/.artifacts/training/`). Keep `.artifacts/` in .gitignore. This is now
also written into VISION.md itself (line 32, the setup/environments section),
so it is a project contract, not just a preference.

Applies to research too: `.artifacts/research/bars/` holds regenerable bars
while research *code* stays tracked in `research/` — see
[[edge-measurement-first-probe]].
