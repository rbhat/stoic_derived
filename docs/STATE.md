# Current state — what is true right now

The `PTB Entries` set is complete — 748 segments, the full 01:37:54, all four stages `done` in
`edu/derived/manifest.json`. `PTBV` in §0 has a file behind it, and 34 citations at 32 distinct
timestamps point at it.

**Phases 0, 1 and 2a are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and is short
of its gate on one open row.** The spec is written and every rule carries a citation; §12 now blocks
on **O-14** alone (where the post-Step-3 expansion leg ends).

**One thing now blocks Phase 5: O-14**, and it gates **L1 and L3**. L4 is clear.

## Phase 2a — closed 2026-08-08. `docs/AUDIT-2a.md` is the record; this is the summary

All **132 definitional rows** in §1–§9 are classed: **109 cited, 23 human decision, 0 invented**. The
sweep ran to 143 rows across four passes, 0 broken citations, and all twelve findings were verified
against source by the lead — **one agent-reported finding was rejected** on verification.

**The caveat matters more than the count.** The largest invented mechanism in the spec — the ATR stop
floor — was classed a legitimate `DECISION` by every sweep, because it cited a real D-row with a real
open row for its constants. It came out only because the human was asked where the predicate came
from. **No mechanical check would have caught it**, which is why
`claude_memories/audit-hard-rules-not-in-material.md` is a standing rule and not a phase.

Four results bind what comes next:

- **The sweep's own coverage was wrong and the arithmetic hid it.** Three sweeps counted 132 rows and
  §1–§9 holds 132 definitional rows — **different 132**. Eleven numbered rules had no evidence at
  all. `sweep_D` closed it. See `claude_memories/coverage-claims-need-enumeration.md`.
- **`5.3.4`** rests on `PTBQ` §1 **contradicting itself** — *"within the three-bar window"* and *"The
  3 bar window is not defintite"* are both verbatim in that file, and **D-17** picks a side.
  **`5.4.7c`** rests on a condition an independent search confirms is **nowhere in the corpus**, and
  the user re-read and affirmed it. Both are disclosed in the rules themselves.
- **`DIA-P` and `DIA-L` are one file** (md5 `5db99292…`, `diff` empty, three paths). §10.3's
  corroboration argument was void and is gone; §0, §5.2.4 and §5.3.6 disclose the identity.
  **Resolved:** §3.4 and §5.3.4 **keep M** — §3.4 never rested on the corroboration (its source is
  D-16, and a running maximum has no free parameter), and §5.3.4 keeps M with the `PTBQ`
  contradiction disclosed. Hashing every image asset settled the wider question: **fifteen files,
  exactly one duplicated hash**, so `DIA-S` and `IBD` are genuinely distinct.
- **Three marked-up charts had never been opened** — in the repo since the restart cull, referenced
  nowhere in `docs/`, read 2026-08-08 (F-13). **Now wired in as `T2`, `LT3` and `LT4`** (§0, §10.8–
  §10.9), and `PWC` / `PWH` / `PLOW` are defined in §7.3. Between them: **two complete 1-2-3 counts
  with two PTBs on one chart** and a live-marked **reset**, **`BE`** drawn on a chart, and outcomes
  to **+4.5R**.

**Five decisions closed the same day**, from the user reading the audit's frozen-decision list:

| | |
|---|---|
| **D-18** | **Deleted the ATR stop floor** — *"stop after entry is the opposite extreme of the PTB."* ATR is nowhere in the corpus. **Closed O-5 without setting its constants; unblocked L4** |
| **D-24** | ***Strong* = 10% of the candle's own high-low range** — the only number in the exit path |
| **D-24** | The **Step 2 boundary condition re-read and affirmed**, so it stays despite being absent from the corpus |
| **D-17** | Gained its missing termination — the order walks candle by candle *"till either we hit an entry or it invalidates without an entry"*, so §5.4.7 now cancels pending orders too (§5.3.4a) |
| **D-25** | **New.** Stop to break-even when price trades beyond the Step 3 High/Low — the same event as TP1, where `ET` already put it. `TPA @ 00:13:00` teaches an earlier trigger; D-25 records the divergence |

