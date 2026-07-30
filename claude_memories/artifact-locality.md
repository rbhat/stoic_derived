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
`<repo>/.artifacts/training/`). Keep `.artifacts/` in .gitignore. This is
written into VISION.md itself (the setup/environments numbered list — line 32
as of 2026-07-29), so it is a project contract, not just a preference. Note
`.gitignore` also blocks a bare `/artifacts/` dir, which has been created by
accident before.

The general rule — regenerable output under `.artifacts/`, the code that
generates it tracked — still holds. The specific example this memory used
(`.artifacts/research/bars/` alongside tracked `research/`) refers to the
`research/` and `training/` trees, which the 2026-07-29 reset removed from
`main`; they and [[edge-measurement-first-probe]] are on `stoic_legacy`.
