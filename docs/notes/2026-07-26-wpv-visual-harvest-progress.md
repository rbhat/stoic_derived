# WP-V §3.1 — frame harvest: status, audit counts, resume point

**Date:** 2026-07-26 · **Status:** §3.1 landed, audit gate one check short of green · **Plan:**
`docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`

Counts, not verdicts (ADR-0021). §3.2 (VLM) and §4 (retraining) are **not started** and §4 needs
the user's sign-off on these numbers first.

---

## 1. What exists now

Code (tracked, on `main`, unstaged):

- `edu/pipeline/visual_harvest.py` — the harvest. Three resumable stages per video:
  `decode` → `states` → `extract`.
- `edu/pipeline/visual_harvest_audit.py` — the audit gate (A1–A8).
- `edu/pipeline/visual_harvest_calibrate.py` — the `FINE_FRAC` sweep.

Artifacts (gitignored, **3.3 GB**, do not travel between machines):
`.artifacts/research/visual/<video_id>/` with `gray_1fps.npy`, `frames_index.jsonl`,
`states.jsonl`, `keyframes_v2/*.jpg`, `state.json`; `manifest.json` at the root.

Run: `.venv/bin/python edu/pipeline/visual_harvest.py` (17m17s for all 16 videos, resumable,
per-video elapsed/ETA). Audit: `.venv/bin/python edu/pipeline/visual_harvest_audit.py`.

## 2. Method as built (differs from the plan — deliberately)

The plan specified 1 fps + dHash Hamming ≤ 4. **dHash alone under-splits badly** and that was
caught by the audit, not by inspection. A 64-bit dHash (9×8 grid) only fires on *global* layout
change; it is blind to a drawn level, an added bullet line, an annotation, or price action.

Measured on the v1 (dHash-only) harvest — content changes landing **inside** a state instead of at
its boundary:

| video | states | changes inside a state |
|---|---|---|
| `concept_simple_stoic_setups_sss` | 50 | 7 |
| `concept_htf_stoic_trader_protocol` | 75 | **214** |
| `cs_vol1_stoic_edge_in_action_case_studies` | 18 | **208** |

`cs_vol1#0007` spanned 00:00:14–00:05:27 and absorbed 208 distinct visual changes into one frame —
an entire annotated chart walkthrough that the VLM would never have seen. Same class of failure as
the one WP-V exists to fix, just moved from sampling to deduping.

**Fix: two-criterion clustering.** A consecutive second joins the current run iff **both** hold
against the run's *anchor* (never against the previous frame — anchor comparison is what stops slow
drift from walking away):

1. `hamming(dhash, anchor_dhash) <= 4` — global layout, and
2. `changed_cell_frac(fine, anchor_fine) <= FINE_FRAC` — localized content, the fraction of 720
   8×8-px cells whose mean gray moves more than `FINE_DELTA = 6.0` levels.

One gray cache at **288×160** serves both exactly, with no interpolation: 20×32 blocks give the
8×9 dHash grid, 8×8 px cells give 720 fine cells.

### `FINE_FRAC = 0.005` — tooling decision, 2026-07-26

From `visual_harvest_calibrate.py` over 5 videos (residual under-split = share of independently
detected content changes still landing inside a state):

| FINE_FRAC | corpus states | VLM wall @6s | worst-video residual under-split |
|---|---|---|---|
| 0.005 | ~7,249 | 12.1 h | **1.1 %** |
| 0.0075 | ~5,930 | 9.9 h | 5.8 % |
| 0.01 | ~5,054 | 8.4 h | 19.1 % |
| 0.02 | ~3,270 | 5.5 h | 59.9 % |
| 0.03 | ~2,582 | 4.3 h | 79.3 % |

0.0075 → 0.01 is a sensitivity cliff. 0.005 is the only swept value clearing the A8 gate on every
video, and the 115 s SSS slide hold stays one state at every value tested, so it does not shatter
static slides. The bias is deliberate and asymmetric: **under-splitting loses content the VLM never
sees and is unrecoverable; over-splitting only costs VLM wall time.** This is a tooling threshold
calibrated against ground truth, not a strategy parameter (ADR-0004 is untouched).

## 3. Harvest counts (16/16 videos, 37,211 frames sampled at 1 fps)

**10,120 distinct visual states**, 10,120 full-resolution keyframes.

| video | states | | video | states |
|---|---|---|---|---|
| `concept_candle_swing_theory_pdh_pdl_pdc` | 599 | | `cs_vol3_gold_futures_study` | 581 |
| `concept_htf_stoic_trader_protocol` | 530 | | `cs_vol4_how_to_stay_out_of_choppy_price_action` | 216 |
| `concept_simple_stoic_setups_sss` | 53 | | `cs_vol5_nq_v_shape_fomo_study` | 432 |
| `concept_stoic_edge_system_module_1_is_live` | 110 | | `cs_vol6_gbp_jpy_lesson_on_patience` | 336 |
| `concept_the_only_trading_video_that_you_will_ever_need` | 831 | | `cs_vol7_rty_textbook_break_retest` | 286 |
| `cs_vol1_stoic_edge_in_action_case_studies` | 439 | | `live_3_5r_on_nq` | 665 |
| `cs_vol2_nasdaq_range_study` | 568 | | `live_4_14r_on_nq` | 1,250 |
| | | | `live_4_2r_on_nq` | 1,432 |
| | | | `live_4_3r_on_cl` | 1,792 |

