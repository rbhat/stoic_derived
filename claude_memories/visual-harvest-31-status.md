---
name: visual-harvest-31-status
description: "WP-V §3.1 is built and audited — 10,120 visual states from 16 videos; dHash alone under-splits and needed a second fine-grained criterion; A2 is the one open audit check and the check itself is wrong"
metadata:
  type: project
---

**§3.1 (deterministic 1 fps harvest + dedupe) is done and audited as of 2026-07-26.** §3.2 (VLM)
and §4 (retraining) are **not started**; §4 needs the user's sign-off on the audit counts.

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
- **A2 is the only open audit check, and the check is wrong, not the harvest.** Its `argmin` over
  `rep_t ± 2` is decided by tie-breaking whenever content is held. Re-measured properly, `rep_t` is
  among the best-matching frames for 93 % of states held ≥ 10 s. Restate the check before gating.

**Correction:** the First Red/Green Day slide is held **2105–2220 s (00:35:05–00:37:00, 115 s)**,
not the 45 s that the plan and older notes claim — that figure came from two sparse keyframes inside
a longer hold. Verified by eye and recovered as one state,
`concept_simple_stoic_setups_sss#0031`.

See [[slide-text-not-in-transcripts]], [[red-day-definition]], [[audit-derived-numbers]].
