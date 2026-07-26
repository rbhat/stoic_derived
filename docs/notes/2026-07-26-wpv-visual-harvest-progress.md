# WP-V §3.1 — frame harvest: status, audit counts, resume point

**Date:** 2026-07-26 · **Status:** §3.1 landed, **all six HARD audit checks green** · **Plan:**
`docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md`

Counts, not verdicts (ADR-0021). §3.2 (VLM) and §4 (retraining) are **not started** and §4 needs
the user's sign-off on these numbers first. Every count below was re-derived from the artefacts on
2026-07-26 and reconciles — see §7.

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
| A2 seek alignment | yes | **pass** — check restated, see below |
| A3 known-slide recall | yes | **pass** |
| A4 dedupe shape | no | informational |
| A5 determinism — redecode sha256 | yes | **pass** |
| A6 artefact integrity — every `source_frame` exists, right resolution, one representative per state | yes | **pass**, 16/16 |
| A8 residual under-split, gate ≤5 % per video | yes | **pass**, max 1.1 % |

`overall_hard_pass: true`, exit 0.

**A3 is the one that matters and it passes.** The First Red/Green Day slide is recovered as
`concept_simple_stoic_setups_sss#0031`, `[00:35:05–00:37:00]`, 115 s, one state, representative
`keyframes_v2/0031_003700.jpg` — visually verified to be a clean full-res capture of the slide.

**Correction to the record:** the plan and two memories say that slide is held "00:35:12 → 00:35:57".
It is actually held **2105–2220 s (00:35:05 → 00:37:00, 115 s)** — verified by eye at 2108, 2120,
2150, 2175 and 2210. The 45 s figure came from two old sparse keyframes *inside* a longer hold.

### A2 — the check was wrong, not the data. Fixed 2026-07-26 and now green.

A2 asks whether the JPEG handed to the VLM is really the frame that was clustered. The v2
implementation took `argmin` of Hamming distance over `rep_t ± 2` and gated on the offset being 0.
**For held content every candidate second is identical, so that argmin was decided entirely by
tie-breaking** — the reported "−1 skew" (`{-2:4, -1:20, 0:70, 1:3, 2:3}`, zero_share 0.70) measured
the tie-break rule, not a phase offset. (An early probe scored `-2` in 52/60 cases for exactly that
reason; a suspiciously clean number out of a degenerate comparison is the ADR-0021 symptom of a
broken generator.)

**As now implemented**, A2 is a membership test plus an absolute bound, stratified by state
duration, sampling up to 60 per bucket on an even per-video quota:

1. is `rep_t` **among** the minimum-Hamming candidates in `rep_t ± 2`? Ties count as success —
   indistinguishable seconds mean the seek cannot be wrong.
2. is `hamming(JPEG, cached dHash at rep_t) ≤ 8`? The v2 spec's own bound, unchanged.

Both are gated at ≥ 90 % **on states held ≥ 10 s only**; the other buckets are reported. Also hard:
zero unreadable JPEGs, and `states.jsonl`'s own `dhash` must equal the `frames_index` row at
`rep_t` (else the whole comparison runs against the wrong row).

| bucket | population | sampled | `rep_t` optimal | Hamming ≤ 8 | best match inside the state's own span | Hamming at `rep_t` med/p95/max |
|---|---|---|---|---|---|---|
| held ≥ 10 s **[gated]** | 450 | 59 | **94.9 %** | **100 %** | 98.3 % | 0 / 2 / 5 |
| 1–9 s | 2,595 | 59 | 83.0 % | 100 % | 94.9 % | 0 / 2 / 3 |
| single-second | 7,075 | 60 | 61.7 % | 96.7 % | 61.7 % | 1 / 6 / 14 |

The monotone gradient by duration is the expected shape: on a 1-second state the content genuinely
changes within the second, so a ±1 frame ambiguity is inherent to seeking rather than a defect, and
`best_inside_span` collapses to the membership test because the span is one second wide. Gating
that bucket would gate on video motion.

**Why criterion 2 was added back.** The membership test alone is weak, and measuring it says so:
fed a JPEG from a state ≥ 60 s away in the same video, it still "passes" 64.4 % of the time — a
wholly wrong frame is roughly equally wrong at all five candidate seconds and so ties them. It can
only see misalignment of ≤ 2 s, by construction. Bucketing is what makes an absolute bound usable:
over held states the true distance distribution is median 0 / p95 2 / max 5 against **24 / 31 / 40**
for the deliberately wrong frame, where the old corpus-wide sample's fat tail (p95 15) had made any
absolute bound look untenable.

**Negative control, run through `check_a2` itself** with `jpg_dhash` monkeypatched to return a
far-away state's JPEG: `hard_pass=False`, `close_at_rep` 5.1 % against the 90 % gate. The check has
power; it is not passing by construction.

The three held-bucket misses are all boundary effects, not mislabelled content:
`concept_stoic_edge_system_module_1_is_live#0016` (excess 5, `rep_t=274` is the last second of
`[232, 274]`), `cs_vol2#0223` and `cs_vol3#0187` (excess 1 each). In all three the best-matching
second still lies inside the state's own span.

