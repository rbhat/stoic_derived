# SLM retrain — the explicit plan

**Date:** 2026-07-26 · **Status:** decided, not started · **Decided by:** the user, this session
**Depends on:** `docs/notes/2026-07-26-wpv-visual-harvest-progress.md` (§3.1, all HARD checks green)

The user's call, 2026-07-26: **"we need to redo the SLM."** This is a strategy decision under
ADR-0004, recorded as a decision, not a measurement. This note is the durable spec for executing it.

---

## 0. Why the old "do not retrain" verdict does not bind

That verdict (`docs/notes/2026-07-25-slm-eval-learnings-and-gap-to-goal.md`) was measured against a
corpus that **did not contain the on-screen material**. Slides carry the rule definitions and no
transcript contains them — the First Red/Green Day sequence is the proof case. A model cannot learn
what was never in its training data, so a result on that corpus says nothing about a corpus that
now includes it.

What has changed since: WP-V §3.1 landed **10,120 distinct visual states** with full-resolution
keyframes and a green audit gate. §3.2 turns those into text. That text is the new training signal.

The objective is unchanged and is **not** a benchmark score: (a) resolve the 12
`unresolved_decisions` in `strategy/rulebook.yaml` from the material with evidence citations, and
(b) turn `edu/derived/` into fixtures a signal generator can be validated against. Judge the retrain
by whether it serves those two.

## 1. The chain, and why it spans two machines

| stage | machine | why | wall time |
|---|---|---|---|
| **A** §3.2 VLM extraction, 10,120 states | **Mac** | `qwen3-vl-30b-a3b-instruct-mlx` needs ~17 GB even at 4-bit | ≈ 16.9 h @ 6 s/state |
| **B** §3.3 audit gate + rebuild `edu/derived/dataset.jsonl` | Mac | cheap, deterministic | minutes |
| **C** eval delta → QLoRA retrain → eval | **WSL / RTX 5070 Ti** | CUDA, and the training package already lives there | hours |

**The split is forced, not a preference.** The Windows box is a **16 GB** card
(`docs/superpowers/specs/2026-07-24-win-cuda-training-package-plan.md:42`). A 30B-A3B VL model does
not fit it. Running the extraction there would mean a materially smaller extractor on the one pass
this entire work package exists to get right — rejected.

Consequence to plan around: **Stage C cannot start until Stage A finishes and is pushed.** Nothing
on Windows is runnable before that.

## 2. Stage A — §3.2 VLM extraction (Mac)

Build `edu/pipeline/visual_extract.py`. Spec is `2026-07-26-exhaustive-visual-extraction-plan.md`
§3.2; it is unchanged and binding. Restating only what execution needs:

- Input: `.artifacts/research/visual/<video>/states.jsonl` + `keyframes_v2/*.jpg` (both audited).
- Output: `.artifacts/research/visual/<video>/visual_records.jsonl`, one record per state, schema in
  the plan §3.2.
- Model: `qwen3-vl-30b-a3b-instruct-mlx` via LM Studio at `http://localhost:1234/v1`.
  **Confirm it is loaded before launching** — 17 h is a long time to discover a connection refusal.
- **`ocr_text` is verbatim.** No paraphrase, no completion. Unreadable lines are marked
  `unreadable`, never guessed. Interpretation goes in separate fields.
- Chart numbers are **proposals**, checked against `.artifacts/research/bars/`, never ground truth.
- Every record cites `video` + `t_start`. Uncited claims are dropped.
- **Resumable per state**, elapsed/ETA per video, same three-stage pattern as `visual_harvest.py`.
  Restarting must re-do only what is missing.

Launch:

```bash
scripts/launch_bg.sh wpv-32-extract -- .venv/bin/python edu/pipeline/visual_extract.py
```

That detaches it, holds `caffeinate` for exactly as long as the job lives, and prints the pid.

**Budget ≈ 16.9 h**, not the ~12 h older notes quote — that figure came from the calibration's
*extrapolated* 7,249 states; the measured corpus is 10,120. The 5,139 live-session states are 8.6 h
of it and are the lever if that needs cutting.

