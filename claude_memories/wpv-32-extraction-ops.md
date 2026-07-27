---
name: wpv-32-extraction-ops
description: "WP-V §3.2 VLM extraction — HOW TO RUN IT: the commands, the durability contract, the thermal cycle, the four constants that move together, and the 2–3 h sanity check. Findings live in wpv-32-extraction-findings."
metadata:
  type: project
---

**This memory is how to *operate* the job. What its output *says* is [[wpv-32-extraction-findings]].**

> **Before you write any check against `chart.drawn_levels`: don't.** Two have been built and
> retired; the disagreements are the instructor live-editing a TradingView chart, not model error.
> The full argument and the JPEG evidence are in [[wpv-32-extraction-findings]] § "STOP AUDITING
> `drawn_levels`". This banner is duplicated deliberately — it has been rediscovered the hard way
> twice.

`edu/pipeline/visual_extract.py` runs the §3.2 VLM pass over the 10,120 audited visual states from
[[visual-harvest-31-status]]. Built 2026-07-26. Three stages per video, each resumable:
`extract` (one VLM call per state → `visual_records.jsonl`) → `crosscheck` (deterministic, levels vs
daily bars → `chart_checks.jsonl`) → `report` (counts → `extract_report.json`).

Live status is in `docs/STATE.md`, not here — this file goes stale on status by design.

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

**`--status`'s ETA is not a corpus ETA.** It is built only from states extracted *this run* —
correct, since already-done work is in neither numerator nor denominator — so a restart landing in
a dense stretch prints a wild number. Bracket against the measured rates below instead.

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

**The `MAX_ATTEMPTS` worry is not a live risk — resolved 2026-07-27.** The concern was that the
video-stage `attempts` counter reached 3 on the first concept videos purely from repeated restarts.
It does not bite: the give-up branch (`visual_extract.py:1399`) requires status `failed` **and**
attempts >= 3, and a killed run leaves the stage `running` (reclaimed immediately by pid liveness)
or `done` — never `failed`, which is set only on an exception. Demonstrated in practice:
`concept_htf_stoic_trader_protocol` finished 530/530 with `attempts: 6`. It would take **three
genuine exceptions on one stage** to skip a video.

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

### It came back at 6000, and the cap was never the fix

Raising the ceiling to 6000 did **not** fix those frames — states 180–183 errored again with
`prompt 895 + completion 5999`. Probing the frame showed why: the model transcribes the *visible*
ladder (0.71940 down to 0.69520) and then **keeps extrapolating the arithmetic sequence past the
bottom of the image** — 0.66, 0.62, … 0.57460, numbers that are nowhere on the chart. It is a
**decode loop, so it does not terminate**; no `VLM_MAX_TOKENS` bounds it, and each attempt burns
361 s to hit the wall. Prompt RULE 1 already forbids exactly this in as many words and the model
ignores it here, so the prompt is not the lever either.

**The lever is `maxLength` on the `ocr_text` string in `RECORD_SCHEMA`** (`OCR_TEXT_MAX_CHARS`,
3000). LM Studio enforces it **in the structured-output grammar**, not by asking the model to
cooperate: the string is force-closed at the cap and generation continues into the remaining
fields. That is the whole point — `chart.drawn_levels` and `chart.annotations` come *after*
`ocr_text`, and on these frames they are where the real content is (PDH / PDC / PDL /
"Monday Close"). Verified on `0180_002503.jpg`: `finish_reason` `stop`, record parses, chart block
recovered. A lost state becomes a recorded one.

- **3000 is ~5× the largest legitimate `ocr_text` measured** (574 chars over 805 records), and
  verified non-binding: re-running healthy frame `#0051` with the cap reproduced its stored record
  byte for byte.
- **It does not split the corpus.** `prompt_sha` hashes the prompt text, which is untouched
  (`3eccf9049745`), and the cap cannot bind on anything already extracted.
- **When it binds, the record says so** — `ocr_text_capped: true` plus `ocr_text_raw`. Usually that
  is the decode loop being cut off and costs nothing, but a genuinely text-dense slide could land
  there too, and §3.3 must be able to tell them apart by inspection.
- **A truncation is never retried.** `TruncatedResponse` breaks out of the retry loop, because at
  `temperature: 0` attempts 2 and 3 regenerate the same tokens and hit the same wall — that is what
  turned one 361 s loss into ~18 min per state.

**Confirmed in production 2026-07-26 20:40 PDT.** The five AUD/USD states 180–184 that had failed
since the beginning came back **5/5 `ok`, `attempts: 1`**, each `ocr_text_capped: true`,
`axis_lines_stripped` 368, `ocr_text` the title and chart header only, `chart` block populated —
exactly what the probe predicted. **~77 s each, against the ~18 min per state they were burning**
(3 × 361 s of identical retries).

What this does **not** recover is `ocr_text` itself on a looping frame: the ladder is emitted before
the model reaches the drawn labels, so the cleaned text keeps only the title and chart header. The
labels survive as `annotations`, which are descriptive, not verbatim. Treat those frames as
partially transcribed — and see [[wpv-33-ocr-gate]] for what Stage B must read instead.