**Also settled:** the trail **skips inside candles** rather than advancing to them, and resumes at the
next non-inside candle (§5.3.5a) — §5.2.8 previously said the anchor *"moves on"*, which read as the
opposite.

**Nine rows closed on 2026-08-03** (D-15…D-23 in §11), from the user's answers plus the `PTB Entries`
video. Two that came out of the video still stand: a continuation entry **reuses** the sequence state,
with one Step 3 High per state frozen per entry (**D-21**); a gap through the trigger is a **market
fill at the bar's open**, never better than the trigger, with R taken from the fill (**D-22**).

**D-23 was rewritten on 2026-08-08** — the first Phase 2a-class finding, and it landed before the
audit did. Its old form (*a correction bar is one whose body opposes the sequence direction,
`close < open` for a long*) was a **P**-grade predicate recorded as a decision on the belief that the
material was silent. The ninth transcript (`TPA`) is not silent: it states the rival *lower-high*
reading in **five** distinct passages — `@ 00:01:05`, `@ 00:23:30`, `@ 00:23:50`, `@ 00:27:47`,
`@ 00:29:52`, the last two being the bearish mirror — inside a bar-by-bar walkthrough at
`00:23:20`–`00:26:52`, while D-23's sole citation (`PTBV @ 00:02:15`) discriminates neither reading. Put to the user, **both mechanical
readings were rejected as over-specification.** A PTB is *a candle **inside the pullback** that
follows Confirmed Step 3, and not an inside candle* — status **J**. It read *"approaching the 10/20
SMA"* until 2026-08-08, when fixing L3's layer boundaries showed that phrase was standing in for a
structural fact a layer below already owned: **the open question is where the expansion leg ends, not
how near the MAs a candle sits.** That is **O-14** — see Next, item 1.

**The 62.8% still matters, inverted.** That is how often the two rejected readings pick a different
anchor bar (NQ 5m RTH 2019–2026, `.artifacts/ptb_atr_distribution.md`) — which is why neither could
be adopted quietly, and why the `BODY` and `EXTREME` columns of that artifact now describe two
readings the spec does not use. **Its ATR percentiles now have no consumer at all** — O-5 closed by
deleting the stop floor, so nothing in the spec reads them. The 62.8% figure is still the reason
D-23 stands; the rest of the artifact is inert.

**D-24 opened and closed on 2026-08-08 — trade invalidation.** Three conditions, any one of which
ends an open trade: the confirmed opposite Step 3 (already §6.4); a **strong close beyond the 10/20
against the trade direction**; and a **close beyond the Step 2 boundary against the trade
direction** — trading through it is not enough, which makes 5.4.7c the mirror of §2.3.1, where a
trade through the *same* line is what starts Step 3. All three exits are close-based; the stop is the
only trade-through in the exit path.

The MA condition is corroborated (`TPA @ 00:24:48`, `PTBV @ 00:03:28`); the **Step 2 boundary
condition was not found anywhere in the corpus** — an independent search under Phase 2a confirmed
zero hits — and is the user's, as is *strong*, now set at **10% of the candle's range**. Both are
decisions, not citations, and the user re-read and affirmed the boundary condition on 2026-08-08. It
narrows §6.5, which said the position is *"simply held"* until **D-26** rewrote it.

**`insidebar.png` (`IBD`) closed the question the audit was created over.** The inside-bar reference
is the **parent bar** — the nearest preceding bar not itself inside — not the bar immediately to the
left. `IBD` labels one Parent Bar and points a run of two Inside Bars at it;
`claude_memories/audit-hard-rules-not-in-material.md` was written when that reference had no source.
It has one now, so §5.2.8a is **cited**, not invented. The memory's standing rule is untouched.

**The decision register lives in `docs/RULEBOOK.md` §11**, with §12 for what is still open. The table
in `docs/PLAN.md` was the intake form and is now historical.

