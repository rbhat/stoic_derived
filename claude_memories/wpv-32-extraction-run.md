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

### It came back at 6000, and the cap was never the fix (2026-07-26, later)

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

What this does **not** recover is `ocr_text` itself on a looping frame: the ladder is emitted before
the model reaches the drawn labels, so the cleaned text keeps only the title and chart header. The
labels survive as `annotations`, which are descriptive, not verbatim. Treat those frames as
partially transcribed.

Current constants, sized against wall-clock rather than tokens (the model is local, so tokens are
free, but time is not):

| constant | value | why |
|---|---|---|
| `OCR_TEXT_MAX_CHARS` | 3000 | grammar-enforced circuit breaker on the decode loop; ~5× the largest legitimate `ocr_text` (574 chars) |
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
- **`drawn_levels` is mixed, and the "zero tick-exact matches" line was wrong.** That came from a
  small early batch. Measured over the **962 levels of the completed video** (all NQ, the one
  instrument with bars): **460 `ohlc_match` / 498 `in_range_no_match` / 4 `out_of_range`** — a
  47.8 % match rate. Against a coincidence baseline it is real signal, not noise: drawing prices
  uniformly over the span the levels themselves occupy hits some daily OHLC within 1 tick only
  **4.2 %** of the time (2.8 % over the full bars range), so 47.8 % is ~11× the null.
  `ohlc_match` still is not "correct" — a level may legitimately sit on a 15-minute swing the daily
  bars never touch, which is what `in_range_no_match` is for — but the field is carrying
  information and should not be written off.
- **Where it fails is levels with no printed price.** The Gold frame `#0025` transposed the
  Previous Month Lowest Close to `4,689.9` against a chart reading **4,680.9**, every other field
  exact. On the AUD/USD frames the PDH/PDC/PDL lines carry *no printed number at all*, and across
  five consecutive frames of the same chart the model returned three different values for PDH and
  three for PDL — it is estimating against the axis. **The rule is: a level whose price is printed
  is a reading; a level whose price is not printed is a guess.** The prompt already says to leave
  the latter out, and it does not obey. Levels stay advisory; the rulebook value is in `ocr_text`.
  Consistent with [[bars-match-education-not-tradingview]] and [[audit-derived-numbers]].
- **The label sorts the good from the junk, and it does it cleanly.** Splitting those same 962
  levels by what they are labelled:

  | label | n | `ohlc_match` | vs 4.2 % null |
  |---|---|---|---|
  | method term (`Previous Day High`, `Friday Close`, `PDC`, `PWL`, …) | 627 | **68.4 %** | 16× |
  | anything else (`M` 157, `Y` 52, `BWH`, `Swing Failure Pattern SFP`) | 281 | **5.7 %** | ~1× |
  | unlabelled | 54 | 27.8 % | 7× |

  The "other" bucket is indistinguishable from chance because most of it **is not a level at all** —
  `M` and `Y` are chart furniture, and `Swing Failure Pattern SFP` / `Break & Retest` are concepts
  misfiled into `drawn_levels`. So the field is not uniformly unreliable; it is two populations, and
  the label separates them deterministically, the same way `_strip_axis_ladders` separates furniture
  from content.

### The levels audit — BUILT 2026-07-26, `edu/pipeline/levels_audit.py`

