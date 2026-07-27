---
name: wpv-32-extraction-run
description: "WP-V §3.2 VLM extraction — how to check on the run, resume it, and sanity-check it; the measured rates, the token/context trap that ate dense chart frames, the thermal cycle, and the axis-furniture decision"
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

Bare `scripts/launch_bg.sh` does the same as bare `extract.sh` (it forwards, so the default job is
defined in one place), and `launch_bg.sh --status` forwards too. Both print the launch time in
**Pacific** and an elapsed `running 2h47m`, which is wall time and so includes the thermal pauses —
the right thing to compare against the ETA, which includes them too.

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
- **Stage ownership is decided by pid liveness, not by heartbeat age** (changed 2026-07-26). Each
  `running` entry records the owning `pid` and `host`; if that pid is gone, the stage is reclaimed
  immediately. `STALL_SECONDS` (2400) survives only as a fallback for what liveness cannot answer —
  no pid recorded, or a run that died on another host. Before this, a killed run's marker blocked
  its own videos until the timer expired, and an immediate restart silently skipped them.
- `extract_progress.json` is rewritten *during* a video (every 25 states), so a crash inside the
  1,792-state `live_4_3r_on_cl` still leaves a readable corpus-level checkpoint.
- `scripts/wpv32_run.sh` supervises: it **waits** for LM Studio rather than failing when it is
  absent, **reloads the model at `VLM_CONTEXT_LENGTH` if it finds it loaded smaller**, retries a
  crashed video, exits when the corpus is complete, and gives up after 10 attempts that extract
  nothing — progress measured in states, never in exit codes.
- A dead LM Studio raises `ServerDown` and **aborts the whole run**, rather than marching through
  the corpus laying down error records that only mean "the server was off".

## Thermal cycle — two tiers

- Short: **90 s idle every 300 s** of work (`STOIC_COOL_FOR` / `STOIC_COOL_EVERY`).
- Long: **15 min idle every 90 min** of work (`STOIC_REST_FOR` / `STOIC_REST_EVERY`), added
  2026-07-26 because the short pause is too brief to shed heat soaked into the chassis over a
  multi-day run. First cut was 20 m every 2 h; shortened at the user's request when the machine was
  still hot. **Note the duty ratio is 1:6 either way** — what changed is how long heat accumulates
  before it is shed, not how much idle there is. If it is still hot, the lever is a longer
  `STOIC_REST_FOR` or a shorter `STOIC_COOL_EVERY`.

Pauses are taken between states so they never interrupt a request, the heartbeat is beaten
throughout an idle, and idle time stays **inside** the throughput measurement — the ETA has to
predict when the job finishes, not how fast it would run if it never rested.

## The token/context trap — read this before diagnosing any parse error

Five states on one AUD/USD dual chart (00:25:03–05 of `concept_htf_stoic_trader_protocol`) failed
with `response did not parse as the required schema`. **The schema was not the problem.** The frame
carries two full price-axis ladders, the model transcribed them, the response hit `max_tokens`
mid-string, and under a strict `json_schema` a truncated response is unparseable — so the state was
*lost*, not merely verbose. `_strip_axis_ladders` cannot help: it is a **post-parse** filter and
never sees a response that died before parsing.

The binding limit was not `max_tokens` either. **LM Studio had the model loaded at 4096 context
against a 262144 maximum**, and prompt + one 1920×1080 keyframe measures **895 tokens**, leaving
~3.2k. Raising the cap alone would have moved the truncation, not removed it. Always check
`~/.lmstudio/bin/lms ps --json` → `contextLength` before believing a token number.

Current constants, sized against wall-clock rather than tokens (the model is local, so tokens are
free, but time is not):

| constant | value | why |
|---|---|---|
| `VLM_MAX_TOKENS` | 6000 | ~20× the largest legitimate output (~300 tok); reachable in 361 s at the measured 16.6 tok/s |
| `VLM_CONTEXT_LENGTH` | 32768 | supervisor reloads LM Studio to this |
| `VLM_TIMEOUT` | 600 | must exceed `VLM_MAX_TOKENS` / rate, or the cap is unreachable and the real failure becomes a read timeout |
| `STALL_SECONDS` | 2400 | must exceed `VLM_RETRIES * VLM_TIMEOUT + COOL_FOR` = 1890 |

