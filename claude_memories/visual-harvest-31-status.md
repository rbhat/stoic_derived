---
name: visual-harvest-31-status
description: "WP-V §3.1 is built and audited — 10,120 visual states from 16 videos, all six HARD checks green, every count re-derived; dHash alone under-splits and needed a second fine-grained criterion"
metadata:
  type: project
---

**§3.1 (deterministic 1 fps harvest + dedupe) is done and audited as of 2026-07-26, with all six
HARD checks green** (`overall_hard_pass: true`). **§3.2 (VLM) is the next thing to build and it runs
on the Mac** — see `docs/notes/2026-07-26-slm-retrain-plan.md` and [[slm-model-artifacts]]; the
retrain downstream of it is decided.

Full write-up, counts, and the ordered resume point:
`docs/notes/2026-07-26-wpv-visual-harvest-progress.md`. Read that before touching WP-V.

- Code on `main`: `edu/pipeline/visual_harvest.py`, `visual_harvest_audit.py`,
  `visual_harvest_calibrate.py`. Artifacts (3.3 GB, gitignored, machine-local):
  `.artifacts/research/visual/`. Full run = 17 min, resumable.
- **10,120 distinct visual states** from 37,211 sampled seconds; live sessions are 51 % of them.
- **dHash alone under-splits and the plan's spec was wrong about this.** A 64-bit dHash is blind to
  localized change — one state absorbed a 5-minute annotated chart walkthrough (208 content
  changes). Fixed with a second criterion: fraction of 720 fine cells changed vs. the run anchor,
  `FINE_FRAC = 0.005`, calibrated against ground truth and recorded as a **tooling** decision, not a
  strategy parameter.
- The asymmetry that drives every threshold here: **under-splitting loses content the VLM never
  sees and is unrecoverable; over-splitting only costs VLM wall time.**
- **A2 was fixed by restating the check, not by changing the harvest.** Its old `argmin` over
  `rep_t ± 2` was decided by tie-breaking whenever content is held. It now asks whether `rep_t` is
  *among* the min-Hamming candidates **and** whether the distance at `rep_t` is ≤ 8, gated at ≥ 90 %
  on states held ≥ 10 s only (94.9 % / 100 % measured); shorter buckets are reported, not gated,
  because a ±1 s ambiguity on a 1-second state is video motion, not a defect. The membership test
  alone passes a deliberately wrong frame 64 % of the time — that is why the absolute bound is
  paired with it, and why the fix ships with a negative control that makes the gate fail.
- **Every VLM budget derived here was an estimate and all of them are superseded.** The plan's
  6 s/state (≈16.9 h) and the calibration's ~12 h both predate measurement; the measured rate
  bracket is in [[wpv-32-extraction-ops]] § Measured rates. What survives from this file is the
  **corpus size: 10,120 states**, against the calibration's 5-video extrapolation of 7,249.

**Correction:** the First Red/Green Day slide is held **2105–2220 s (00:35:05–00:37:00, 115 s)**,
not the 45 s that the plan and older notes claim — that figure came from two sparse keyframes inside
a longer hold. Verified by eye and recovered as one state,
`concept_simple_stoic_setups_sss#0031`. That slide is **text-only**: the Jan 26–30 chart sits in the
adjacent `#0030`, and `#0032` shows a *December* example — see [[red-day-definition]].

See [[slide-text-not-in-transcripts]], [[red-day-definition]], [[audit-derived-numbers]].
