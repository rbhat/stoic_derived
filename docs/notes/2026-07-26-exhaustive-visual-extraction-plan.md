# Exhaustive visual extraction of the education corpus — plan

**Date:** 2026-07-26 · **Status:** planned, not started · **Supersedes:** nothing

This note is the durable spec for WP-V ("visual extraction"). It travels with the repo.

---

## 0. Why this exists

The `edu/derived/**/transcript.*` files capture **audio only**. A large part of the education is
delivered as **on-screen text** — slides, template lists, rule statements, chart annotations — and
none of it is in any searchable field today.

This was found the hard way on 2026-07-26. The definition of the First Red/Green Day setup is
stated on a slide in `concept_simple_stoic_setups_sss` held from **00:35:12 to ~00:35:57**:

```
First Red/Green Day  —  "The first crack in the wall"
  Day 1: Highest Close of the Month
  Day 2: Highest Close of the Month
  Day 3: Highest Close of the Month
  Day 4: First Red Day = CONFIRMATION
```

Searching every transcript in the corpus does not surface this, because it is never spoken. Two
sessions of chart-pixel measurement and transcript inference were spent circling a question that
one OCR pass would have answered outright.

Worse, the existing keyframe labels are **actively misleading**:

| frame | file | `label` | `why` |
|---|---|---|---|
| 106 (00:35:12) | `keyframes/0106_003512.jpg` | `First red day signal` | *"The chart shows the first daily close lower after an uptrend…"* |
| 107 (00:35:57) | `keyframes/0107_003557.jpg` | *(empty)* | *(empty)* |

Both frames are the **same text slide**. Frame 106's `why` describes a chart that is not on screen —
a hallucinated caption. Frame 107, the cleanest capture of the slide, carries no label at all.

**Therefore:** treat every existing `label` / `why` field as **unverified** until this pass replaces
it. ADR-0021 applies to VLM output exactly as it applies to derived numbers.

## 1. Objective

Extract **exhaustively** — do not sample, do not filter to "interesting" frames. Every distinct
visual state in all 16 videos becomes a searchable, citable record. If a frame could plausibly
carry a concept, an example, a rule, a level, or a label, it is in scope.

The output must be good enough that a future question like *"where is X defined?"* is answered by
`grep`, not by watching video.

## 2. Corpus

16 videos, **10.34 h** (37,214 s), all `.mp4` present on disk.

| group | videos | duration |
|---|---|---|
| `concept_*` | 5 | 04:44:11 |
| `cs_vol1..7` | 7 | 02:51:40 |
| `live_*` | 4 | 02:44:14 |

Existing: 2,233 keyframes on disk (1,526 with an LLM label, 707 with none). These are a *starting
set*, not the target — they were drift/gap sampled and demonstrably miss held slides.

## 3. Method

### 3.1 Frame harvest (deterministic, no model)

Sample at **1 fps** (37,214 frames), then collapse near-duplicates by perceptual hash (dHash,
Hamming ≤ 4) so held slides become one record with `t_start` / `t_end`. Expect roughly 3–6k
distinct visual states. Keep the full 1 fps index so nothing is silently dropped — dedupe is a
*view*, not a deletion.

Rationale for 1 fps over scene detection: scene-change thresholds are what produced the current
gap. Slides held for 45 s with a cursor moving over them defeat drift detection. Sampling first and
deduping after is the asymmetric-safe choice.

### 3.2 Classification + extraction (VLM)

Model: the Mac's **`qwen3-vl-30b-a3b-instruct-mlx`** (already used to produce `moments.json`).
Do **not** use the fine-tuned text SLM for this — it has no vision path.

Per distinct visual state, emit:

```jsonc
{
  "id": "concept_simple_stoic_setups_sss#0107",
  "video": "concept_simple_stoic_setups_sss",
  "t_start": 2112.0, "t_end": 2157.0, "hms_start": "00:35:12",
  "frame_class": "slide",        // slide | chart | chart_annotated | mixed | talking_head | other
  "ocr_text": "First Red/Green Day\nThe first crack in the wall\nDay 1: Highest Close of the Month\n…",
  "ocr_confidence": "high",      // high | partial | unreadable
  "chart": {                      // present only when frame_class involves a chart
    "instrument": "NQ", "timeframe": "1D",
    "drawn_levels": [{"label": "HCOM", "value": 25138.00}],
    "annotations": ["arrow down over 2026-03-05"]
  },
  "narration_window": "…±15 s of transcript text…",
  "source_frame": "keyframes_v2/0107_003512.jpg"
}
```

**Hard rules for the extractor:**

- `ocr_text` is **verbatim**. No paraphrase, no completion, no inference. If a line is unreadable,
  mark it `unreadable` rather than guessing.
- Interpretation goes in separate fields, never mixed into `ocr_text`.
- Numbers read off a chart are **proposals**, never ground truth — derive from
  `.artifacts/research/bars/` and use the frame as the check (existing convention, and it has held
  to the tick: HCOM 25,138.00, Feb HCOM 25,873.25, Feb LCOM 24,425.25).
- Every record cites `video` + `t_start`. A claim without a citation is dropped.

### 3.3 Audit gate (ADR-0021)

Before anything downstream consumes this:

1. Hold out **30 frames stratified by `frame_class`**; a human checks `ocr_text` verbatim-accuracy.
2. Re-extract the four known slides (SSS 35:12, and the three `concept_htf_stoic_trader_protocol`
   template slides) and diff against hand-typed ground truth.
3. Report **counts** — frames by class, OCR confidence distribution, unreadable rate. No verdicts.

Record the audit result in this note before proceeding to §4.

## 4. Retraining (conditional, user-directed)

The standing decision had been **not** to retrain (see
`docs/notes/2026-07-25-slm-eval-learnings-and-gap-to-goal.md` and §1 of the fixture-track note).
The user reopened this on 2026-07-26, conditioned on this extraction landing:

> "Once we re-extract the information, I think retraining would be useful - maybe it picks up
> more/better info?"

**This is a strategy decision, recorded, not a measurement.** The reasoning that justifies
revisiting it: the earlier "do not retrain" verdict was reached against a corpus that *did not
contain the on-screen material*. A model cannot learn what was never in its training data, so the
prior verdict does not bind a corpus that now includes it.

Sequence — do not reorder:

1. §3 lands and passes the §3.3 audit.
2. Rebuild `edu/derived/dataset.jsonl` including the new visual records.
3. **Measure the delta on the existing eval harness first** (`cited_qa`, `rule_candidate`) against
   the current fine-tune and the instructed base. Counts, not verdicts.
4. Only then decide on a training run. Training config, GPU package and traps are in
   `claude_memories/win-cuda-training-package.md`; the CUDA venv rule (cwd must be
   `training/win_cuda`) is non-negotiable.

## 5. Engineering constraints

- **Resumable + progress-tracked.** Both passes write a manifest and skip completed work on
  restart; log elapsed and ETA per video. (10 h of video and a 30B VLM is not a single sitting.)
- Artifacts under **`.artifacts/research/visual/`**; scratch under `.scratch/`. Never `~`, never
  another drive.
- `.venv` (3.14) for harvest/orchestration. The VLM runs via MLX on the Mac.
- `uvx ruff check --fix`, line length 100.
- Deterministic signal code must never call a model. This pass builds the *rulebook*; plain code
  makes the calls.

## 6. Out of scope

- Regenerating bars — `.artifacts/research/bars/` is rebuilt and verified (111 daily bars,
  2026-01-02..06-05).
- Any change to `strategy/rulebook.yaml`. Extraction proposes; the human confirms.