## 3. Stage B — audit gate, then the dataset

The §3.3 gate is **hard** and comes before the dataset rebuild:

1. 30 frames stratified by `frame_class`, human-checked for verbatim OCR accuracy.
2. Re-extract the four known slides (SSS 00:35:05–00:37:00 and the three
   `concept_htf_stoic_trader_protocol` template slides) and diff against hand-typed ground truth.
3. Report counts — frames by class, OCR confidence distribution, unreadable rate. **Counts, not
   verdicts.**

Then rebuild `edu/derived/dataset.jsonl` including the visual records, and **record the row-count
and per-video deltas against the current dataset**. That diff is the evidence that the retrain has
anything new to learn from; if it is small, say so before spending GPU hours.

Push after this. Stage C reads it from git.

## 4. Stage C — eval delta, then retrain (WSL)

Per the user's decision this session: **measure, then train regardless.** The eval delta is the
record of what changed, not a gate — nothing waits overnight for a human.

1. **Check nothing is already running.** `pgrep -af "venv/bin/python3 -m stoic_training"`, and
   `scripts/launch_bg.sh --list`. Two 8B models on one card is OOM and hours lost.
2. **Eval delta** on the new corpus against the existing fine-tune `adb3c96ab6020c23` and the
   instructed base — `cited_qa` and `rule_candidate`, counts only.
3. **QLoRA retrain** on the rebuilt dataset. Config `training/win_cuda/config/qlora.yaml`, same LoRA
   geometry as `adb3c96ab6020c23` (r=16 / α=32 / dropout 0.05, all seven attn+MLP projections)
   unless there is a stated reason to change it. **Non-thinking targets** — keep thinking OFF at
   inference or the eval will not reproduce.
4. **Eval the new run** and compare all three. Counts, disaggregated by task. ADR-0021 applies to
   every number.

Launch, once `chain_retrain.sh` exists:

```bash
scripts/launch_bg.sh slm-retrain -- training/win_cuda/scripts/chain_retrain.sh
```

### The CUDA venv traps — non-negotiable

- `export UV_PROJECT_ENVIRONMENT=<repo>/.artifacts/training/venv` before any `uv run`.
- `uv run` **must** have cwd `training/win_cuda`; the root `pyproject.toml` is 3.14 and destroys the
  3.12 CUDA venv.
- `uv run` **must not** run while a GPU job is live — it resyncs the venv. Prefer
  `.artifacts/training/venv/bin/python3 -m stoic_training.<cmd>` directly.
- `pgrep -f "stoic_training"` matches your own shell wrapper. Match `venv/bin/python3 -m stoic_training`.

## 5. Monitoring — the hand-off contract

Both stages launch through `scripts/launch_bg.sh`, which writes
`.artifacts/jobs/<name>/{pid,cmd,started_utc,latest.log}` and inhibits machine sleep (`caffeinate`
on the Mac; a Windows-side `SetThreadExecutionState` keeper on WSL, released automatically when the
job exits — `systemd-inhibit` would only hold the Linux side, which is not what sleeps).

Hand a later session **just the pid**:

```bash
scripts/job_status.sh <pid>
```

It resolves the pid to its job, reports RUNNING / STALLED / EXITED / CRASHED, shows GPU state where
there is one, and tails the log. Exit codes match `training/win_cuda/scripts/health.sh`:
**0** running or clean · **1** crashed · **2** stalled.

**STALLED is the one that matters** — process alive but nothing it writes has been touched for
25 min. A wedged CUDA job stays "alive" indefinitely. Treat a stalled job as something to diagnose,
never as permission to launch a second copy.

## 6. What would make this the wrong call

Recorded now so it is not rationalised later:

- The §3.3 audit shows OCR is unreliable (high `unreadable` rate, or the known-slide diffs fail).
  Then the fix is the extractor or the vision model, not a text retrain on bad text.
- The rebuilt dataset is barely different from the current one. Then there is nothing new to learn
  and the honest move is to say so.
- Neither of these is a reason to skip Stage A. Both are reasons to stop before Stage C.
