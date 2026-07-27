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
| **A** §3.2 VLM extraction, 10,120 states | **Mac** | `Qwen3-VL-30B-A3B-Instruct-MLX-8bit` needs ~31 GB | ≈ 48 h **measured over 805 states**, see §2 |
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
- Model: `qwen3-vl-30b-a3b-instruct-mlx` (`Qwen3-VL-30B-A3B-Instruct-MLX-8bit`, ~31 GB) via LM
  Studio at `http://localhost:1234/v1`. **Confirm it is loaded before launching** — a multi-day
  run is a long time to discover a connection refusal.
- **`ocr_text` is verbatim.** No paraphrase, no completion. Unreadable lines are marked
  `unreadable`, never guessed. Interpretation goes in separate fields.
- Chart numbers are **proposals**, checked against `.artifacts/research/bars/`, never ground truth.
- Every record cites `video` + `t_start`. Uncited claims are dropped.
- **Resumable per state**, elapsed/ETA per video, same three-stage pattern as `visual_harvest.py`.
  Restarting must re-do only what is missing.

`scripts/extract.sh` is the single entry point — re-run it to resume after anything (a kill for
heat, a power cut, an LM Studio restart):

```bash
scripts/extract.sh            # start, or report the pid + log if already running
scripts/extract.sh --status   # where it is up to (safe while live)
scripts/extract.sh --stop     # stop it
```

It detaches via `launch_bg.sh`, holds `caffeinate` for exactly as long as the job lives, prints the
pid, and supervises through LM Studio restarts. Resume is per state, so re-running is always safe
and only redoes what is genuinely missing.

### Budget — MEASURED 2026-07-26, superseding the 16.9 h estimate

The 16.9 h figure was `10,120 × 6 s/state`, and the 6 s was never measured. Measured on the
53-state `concept_simple_stoic_setups_sss` run:

| frame kind | n | s/state |
|---|---|---|
| slide | 38 | 9.8 |
| chart | 15 | 23.2 |

Chart frames cost 2–3× because output tokens dominate, and the live sessions are 5,139 near-all-chart
states. Realistic total **including the +30 % thermal duty cycle** (90 s idle per 300 s of work,
added at the user's request): **≈ 50–75 h for the full corpus.** This 53-state calibration figure
was itself superseded the same day by a direct measurement over 805 states from the actual run
(chart median 13.3 s, not 23.2 s) plus the second thermal tier added later — see
`claude_memories/wpv-32-extraction-ops.md`, ETA **≈ 48 h**. Use that figure, not this one.

**Scope decision, user's call 2026-07-26: extract everything, live sessions included** — "make sure
all the info is covered including live sessions". §2's suggestion of cutting the 5,139 live states
as a time lever is therefore **withdrawn**. Processing order remains `concept_* → cs_* → live_*` so
the rule-dense material lands first, but the pass is not complete until all 16 videos are.

### The axis-furniture deviation (user's decision, 2026-07-26)

Chart frames were transcribing every price-axis and time-axis tick — 113 lines / 75 s on one dual
chart, ~94 % of it furniture that answers no rulebook question. The user chose to **exclude
repeating axis ladders from `ocr_text`**, keeping titles, rule statements, chart headers, drawn
labels and called-out prices. This is a deliberate departure from §3.2's literal "every text
element, verbatim", recorded as a decision, not a measurement. It is enforced twice — in the prompt
and by a deterministic post-filter — because measured model compliance was only ~50 %; when the
filter fires the record retains `ocr_text_raw` and `axis_lines_stripped`, so nothing is lost.

Every record carries a `prompt_sha`. Two shas in one corpus means two different definitions of
`ocr_text`; `--status` and the reports flag it rather than silently blending them.

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