Live sessions are 5,139 of the 10,120 (51 %) — a live chart genuinely changes every second, so they
dominate the count while being the least likely to hold definitional slides. Per plan §1 the pass is
exhaustive and does not sample, so they are kept. This is the lever if VLM time needs cutting.

## 4. Audit gate (A1–A8) — `.artifacts/research/visual/audit_31.json`

| check | HARD | result |
|---|---|---|
| A1 coverage — one row per second, count == npy == duration, strictly ascending | yes | **pass**, 16/16 |
| A2 seek alignment / phase offset | yes | **fail as gated** — see below |
| A3 known-slide recall | yes | **pass** |
| A4 dedupe shape | no | informational |
| A5 determinism — redecode sha256 | yes | **pass** |
| A6 artefact integrity — every `source_frame` exists, right resolution, one representative per state | yes | **pass**, 16/16 |
| A8 residual under-split, gate ≤5 % per video | yes | **pass**, max 5 % |

**A3 is the one that matters and it passes.** The First Red/Green Day slide is recovered as
`concept_simple_stoic_setups_sss#0031`, `[00:35:05–00:37:00]`, 115 s, one state, representative
`keyframes_v2/0031_003700.jpg` — visually verified to be a clean full-res capture of the slide.

**Correction to the record:** the plan and two memories say that slide is held "00:35:12 → 00:35:57".
It is actually held **2105–2220 s (00:35:05 → 00:37:00, 115 s)** — verified by eye at 2108, 2120,
2150, 2175 and 2210. The 45 s figure came from two old sparse keyframes *inside* a longer hold.

### A2 is the only open item, and the check is wrong, not the data

A2 asks whether the JPEG handed to the VLM is really the frame that was clustered. As implemented it
takes `argmin` of Hamming distance over `rep_t ± 2` and gates on the offset being 0. **For held
content every candidate second is identical, so the argmin is decided entirely by tie-breaking** —
the reported "−1 skew" (`{-2:4, -1:20, 0:70, 1:3, 2:3}`, zero_share 0.70) measures the tie-break
rule, not a phase offset. A suspiciously clean number is a symptom of a broken generator (ADR-0021);
an early version of the probe scored `-2` in 52/60 cases for exactly this reason.

Re-measured with the meaningful question — *is `rep_t` among the minimum-Hamming candidates?*:

| bucket | n | `rep_t` optimal | Hamming at `rep_t` (median / max) |
|---|---|---|---|
| states held ≥ 10 s | 60 | **93 %** | 0 / 5 |
| 1-second states | 60 | 53 % | 1 / 33 |

Alignment is correct where it matters. On a 1-second state the content genuinely changes within the
second, so a ±1 frame ambiguity is inherent to seeking, not a defect.

**To close A2:** restate the check as "`rep_t` is among the minimum-Hamming candidates", gate it on
states held ≥ 10 s (target ≥ 90 %), and report the 1-second bucket without gating it. Probe:
`.scratch/`-equivalent working copy is at the session scratchpad; re-implement inside
`visual_harvest_audit.py`.

## 5. Resume point — do these in order

1. **Fix A2 in `visual_harvest_audit.py`** as described above, re-run the audit, confirm all HARD
   checks green.
2. **Get the user's sign-off on the §3.3 counts** (this note, §3 and §4). Do not skip this.
3. **Then §3.2 (VLM).** `qwen3-vl-30b-a3b-instruct-mlx` is loaded in LM Studio at
   `http://localhost:1234/v1` and confirmed available. Per-state record schema is in the plan §3.2.
   Hard rules: `ocr_text` verbatim, interpretation in separate fields, chart numbers are proposals
   checked against `.artifacts/research/bars/`, every record cites `video` + `t_start`. Must be
   resumable with elapsed/ETA per video; budget ~12 h at 6 s/state.
4. **§4 (retraining) is downstream and needs sign-off on the audit counts first.** Do not start it.

## 6. Traps hit (also distilled into `coding_rules.md`)

- `np.save(path, arr)` appends `.npy`, breaking `x.npy.tmp` atomic writes — pass a file handle.
- ffmpeg cannot infer a container from `out.jpg.tmp` — pass `-f image2` explicitly.
- A stage gated only on its status flag never notices deleted outputs — gate on disk state.
- Re-clustering orphans the previous run's JPEGs; `stage_states` now prunes unreferenced frames so
  the VLM can never be handed a stale keyframe.
- `min()` over `(distance, offset)` tuples silently resolves ties by offset — do not call that an
  argmin result.