Read-only, deterministic, safe against a live extraction, counts only. **Bars are secondary by
construction** (user's direction: if there are no bars we should not depend on them) — we hold daily
bars for NQ alone and the corpus is mostly AUD/USD, gold, GBP/JPY, RTY and BTC. Results on the first
833 records:

| check | needs bars | result |
|---|---|---|
| **0. collapse** — distinct method-term levels on one frame sharing a price | no | **110 / 363 frames (30.3 %)** |
| **1. self-consistency** — adjacent states, chart advances excluded | no | **104 / 272 labels (38.2 %)** moved while a neighbour held still, median **24.6 bp** |
| **2. label taxonomy** | no | 78.4 % method-term; the rest is `M` ×157, `Y` ×52, `Swing Failure Pattern SFP` |
| **3. nearest daily OHLC** | NQ only | method-term: 65.5 % within 1 tick, **95.9 % within 40 ticks, none beyond 200** |

**The naive version of check 1 was wrong** and its first run reported 23.2 % on evidence that proved
nothing: in a video teaching PDH/PDL the instructor steps the chart forward a day, so
`Previous Day High` genuinely changes between adjacent states. The discriminator is whether labels
move **together** — an advance moves all of them, a misread moves one and leaves its neighbour
alone. Deltas are in **basis points, not ticks**, because a tick is not the same thing on AUD/USD as
on NQ.

**Checks 0 and 3 look contradictory and are not.** Against bars the values are *near* misses — the
right neighbourhood, wrong by a few ticks. Against itself the model puts three different levels on
one price 30 % of the time. Both are what "estimating against the axis" predicts: it finds the
region and cannot resolve which line it is. **That makes the label usable and the value not.**

### Stage B — what the SLM should be trained on

The guide is the user's: the SLM exists so we can **derive a mathematical model for the Python
code**. Under that test `drawn_levels` values are worthless and the labels are valuable:

- **Do not train on the OCR'd price.** If a level is labelled `Previous Day High` and the frame's
  date is known, the value is **computable exactly from our own bars** — it never needed reading.
  Training on axis-estimated numbers teaches the SLM to emit precise-sounding prices it cannot read,
  and per ADR-0021 they would enter training un-audited.
- **Train on the semantics**: which levels the method draws, what they are called, which one a setup
  keys off. That is the specification Python turns into a rulebook, and it survives every failure
  above — 95.9 % within 40 ticks means the model reliably identifies *which line*, and identification
  is all the label needs to be right about.
- `ocr_text` is unaffected and remains where rule statements live.
- **Frame classification is loose at the edges** — intro animation frames come back
  `chart_annotated` with `ocr_confidence: high` over scattered glyphs. The OCR is faithful to what
  is on screen; the label and the confidence are not.

## State as of 2026-07-26 ~20:30 PDT

805/10120 (8.0 %), **805 ok / 0 errors**, one `prompt_sha` (`3eccf9049745`),
`unreadable_line_rate` 0.0000, `axis_lines_stripped` 30 records / 616 lines (max 39 on one frame —
bounded, and every one kept its levels, so the ok corpus shows no sign of the decode loop).
`concept_candle_swing_theory_pdh_pdl_pdc` complete (599/599). Run is **stopped**; max `state_id` on
disk for `concept_htf_stoic_trader_protocol` is 179.

The 19:44 restart re-ran the AUD/USD frames and **states 180–183 errored again** on the same
truncation — that run predates the `maxLength` fix. Those 4 error records were deleted, so the
counts above are all-ok.

**Resolved 2026-07-26 20:40 PDT.** The five AUD/USD states 180–184 that had failed since the
beginning came back **5/5 `ok`, `attempts: 1`**, each `ocr_text_capped: true`,
`axis_lines_stripped` 368, `ocr_text` the title and chart header only, `chart` block populated —
exactly what the probe predicted. **~77 s each, against the ~18 min per state they were burning**
(3 × 361 s of identical retries). Run restarted at 20:27 PDT, 810/10120, 0 errors.

**But audit their `chart.drawn_levels` before using them.** Across five consecutive frames of the
*same* chart, PDH came back 0.71840 / 0.71940 / 0.71920 / 0.71840 / 0.71940 and PDL
0.71180 / 0.71180 / 0.71120 / 0.71180 / 0.70340 — levels that must be identical are not, and none
of them has a price printed beside it on the chart, so the model is estimating against the axis
rather than reading a number. Same finding as the Gold `#0025` transposition above; the frames are
new, the weakness is not. Levels stay advisory. Note the real call-outs did survive on `#183`, but
in `annotations` (`2 @ 0.71255`, `2 @ 0.70835`) — prose, not verbatim, and `Monday Low` came back
0.70520 where the chart reads 0.69560.

**Latent issue, do not fix without asking:** the video-stage `attempts` counter on the first three
concept videos reached `MAX_ATTEMPTS` (3) purely from repeated restarts, not from real failures. If
one of those stages ever ends in status `failed`, the driver logs "giving up on this video" and
skips it permanently. No stage is `failed` today.

## State as of 2026-07-27 ~04:30Z (21:30 PDT) — sanity check #1 after the maxLength fix

Run alive, pid 26128 since 20:49 PDT. **862 records, 862 ok / 0 err**, one `prompt_sha`
(`3eccf9049745`), `unreadable_lines` 0 across the 57 states since restart, LM Studio confirmed at
`contextLength` 32768. All seven sanity-check items green.

**The rate is the news, and it is content, not degradation.** Per-video mean `elapsed_sec`:

| video | n | median | mean | capped |
|---|---|---|---|---|
| `concept_candle_swing_theory_pdh_pdl_pdc` (done) | 599 | 11.9 s | 12.9 s | 0 |
| `concept_htf_stoic_trader_protocol` (in progress) | 237 | 13.5 s | 18.3 s | 28 |
| `concept_simple_stoic_setups_sss` | 19 | 8.6 s | 8.7 s | 0 |
| `concept_stoic_edge_system_module_1_is_live` | 7 | 8.1 s | 8.3 s | 0 |

The 57 states since restart are all in `htf_stoic_trader_protocol`'s dual-chart section and run
**40.7 s/state wall** — **28 of 57 (49 %) hit `ocr_text_capped`**, capped median 43.9 s against
uncapped 26.6 s, and 50 of 57 stripped axis lines. That is the grammar cap working as designed on
the densest material in the corpus, not the model degrading. Idle was 18 % of wall in that window.

**Do not read `--status`'s ETA as a corpus ETA.** It is built only from states extracted *this run*
(correct — already-done work is in neither numerator nor denominator), so with 57 states all drawn
from the corpus's worst stretch it printed **108 h**. Bracketed against measured rates instead:

| rate basis | to end of `cs_vol7` (4,119 states) | full corpus (9,258 states) |
|---|---|---|
| current dense stretch, 40.7 s | 46.6 h | 104.7 h |
| corpus mean + designed 1:6+1:6 duty, 21.7 s | 24.8 h | 55.8 h |
| corpus mean + observed 18 % idle, 17.4 s | 19.9 h | 44.7 h |

**The earlier "~37 h revised / ~16.5 h to cs_vol7" figures are not supported by measured rates.**
The honest statement is a range, because the remaining mix (831 states of
`the_only_trading_video`, 2,858 of `cs_vol1-7`, 5,139 of `live_*`) has no measured rate yet. The
48 h corpus figure above still sits inside the bracket; the checkpoint is **20–47 h out, not 16.5**.

### Gold Fib spot-check — the axis-estimation failure, third instrument

State `#236` / `0236_003353.jpg` (`GC Jan 29th, 2026`, dual 1D + 5m) read against the JPEG:

- **`ocr_text` is right.** Title, both chart headers, `DAY1/DAY2/DAY3`, `Thursday`, `9:30`,
  `61.8%`, `50%`, `1.618`, `2`, `2.618`, `StoicEdge.com` — all verbatim. Wave numbers 1-5 are not
  in `ocr_text` but are in `annotations` ("numbered wave count from 1 to 5"), as documented.
- **`drawn_levels` values are wrong by 28–82 points, every one.** Chart reads 1.618 ≈ 5,380 /
  2 ≈ 5,352 / 2.618 ≈ 5,258 / 61.8 % ≈ 5,580 / 50 % ≈ 5,560; the model returned 5,420 / 5,380 /
  5,340 / 5,531 / 5,520. **None of these has a printed price on the chart.** Same finding as the
  Gold `#0025` transposition and the AUD/USD PDH/PDL spread — the rule holds on a third instrument.
- **It binds printed numbers to the wrong label.** `9:30` — a *time* label at the top of the chart —
  came back with value `5,531.0`, which is the current-price tag printed on the right axis.
- **Adjacent-state disagreement, again.** `#235` and `#236` are the same chart: 1.618 = 5,436 vs
  5,420, 2 = 5,386 vs 5,380, 50 % = 5,524 vs 5,520. Values that must be identical are not.
- **Panel selection is ambiguous on dual charts** — `#235` reported `timeframe: "1D"` and `#236`
  `"5"` for the same two-panel frame. Add this to the "frame classification is loose at the edges"
  caveat above.
- Every label here (`1.618`, `2`, `2.618`, `61.8%`, `50%`, `9:30`) is in the **non-method-term**
  bucket, which the levels audit already measured at 5.7 % `ohlc_match` — indistinguishable from
  chance. Consistent, not new evidence against the method-term bucket.

Two leftovers, neither costing data: `_strip_axis_ladders` missed two time-axis rows that the model
emitted as *single lines carrying many clock times* (the filter matches runs of ≥4 consecutive
lines), and the TradingView logo glyph came back as `T7`.

**Nothing here changes the Stage B decision** — it is the third independent confirmation of it.
Train on level semantics; derive prices in Python from our own bars.

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
