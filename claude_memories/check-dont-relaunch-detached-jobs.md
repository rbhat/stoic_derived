---
name: check-dont-relaunch-detached-jobs
description: "User directive — detached GPU jobs and watcher shells are already running; check them, never re-launch"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f8c47e52-d8d8-4a54-a18d-91b7e1a72f62
  modified: 2026-07-26T02:59:17.192Z
---

Long-running detached shells (GPU eval/train jobs, and the chained watcher
script that auto-launches the next job) survive context clears, so a fresh
session has no record of them. **Before launching anything on the GPU, CHECK
whether it is already running** — do not launch, re-arm, or re-create blindly.

**Current state (verified 2026-07-26): nothing is running.** The v3 chain
completed all three runs and the GPU is free — see [[eval-comparison-wp-progress]].
Re-verify rather than trusting this line; it ages.

**Jobs launched via `scripts/launch_bg.sh` are self-describing** — hand a fresh session just the
pid and run `scripts/job_status.sh <pid>`. It resolves the pid to its job dir under
`.artifacts/jobs/<name>/`, and returns **0** running/clean · **1** crashed · **2** stalled.
`scripts/launch_bg.sh --list` shows every job. The launcher refuses to start a job whose previous
pid is still alive, which is the same trap this memory exists for.

Check with, in order:
- `tail` the newest `.artifacts/training/logs/chain*-*.log` (what the watcher is waiting on / what it launched)
- `pgrep -af "stoic_training|chain_"` (is it alive) — but note this pattern also matches YOUR OWN
  shell wrapper running the pgrep, which reads as a false "it's running". Confirm against the venv
  python path (`pgrep -af "venv/bin/python3 -m stoic_training"`) or parse the pid out of the chain log.
- `cat .artifacts/training/runs/<run-id>/progress.json` (step/ETA; is `updated_utc` recent)
- `scripts/health.sh evaluate`

**Why:** these jobs are `setsid`-detached and outlive the session, so a fresh
context has no record of them. Re-launching one puts two 8B models on the same
GPU — OOM, corrupted run artifacts, and hours of wasted compute. Only launch
after confirming nothing is already running.

**How to apply:** treat a stale `progress.json` (`updated_utc` not advancing) as
a stall to diagnose, not as permission to start a second copy. Relaunch only
once `pgrep` shows the process is genuinely gone. See
[[eval-comparison-wp-progress]] for run ids and log paths, and
[[win-cuda-training-package]] for the `uv run` cwd trap.
