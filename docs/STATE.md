# Current state — what is true right now

The `PTB Entries` set is complete — 748 segments, the full 01:37:54, all four stages `done` in
`edu/derived/manifest.json`. `PTBV` in §0 has a file behind it, and 34 citations at 32 distinct
timestamps point at it.

**Phases 0 and 1 are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and is short of
its gate on two open rows and an unfinished audit.** The spec is written and every rule carries a
citation; §12 blocks on **O-5** (the three constants in the ATR stop floor) and **O-14** (what
*"approaching the 10/20"* means), O-14 being the earlier gate.

**"Every rule cites the material" is not the same as "every rule is supported by it."** This file
used to claim 157 citations *"all verified"*. That claim was about whether citations **resolve** —
they do, all of them, including under the Phase 2a sweep. It was never a check on whether a rule says
**more than** the source it points at, and **10 of 132 rules do**. See `docs/AUDIT-2a.md`.

**The audit found that `DIA-P` and `DIA-L` are the same file** — md5 `5db99292665d2f688ee34531688444ad`,
`diff` empty, three paths one content. §10.3 concludes *"two independent drawings agreeing bar for
bar is why §3.4 and §5.3.4 could be stated mechanically"*, and there are not two drawings. The
diagram's content is real and the geometry checks out; the **corroboration argument is void**, and
two rules were promoted to **M** partly on it. Not yet applied — see `docs/AUDIT-2a.md` F-1.

**Three things now block Phase 5.** O-5 above, **O-14** (below), and **Phase 2a — the invented-rule audit**
(`docs/PLAN.md`), opened 2026-08-08 on the user's directive. Phase 2 made the rules computable, and
the risk it took on is that a silence in the material got closed with a crisp predicate that reads as
settled. Every rule in §1–§9 has to be classed *cited* / *human decision* / *invented*, and the third
class leaves the spec. The standing rule behind it is in
`claude_memories/audit-hard-rules-not-in-material.md`: never invent a predicate to fill a gap — it
pre-decides what Phase 4's SLM exists to discover.

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
readings were rejected as over-specification.** A PTB is now *a candle after Confirmed Step 3
approaching the 10/20 SMA, and not an inside candle* — status **J**, with the *approaching* clause
open as **O-14**.

**The 62.8% still matters, inverted.** That is how often the two rejected readings pick a different
anchor bar (NQ 5m RTH 2019–2026, `.artifacts/ptb_atr_distribution.md`) — which is why neither could
be adopted quietly, and why the `BODY` and `EXTREME` columns of that artifact now describe two
readings the spec does not use. The artifact's ATR percentiles are unaffected and O-5 still reads off
it.

**D-24 opened and closed on 2026-08-08 — trade invalidation.** Three conditions, any one of which
ends an open trade: the confirmed opposite Step 3 (already §6.4); a **strong close beyond the 10/20
against the trade direction**; and a **break of the Step 2 boundary against the trade direction**.
The MA condition is corroborated (`TPA @ 00:24:48`, `PTBV @ 00:03:28`); the **Step 2 boundary
condition was not found anywhere in the corpus** and is the user's, as is *strong* — so it is a
decision, not a citation. It narrows §6.5, which still says the position is *"simply held"*.

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
  `1-2-3-PTB-Long.svg` (`DIA-P` — `DIA-L` re-drawn with the Step 3 High and PTB labelled),
  `nq-1-2-3.png` (`NQ3` — the first fully-marked live chart with real prices, worked at
  `docs/RULEBOOK.md` §10.7), and one clarifying sentence appended to `PTB Questions.md`.
- **Added 2026-08-08:** the `Navigating tough price action with 1-2-3 and PTBs` video (58:00, 410
  segments, transcript complete) and `insidebar.png` (the StoicEdge inside-bar schematic: a parent
  bar, two inside bars, a breakout bar). **Both read 2026-08-08**, and both now carry citation keys
  in `docs/RULEBOOK.md` §0 — `TPA` and `IBD`. `TPA` is the densest source in the corpus on what a PTB
  is and is not, and it rewrote **D-23**. Its management content is **not yet folded in** — see Open.
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

**`docs/PLAN.md` is the plan, end to end.** Position: Phases 0 and 1 closed, **Phase 2 open on its
gate, not on its deliverable**.

1. **Finish Phase 2a — `docs/AUDIT-2a.md` is the record.** The mechanical citation sweep is **done**:
   132 rules, **10 `YES`** (rule says more than its source), **0 broken citations**. Five findings
   were verified against source by the lead, six were not — the doc marks which. What remains is the
   judgment half: class every rule, apply dispositions, report the count moved out.
2. **Fold `TPA`'s management content into §6.** Held back deliberately so the audit sweeps text that
   is not moving underneath it. The passages are listed under Open below; §6.5 currently contradicts
   one of them.
3. **Close O-14** — what *"approaching the 10/20 SMA"* means for a PTB candidate. **J** by
   construction, so per `claude_memories/audit-hard-rules-not-in-material.md` this is a Phase 4 SLM
   question, not a number to choose. It is the earliest gate on Phase 5: without it L3 cannot decide
   which bar the order sits on.
4. **Close O-5** — `k` and `n` in the `k × ATR(n)` stop floor, plus the pivot width that defines
   "swing". The distribution is measured: `.artifacts/ptb_atr_distribution.md`, regenerate with
   `.venv/bin/python scripts/measure_ptb_atr.py`. Read it as counts and set the number;
   **do not search for the best-performing cell** (`CLAUDE.md`). The pivot width is not measurable
   that way and is an unaided choice. No further reading of the material will settle any of it.
   Its `BODY` / `EXTREME` columns now describe two readings the spec rejected (D-23); the ATR
   percentiles O-5 actually needs are unaffected.
5. Then Phase 3 (labelled reference set) can start against a spec that says the same thing twice.
   `NQ3` (§10.7) is the first candidate fixture — one instance, so small-*n* rules apply. `PTBV` is
   the richer source: a full session in which the trader marks every PTB entry on one 1-2-3.

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

- **`TPA`'s management content is read but not folded into §6.** Four findings, all cited, held for
  the pass after the audit (Next, item 2). **§6.5 is contradicted**: it says the position is *"simply
  held"* to the opposite Step 3, but `TPA @ 00:13:36`–`00:14:06` says *"as soon as price makes a lower
  high just get out of the position and reassess."* Three more are simply missing — a **trailing stop
  behind each new PTB** (`TPA @ 00:17:50`, `00:31:06`, `00:21:20`), a **break-even trigger** once
  price takes out the PTB, making it a *"confirmed PTB bar"* (`TPA @ 00:13:00`), and **HTF nesting**,
  where the *higher* timeframe's confirmed Step 3 is what licenses the 5m PTB entries
  (`TPA @ 00:45:01`–`00:45:43`) — stronger than §9's current reading of the execute timeframe as a
  timing aid. Also qualifying D-7: the 1m is explicitly discouraged, *"one minute is tricky… it could
  have fake outs"* (`TPA @ 00:18:57`).
- **An unrelated file is sitting in `edu/123sequence/`** — a LinkedIn job-posting PDF, untracked. It
  is not strategy material and should not be committed with the corpus.
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