**These four move together** — changing one without the others reintroduces the failure in a new
place. A truncation now reports itself as a truncation, with both token counts, so the next
occurrence does not send anyone down the schema path again.

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
`prompt_sha` hashes the prompt text only, so changing token or context constants does **not** split
the corpus.

## Measured rates

The plan's `6 s/state → 16.9 h` was never measured. Measured over 805 records:
**chart frames median 13.3 s, p90 15.6 s, max 71.2 s** (n=535); output ~16.6 tok/s. Slides are
faster. Corpus ETA settles around **48 h** including both thermal tiers.

**Scope decision, user's call 2026-07-26: extract the FULL corpus, live sessions included.**
"Make sure all the info is covered including live sessions." The retrain plan's option of cutting
the 5,139 live states as a time lever is therefore **closed** — do not propose it again without
being asked. Video order is `concept_* → cs_* → live_*` so the rule-dense material lands first,
but the run is not finished until all 16 videos are done.

## What the results say so far

- **`ocr_text` is good.** The First Red/Green Day slide (`concept_simple_stoic_setups_sss#0031`)
  and the THREE-DAY CYCLE slide (`concept_htf_stoic_trader_protocol#0018`) both came back verbatim
  against their JPEGs. This is the objective — see [[slide-text-not-in-transcripts]].
- **`drawn_levels` is not.** Zero tick-exact matches on an early NQ batch, and on the Gold frame
  `#0025` the Previous Month Lowest Close came back `4,689.9` where the chart reads **4,680.9** — a
  digit transposition, while every other field on that frame was exact. Treat levels as advisory;
  the rulebook value is in `ocr_text`. Consistent with [[bars-match-education-not-tradingview]] and
  [[audit-derived-numbers]].
- **Frame classification is loose at the edges** — intro animation frames come back
  `chart_annotated` with `ocr_confidence: high` over scattered glyphs. The OCR is faithful to what
  is on screen; the label and the confidence are not.

## State as of 2026-07-26 ~19:00 PDT

805/10120 (8.0 %), **805 ok / 0 errors**, one `prompt_sha`, `unreadable_line_rate` 0.0000,
`axis_lines_stripped` 30. `concept_candle_swing_theory_pdh_pdl_pdc` complete (599/599). Run is
**stopped** (user needed the laptop); max `state_id` on disk for `concept_htf_stoic_trader_protocol`
is 179.

**Still unverified:** the five deleted AUD/USD states 180–184 of `concept_htf_stoic_trader_protocol`
have not been re-extracted. They are the first test of the truncation fix — check them.

**Latent issue, do not fix without asking:** the video-stage `attempts` counter on the first three
concept videos reached `MAX_ATTEMPTS` (3) purely from repeated restarts, not from real failures. If
one of those stages ever ends in status `failed`, the driver logs "giving up on this video" and
skips it permanently. No stage is `failed` today.

## The 2–3 hour sanity check

Not a gate — counts, per [[signal-fidelity-over-edge-revalidation]] and ADR-0021. Look for:

1. `--status` — is `done_states` advancing, and does the ETA look sane? **Confirm the process is
   actually alive**; a stopped job still reports its last counts perfectly happily.
2. **One prompt_sha only.** More than one means a mixed corpus.
3. **Error rate.** Any video showing `N err` is worth reading. A truncation now names itself; do
   not diagnose it as a schema problem.
4. **`unreadable_line_rate`** across `extract_report.json` — a climbing rate means the model is
   degrading, and that is a reason to stop, per §6 of the retrain plan.
5. **Spot-read 2–3 records against their JPEGs** — the harvest's own `label`/`why` fields were
   demonstrably hallucinated, which is exactly why this pass exists. Do not trust OCR unaudited.
6. **`axis_lines_stripped`** — a high strip rate is now the *expected healthy* outcome on dense
   chart frames, because stripping is what those frames do instead of erroring.
7. **LM Studio still at 32768** (`lms ps --json`), and the chart `elapsed_sec` distribution still
   near the 13.3 s median — a large jump would mean the bigger cap is letting axis ladders through.

Next after extraction: §3.3 audit gate, then rebuild `edu/derived/dataset.jsonl`, then Stage C on
WSL. Full chain in `docs/notes/2026-07-26-slm-retrain-plan.md`.