## The material

- **`edu/123sequence/` — the main source.** The 1-2-3 sequence: 4 videos, the entry-technique
  write-up and diagrams, the concepts files, the war map, and the `discussion/` and
  `concepts/PTB Questions.md` notes from the user.
- **Added 2026-08-03:** the `PTB Entries - NQ Live Trading 10R` video (1h38m, `PTBV` — a full session
  traded on PTB continuation entries, and the densest single source on §2.5 and §5.3),
  `1-2-3-PTB-Long.svg` (`DIA-P` — **not a re-drawing: byte-identical to `DIA-L`**, as this file
  claimed until the audit checked the md5; see the F-1 note above),
  `nq-1-2-3.png` (`NQ3` — the cleanest **single-sequence** live-marked chart, worked at
  `docs/RULEBOOK.md` §10.7; it was called the *first* fully-marked one until F-13 found three others),
  and one clarifying sentence appended to `PTB Questions.md`.
- **Added 2026-08-08:** the `Navigating tough price action with 1-2-3 and PTBs` video (58:00, 410
  segments, transcript complete) and `insidebar.png` (the StoicEdge inside-bar schematic: a parent
  bar, two inside bars, a breakout bar). **Both read 2026-08-08**, and both now carry citation keys
  in `docs/RULEBOOK.md` §0 — `TPA` and `IBD`. `TPA` is the densest source in the corpus on what a PTB
  is and is not, and it rewrote **D-23**. Its management content is **folded in** — D-25, D-26, D-27 and the D-7 amendment.
- **`edu/videos/` — supporting.** 3 concept videos (Candle Swing Theory, HTF Protocol, Simple Stoic
  Setups).
- **`edu/resources/` — 8 case-study PDFs.** Validation material for the rulebook, not training input.
- **`edu/derived/` — 9 complete transcript sets**, one per video, indexed by
  `edu/derived/manifest.json`.

**A duplicate was removed on 2026-08-01.** `Universal 1-2-3 Sequence …mp4` was a byte-identical
recording of `Stoic Edge System Module 1 is Live …mp4` — same full-audio md5
(`12902a8cf8bc6c6632273491aefe5bde`), same 86,654 frames. The Module 1 copy was kept because
`videos.zip` backs it up at exactly its 48,245,311 bytes and does not contain the Universal file.
So Phase 1 produced **2** new transcript sets, not the 3 its exit gate named.

## Next

**`docs/PLAN.md` is the plan, end to end.** Position: Phases 0, 1 and 2a closed, **Phase 2 open on its
gate, not on its deliverable**.

1. **O-14 is with the Phase 4 SLM, and its input set is now assembled.** It gates **L1 and L3**.
   Reframed 2026-08-08 from *"what does approaching the 10/20 SMA mean"* to **"where does the
   post-Step-3 expansion leg end and the pullback begin"** — a structural question **L1 already owns**.
   **The passages are attached under §12** — seven citations across `TPA` and `PTBV`. They settle the
   *concept* (no pullback while price keeps making new extremes; both directions stated) and leave
   **three rival operationalizations** of the first candle that goes the other way. **Put to the user
   2026-08-08, who declined to pick and kept it with the SLM** — so this needs Phase 4, not another
   pass over the corpus. Do not re-derive the passages and do not re-ask.
2. Then Phase 3 (labelled reference set) can start against a spec that says the same thing twice.
   **`T2` (§10.8) is the densest fixture** — two counts, a live-marked reset, two PTBs, six
   executions — with `NQ3` (§10.7) the cleanest single-sequence one and `LT3`/`LT4` (§10.9) the only
   trade held past the session. All are single instances, so small-*n* rules apply. `PTBV` is the
   richer source: a full session in which the trader marks every PTB entry on one 1-2-3.
   **§10.10 recovers the stop from any of them** — none draws one, but the R labels are normalised
   against a ~$1,000 risk unit, so `stop distance = P&L points ÷ R multiple`.

