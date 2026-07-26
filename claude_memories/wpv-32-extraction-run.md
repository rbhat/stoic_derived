---
name: wpv-32-extraction-run
description: "WP-V §3.2 VLM extraction — how to check on the run, resume it, and sanity-check it; the measured rates that replace the plan's 16.9 h estimate, and the axis-furniture decision"
metadata:
  type: project
---

`edu/pipeline/visual_extract.py` runs the §3.2 VLM pass over the 10,120 audited visual states from
[[visual-harvest-31-status]]. Built 2026-07-26. Three stages per video, each resumable:
`extract` (one VLM call per state → `visual_records.jsonl`) → `crosscheck` (deterministic, levels vs
daily bars → `chart_checks.jsonl`) → `report` (counts → `extract_report.json`).

## The only two commands worth remembering

**`scripts/extract.sh` is the single entry point.** It wraps everything else; the underlying
commands should not be invoked directly.

```bash
scripts/extract.sh            # start it, or report the pid + log if already running
scripts/extract.sh --status   # where it is up to (safe while live)
scripts/extract.sh --stop     # stop it, e.g. the laptop is hot
```

Any other argument is forwarded to `visual_extract.py`, so `--list`, `--dry-run` and `--remaining`
work through it too. `--stop` kills the supervisor *before* the extractor, since the other order
lets the supervisor observe the death and start a replacement.

`scripts/job_status.sh <pid>` also works if you have the pid. **Never launch a second copy** —
see [[check-dont-relaunch-detached-jobs]]. Both `extract.sh` and `launch_bg.sh` refuse if the job
is already live.

**The user kills this job when the laptop runs hot.** That is expected and safe. It does not
restart itself; re-running the command above resumes it. **No LaunchAgent** — the user's explicit
decision, 2026-07-26. Nothing auto-starts on this machine.

## Durability contract

Re-running after a kill, a crash, a power cut or an LM Studio restart is always correct and always
cheap. Verified by hard-killing a live run mid-state and confirming the resume count matched
completed work exactly.

- Every record is **appended + fsynced immediately**, so a power cut loses at most one state.
- Resume is **per state**, not per video or per stage: `ok` records are skipped, `error` records
  are retried up to 3 cumulative attempts, and the stage is re-entered if `visual_records.jsonl`
  does not cover every state — gating on disk, not on a status flag.
- `extract_progress.json` is rewritten *during* a video (every 25 states), so a crash inside the
  1,792-state `live_4_3r_on_cl` still leaves a readable corpus-level checkpoint.
- `scripts/wpv32_run.sh` supervises: it **waits** for LM Studio rather than failing when it is
  absent (a booted machine is up long before LM Studio is), retries a crashed video, exits when
  the corpus is complete, and gives up after 10 attempts that extract nothing — progress measured
  in states, never in exit codes.
- A dead LM Studio raises `ServerDown` and **aborts the whole run**, rather than marching through
  the corpus laying down error records that only mean "the server was off".
- Thermal duty cycle: 90 s idle every 300 s of work. Costs ~+30 % wall time and is included in the
  ETA. Tune with `STOIC_COOL_FOR` / `STOIC_COOL_EVERY` in the environment.

## Measured rates — these replace the plan's 16.9 h

The plan's `6 s/state → 16.9 h` was never measured. Measured on the 53-state SSS video:
**slides 9.8 s/state, charts 23.2 s/state.** Charts cost 2–3× because output tokens dominate.
Live sessions are 5,139 near-all-chart states. Realistic total: **≈ 50–75 h** including cooling.

**Scope decision, user's call 2026-07-26: extract the FULL corpus, live sessions included.**
"Make sure all the info is covered including live sessions." The retrain plan's option of cutting
the 5,139 live states as a time lever is therefore **closed** — do not propose it again without
being asked. Video order is still `concept_* → cs_* → live_*` so the rule-dense material lands
first, but the run is not finished until all 16 videos are done.

## The axis-furniture decision (2026-07-26, user's call)

Chart frames were transcribing every price-axis and time-axis tick — 113 lines / 75 s on one dual
chart, ~94 % of it furniture. The user chose to **exclude repeating axis ladders from `ocr_text`**,
keeping every title, rule statement, chart header, drawn label and called-out price. This is a
deliberate deviation from the plan's literal "every text element, verbatim". Enforced twice:
in the prompt, and by a deterministic post-filter (`_strip_axis_ladders`, runs of ≥4 consecutive
bare prices or clock times) because measured model compliance was only ~50 %. When the filter
fires, the record keeps `ocr_text_raw` and `axis_lines_stripped`, so nothing is lost.

Every record carries `prompt_sha`. **Two shas in one corpus means two different definitions of
`ocr_text`** — `--status` and the reports flag it. Never blend them; re-extract instead.

## What the first results say

- **`ocr_text` is good.** The First Red/Green Day slide (`concept_simple_stoic_setups_sss#0031`)
  came back verbatim, matching hand-typed ground truth. This is the objective — see
  [[slide-text-not-in-transcripts]].
- **`drawn_levels` is not.** 21 NQ proposals, **zero** tick-exact matches against daily bars, and
  PDH/PDC given identical prices on two frames. The crosscheck caught it, which is its job. Treat
  levels as advisory; the rulebook value is in `ocr_text`. Consistent with the standing rule that
  chart numbers are proposals and `.artifacts/research/bars/` is ground truth — see
  [[bars-match-education-not-tradingview]] and [[audit-derived-numbers]].

## The 2–3 hour sanity check

Not a gate — counts, per [[signal-fidelity-over-edge-revalidation]] and ADR-0021. Look for:

1. `--status` — is `done_states` advancing, and does the ETA look sane?
2. **One prompt_sha only.** More than one means a mixed corpus.
3. **Error rate.** Any video showing `N err` is worth reading; a `ServerDown` abort is in the log.
4. **`unreadable_line_rate`** across `extract_report.json` — a climbing rate means the model is
   degrading, and that is a reason to stop, per §6 of the retrain plan.
5. **Spot-read 2–3 records against their JPEGs** — the harvest's own `label`/`why` fields were
   demonstrably hallucinated, which is exactly why this pass exists. Do not trust OCR unaudited.
6. **`axis_lines_stripped`** — if it fires on nearly every chart frame, model compliance dropped
   and the runtime estimate needs redoing.

Next after extraction: §3.3 audit gate, then rebuild `edu/derived/dataset.jsonl`, then Stage C on
WSL. Full chain in `docs/notes/2026-07-26-slm-retrain-plan.md`.