### The four constants move together

Sized against wall-clock rather than tokens (the model is local, so tokens are free, but time is
not). **Changing one without the others reintroduces the failure in a new place.**

| constant | value | why |
|---|---|---|
| `OCR_TEXT_MAX_CHARS` | 3000 | grammar-enforced circuit breaker on the decode loop; ~5× the largest legitimate `ocr_text` (574 chars) |
| `VLM_MAX_TOKENS` | 6000 | ~20× the largest legitimate output (~300 tok); reachable in 361 s at the measured 16.6 tok/s |
| `VLM_CONTEXT_LENGTH` | 32768 | supervisor reloads LM Studio to this |
| `VLM_TIMEOUT` | 600 | must exceed `VLM_MAX_TOKENS` / rate, or the cap is unreachable and the real failure becomes a read timeout |
| `STALL_SECONDS` | 2400 | must exceed `VLM_RETRIES * VLM_TIMEOUT + COOL_FOR` = 1890 |

A truncation now reports itself as a truncation, with both token counts, so the next occurrence
does not send anyone down the schema path again.

## The axis-furniture decision (2026-07-26, user's call) and `prompt_sha`

Chart frames were transcribing every price-axis and time-axis tick — 113 lines / 75 s on one dual
chart, ~94 % of it furniture. The user chose to **exclude repeating axis ladders from `ocr_text`**,
keeping every title, rule statement, chart header, drawn label and called-out price. This is a
deliberate deviation from the plan's literal "every text element, verbatim". Enforced twice:
in the prompt, and by a deterministic post-filter (`_strip_axis_ladders`, runs of ≥4 consecutive
bare prices or clock times) because measured model compliance was only ~50 %. When the filter
fires, the record keeps `ocr_text_raw` and `axis_lines_stripped`, so nothing is lost.

Known gap: `_strip_axis_ladders` misses a date/time axis emitted as **one long line**, because it
matches runs of ≥4 *lines*. Cosmetic, repairable offline against stored records.

Every record carries `prompt_sha`. **Two shas in one corpus means two different definitions of
`ocr_text`** — `--status` and the reports flag it. Never blend them; re-extract instead.
`prompt_sha` hashes the prompt text only, so changing token or context constants does **not** split
the corpus.

## Measured rates

The plan's `6 s/state → 16.9 h` was never measured. Measured over 805 records:
**chart frames median 13.3 s, p90 15.6 s, max 71.2 s** (n=535); output ~16.6 tok/s. Slides are
faster. Per-video mean `elapsed_sec` at the 862-record mark:

| video | n | median | mean | capped |
|---|---|---|---|---|
| `concept_candle_swing_theory_pdh_pdl_pdc` (done) | 599 | 11.9 s | 12.9 s | 0 |
| `concept_htf_stoic_trader_protocol` | 237 | 13.5 s | 18.3 s | 28 |
| `concept_simple_stoic_setups_sss` | 19 | 8.6 s | 8.7 s | 0 |
| `concept_stoic_edge_system_module_1_is_live` | 7 | 8.1 s | 8.3 s | 0 |

**A dense stretch is content, not degradation.** 57 states of `htf_stoic_trader_protocol`'s
dual-chart section ran **40.7 s/state wall** — 28 of 57 hit `ocr_text_capped`, capped median 43.9 s
against uncapped 26.6 s. That is the grammar cap working as designed on the densest material in the
corpus. Idle was 18 % of wall in that window.

So the honest corpus figure is a **bracket, not a number**, because the remaining mix has no
measured rate yet:

| rate basis | to end of `cs_vol7` | full corpus |
|---|---|---|
| dense stretch, 40.7 s | ~47 h | ~105 h |
| corpus mean + designed 1:6+1:6 duty, 21.7 s | ~25 h | ~56 h |
| corpus mean + observed 18 % idle, 17.4 s | ~20 h | ~45 h |

Any "~37 h revised / ~16.5 h to cs_vol7" figure predates this and is **not supported by measured
rates**. Quote the bracket.

**Scope decision, user's call 2026-07-26: extract the FULL corpus, live sessions included.**
"Make sure all the info is covered including live sessions." The retrain plan's option of cutting
the 5,139 live states as a time lever is therefore **closed** — do not propose it again without
being asked. Video order is `concept_* → cs_* → live_*` so the rule-dense material lands first,
but the run is not finished until all 16 videos are done.

## The 2–3 hour sanity check

Not a gate — counts, per [[signal-fidelity-over-edge-revalidation]] and ADR-0021. Look for:

1. `--status` — is `done_states` advancing? **Confirm the process is actually alive**; a stopped job
   still reports its last counts perfectly happily. Ignore its ETA (see above).
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

Next after extraction: the §3.3 audit gate ([[wpv-33-ocr-gate]]), then rebuild
`edu/derived/dataset.jsonl`, then Stage C on WSL. Full chain in
`docs/notes/2026-07-26-slm-retrain-plan.md`.