## 5. Resume point — do these in order

1. ~~Fix A2 in `visual_harvest_audit.py`, re-run the audit, confirm all HARD checks green.~~
   **DONE 2026-07-26** — see §4. `overall_hard_pass: true`.
2. **Get the user's sign-off on the counts** (this note, §3, §4 and §7). Do not skip this.
3. **Then §3.2 (VLM).** `qwen3-vl-30b-a3b-instruct-mlx` is loaded in LM Studio at
   `http://localhost:1234/v1` and confirmed available. Per-state record schema is in the plan §3.2.
   Hard rules: `ocr_text` verbatim, interpretation in separate fields, chart numbers are proposals
   checked against `.artifacts/research/bars/`, every record cites `video` + `t_start`. Must be
   resumable with elapsed/ETA per video.
   **Budget ≈ 16.9 h at 6 s/state, not the ~12 h quoted earlier** — that figure came from the
   calibration's *extrapolated* 7,249 states (5 videos × `scale_factor` 2.5118), and the measured
   corpus is 10,120. If that wall time needs cutting, the lever is the 5,139 live-session states
   (8.6 h of the 16.9), which are the least likely to hold definitional slides.
4. **§4 (retraining) is downstream and needs sign-off on the audit counts first.** Do not start it.

## 6. Traps hit (also distilled into `coding_rules.md`)

- `np.save(path, arr)` appends `.npy`, breaking `x.npy.tmp` atomic writes — pass a file handle.
- ffmpeg cannot infer a container from `out.jpg.tmp` — pass `-f image2` explicitly.
- A stage gated only on its status flag never notices deleted outputs — gate on disk state.
- Re-clustering orphans the previous run's JPEGs; `stage_states` now prunes unreferenced frames so
  the VLM can never be handed a stale keyframe.
- `min()` over `(distance, offset)` tuples silently resolves ties by offset — do not call that an
  argmin result.
- An extrapolated number and a measured one must not be quoted interchangeably: the VLM budget was
  carried forward from the calibration's 5-video extrapolation (7,249) long after the full harvest
  had measured 10,120.

## 7. Count reconciliation — what was re-derived independently, 2026-07-26

Every number in §3 and §4 was recomputed from the artefacts rather than read back from the report
that produced them (ADR-0021).

| claim | independent check | result |
|---|---|---|
| 16 videos, exhaustive | `find edu -iname '*.mp4' …` vs `edu/derived/*/meta.json` | 16 video files on disk, 16 harvested, **0 unharvested** |
| 37,211 frames sampled | sum of per-video `frames_index.jsonl` rows, each cross-checked against `meta.json` `duration_sec` | 37,211 ✓ (two videos 1 s under their rounded duration, inside A1's ±2) |
| 10,120 states | sum of per-video `states.jsonl` rows | 10,120 ✓, per-video table in §3 matches line for line |
| 10,120 keyframes | files on disk vs `source_frame` referenced | 10,120 on disk, **0 orphans, 0 missing** |
| live sessions 51 % | 665 + 1,250 + 1,432 + 1,792 | 5,139 = 50.8 % ✓ |
| `harvest_report.json` | vs the above | 16/16 done, 37,211 / 10,120, ratio 3.68 ✓ |
| FINE_FRAC sweep table (§2) | recomputed from `calibration_31.json` | every cell matches ✓ |
| A3 keyframe is really the slide | opened `sss/keyframes_v2/0031_003700.jpg` by eye | 1920×1080, clean, and its text is verbatim what `red-day-definition` quotes ✓ |

**The §2 v1 table cannot be reproduced exactly** — the v1 artefacts are gone and the gray cache
resolution changed with the fix (72×64 → 288×160), so a like-for-like re-run is not available. Re-run
at the *current* resolution with the fine criterion disabled (`FINE_FRAC = 1.0`, i.e. dHash only):

| video | v1 content changes inside a state (note) | re-measured, dHash-only | with the fix |
|---|---|---|---|
| `concept_simple_stoic_setups_sss` | 7 | 7 | **0** |
| `concept_htf_stoic_trader_protocol` | 214 | 224 | **0** |
| `cs_vol1_stoic_edge_in_action_case_studies` | 208 | 203 | **1** |

The small drift is the resolution change; the claim the fix rests on — dHash alone leaves 200+
content changes buried inside states, two-criterion clustering leaves ~0 — reproduces independently.

**One correction found while checking A3.** The `First Red/Green Day` slide (`sss#0031`) is
text-only. The Jan 26–30 daily chart that the case-study note said was "on screen at the slide" is
in the *preceding* state `sss#0030` ("Wednesday → Thursday Reversal A+ Setup", 00:33:56–00:35:04);
the *following* state `sss#0032` ("Three Closes Reversal") shows a December example. Corrected in
`docs/notes/2026-07-25-case-study-fixture-track.md` §4a. The canonical fixture is unaffected — it
was verified against our own bars, not read off a chart.