`docs/RULEBOOK.md` §13 records how the rest of the corpus is used. Simple Stoic Setups / HTF Protocol
/ Candle Swing Theory / the war map are the **complementary layer the 1-2-3 was distilled from** —
context and targets, never a step of the sequence, and they yield on conflict.

## What Phase 0 and Phase 1 built

| | |
|---|---|
| `stoic/sessions.py` | CME trading day, session phases, the 13:58 PT flatten cutoff. UTC storage, local zones only inside this module |
| `stoic/bars.py` | 1m → 5m/15m/60m/1D/1W. Pure resample, no materialised parquet |
| `scripts/check_bar_spine.py` | Gates A–E, each with literal output and a negative control |
| `scripts/build_corpus.py` | Resumable transcribe + keyframe pipeline, 4 stages, no LLM/VLM |
| `tests/` | 25 tests, hermetic |

## Open

- **`TPA`'s management content is folded in — closed 2026-08-08.** All four findings landed:
  the *"trailing behind the PTB"* passages were **entry anchoring**, not a stop rule (§5.3.5); the
  break-even trigger became **D-25**; the lower-high exit became **D-26** and the **HTF nesting**
  **D-27**; and **D-7 was amended** to drop 1m execution for Scalp and Day. Nothing from `TPA`
  remains unread against §6.
- **A `T2` reading that would bear on D-23, not yet verified.** On `T2`'s bullish count the last
  pullback candle before the entry looks **up-bodied (green)**, which would make it a live-marked
  counterexample to the `close < open` body test D-23 rejected — evidence *for* the decision the user
  already took. It is **not** written into §10.8, because at the available zoom the `ptb` level's
  anchor bar cannot be told apart from the large down candle before it (~14 points, inside the ±10
  pixel error). Worth one pass at full resolution; nothing depends on it.
- **`LT4` is held past the 1:58pm Pacific flatten** — entry 04:00 PM ET, exit into the Asia session
  at +4.5R (§10.9). Under `VISION.md` a Scalp or Day trade is marked closed at the cutoff, so this
  fixture is only reproducible as a **Swing or Position** Type. Phase 3 must record the Type it
  labels it as; Phase 6 will otherwise report a divergence that is the harness's, not the engine's.
- **Session `2025-11-28` has a ~645-minute hole in `data/historical/{NQ,ES}_1m.parquet`** — the whole
  Asia/London portion, both instruments. Real missing data, not a holiday early close. Any Phase 3
  label or Phase 5 replay touching that date must exclude or flag it. See
  `claude_memories/historical-bars-2025-11-28-outage.md`; Gate E reports it every run.
- **The source videos exist only on this disk.** They are gitignored (`*.mp4`) and `videos.zip`
  predates the 1-2-3 material, so it does not contain the Marker Study, the Scalping Example, the
  `PTB Entries` video (the one the newest 34 citations rest on), or `Navigating tough price action`
  added 2026-08-08. Nothing
  restores them if the disk is lost. They need to go to Google Drive and into `videos.zip`.
  The transcripts and keyframe manifests are in git; the keyframe **images** are gitignored
  (`edu/derived/**/keyframes/`) and are regenerable from the videos — which is only true while the
  videos survive.
- `past_flatten` is 0 for every 5m bar by construction — the cutoff sits in a 2-minute window no 5m
  bar can start in. Phase 7 will need the bar *containing* the cutoff, not bars after it.

## What was removed on 2026-07-31, and how to restore it

Restore with `git show main:<path>` or `git checkout main -- <path>`.

| Removed | Restore from |
|---|---|
| `edu/derived/` for 7 case-study + live-session videos, `dataset.jsonl`, `index.json` | `main` (transcripts); keyframes are regenerable |
| 12 `.mp4` under `edu/resources/` | `videos.zip` → `./unzip_videos.sh` |
| `edu/pipeline/` (14 files) | `main` — superseded by `scripts/build_corpus.py` |
| root `requirements.txt` | superseded by `pyproject.toml` |

## What does not belong in this file

Completed work. This file says what is true now; `git log` says what happened.
