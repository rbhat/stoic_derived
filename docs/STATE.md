# Current state — what is true right now

The `PTB Entries` set is complete — 748 segments, the full 01:37:54, all four stages `done` in
`edu/derived/manifest.json`. `PTBV` in §0 has a file behind it, and 34 citations at 32 distinct
timestamps point at it.

**Phases 0 and 1 are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and is short of
its gate on one open row and an unfinished audit.** The spec is written and every rule carries a
citation; §12 now blocks on **O-14** alone (where the post-Step-3 expansion leg ends).

**"Every rule cites the material" is not the same as "every rule is supported by it."** Citations
**resolve** — all of them, including under the Phase 2a sweep. That was never a check on whether a
rule says **more than** the source it points at, and **10 of 143 swept rows do**.

**The sweep is now complete and verified; it was neither before.** Its coverage was wrong and the
arithmetic hid it — three sweeps counted 132 rows, §1–§9 holds 132 definitional rows, **different
132**. Eleven numbered rules had no evidence at all. `sweep_D` closed that on 2026-08-08 (143 rows, 0
broken), and all twelve findings are now verified against source — one of them **rejected** on
verification. Detail, per finding, in `docs/AUDIT-2a.md`. Two results bind what comes next:
**`5.3.4`** rests on `PTBQ` §1 **contradicting itself** (*"within the three-bar window"* and *"The 3
bar window is not defintite"*, both verbatim), and **`5.4.7c`** rests on a condition an independent
search confirms is **nowhere in the corpus**. Both are now disclosed in the rules themselves.

**Three marked-up charts in `edu/123sequence/` had never been opened** — `stoic_trade2.png`,
`stoic_live_trade3.png`, `stoic_live_trade4.png`, in the repo since the restart cull, referenced
nowhere in `docs/`, read 2026-08-08. Between them: **two complete 1-2-3 counts with two PTBs on one
chart** and a live-marked **reset**, **`BE`** drawn on a chart, outcomes to **+4.5R**, and **`PWC` /
`PLOW`** — previous-week levels the material targets and §7.3 does not define. `docs/AUDIT-2a.md`
F-13. Hashing every image asset also settled the wider question F-1 raised: **fifteen files, exactly
one duplicated hash** — F-1's known triple — so `DIA-S` and `IBD` are genuinely distinct and F-1's
damage does not spread.

**The audit found that `DIA-P` and `DIA-L` are the same file** — md5 `5db99292665d2f688ee34531688444ad`,
`diff` empty, three paths one content. §10.3 concludes *"two independent drawings agreeing bar for
bar is why §3.4 and §5.3.4 could be stated mechanically"*, and there are not two drawings. The
diagram's content is real and the geometry checks out; the **corroboration argument is void**, and
two rules were promoted to **M** partly on it.

**The factual half is applied** — §0 discloses the identity, §10.3's two false sentences are gone,
and §5.2.4 / §5.3.6 no longer count one drawing twice. **The judgment half is open:** §3.4 and §5.3.4
now stand on `DIA-L` plus the transcripts alone, and nobody has re-checked whether that carries their
**M**. See `docs/AUDIT-2a.md` F-1.

**Five decisions closed on 2026-08-08, from the user reading the audit's frozen-decision list.**
**D-18 deleted the ATR stop floor** — *"stop after entry is the opposite extreme of the PTB"* — which
**closed O-5 without setting its three constants** and unblocked L4. ATR is never mentioned in the
corpus; the mechanism was ours. **D-24's *strong* is now 10% of the candle's own high-low range**, the
only number in the exit path. **D-17 gained the termination it was missing** — the order walks candle
by candle *"till either we hit an entry or it invalidates without an entry"*, so §5.4.7 now cancels
pending orders as well as closing open trades (§5.3.4a). **D-24's Step 2 boundary condition was
re-read and affirmed** by the user, so it stays despite being absent from the corpus. And **D-25 is
new**: the stop goes to break-even when price trades beyond the Step 3 High/Low — the same event as
TP1, which is where `ET` already put it. `TPA @ 00:13:00` teaches an earlier trigger and D-25 records
the divergence rather than dropping it.

**Two things now block Phase 5.** **O-14** (below) and **Phase 2a — the invented-rule audit**
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
open as **O-14**. That clause was **reframed on 2026-08-08** once L3's layer boundaries were fixed:
it is not a distance to the MAs, it is where the expansion leg ends. See Next, item 3.

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
narrows §6.5, which still says the position is *"simply held"*.

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

1. **Finish Phase 2a — `docs/AUDIT-2a.md` is the record.** The mechanical sweep is **complete and
   verified**: 143 rows across four sweeps, **10 `YES`**, **0 broken citations**, all twelve findings
   checked against source by the lead. What remains is the judgment half, and it is now the only
   thing left in the phase: **class the 132 definitional rows** *cited* / *human decision* /
   *invented*, apply the dispositions F-1 … F-12 each carry, re-check the status tags on `5.3.4` and
   `5.4.7c`, and report the count moved out without minimising it.
2. **Fold `TPA`'s management content into §6.** Held back deliberately so the audit sweeps text that
   is not moving underneath it. The passages are listed under Open below; §6.5 currently contradicts
   one of them.
3. **Close O-14 — reframed 2026-08-08, and the reframing is most of the work.** It was *"what does
   **approaching the 10/20 SMA** mean"*, a distance nobody could source. It is now **"where does the
   post-Step-3 expansion leg end and the pullback begin"** — a structural question **L1 already owns**
   (`docs/PLAN.md` lists *consolidation vs expansion* there). `ET` defines the PTB as *"simply the
   last candle in that pullback"*, so it presupposes a pullback; §5.3.3a had substituted an atomic
   property of one candle for a fact about a leg. Asked correctly it is **answerable from the
   material** — §8, §2.2, §4, and the bar-by-bar walkthroughs — so it goes to the **Phase 4 SLM** with
   those passages attached, per `claude_memories/audit-hard-rules-not-in-material.md`. It gates **L1
   and L3**.
4. Then Phase 3 (labelled reference set) can start against a spec that says the same thing twice.
   `stoic_trade2.png` is now the densest candidate fixture — two counts, two PTBs, six executions on
   one chart (F-13) — with `NQ3` (§10.7) the cleanest single-sequence one. Both are single instances,
   so small-*n* rules apply. `PTBV` is the richer source: a full session in which the trader marks
   every PTB entry on one 1-2-3.

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
  high just get out of the position and reassess."* One more is missing, and two are now resolved.
  **Resolved:** the *"trailing behind the PTB"* passages (`TPA @ 00:17:50`, `00:31:06`, `00:21:20`)
  were filed here as a **trailing stop** and are **not** — the user confirmed on 2026-08-08 that this
  is **entry anchoring**, which §5.3.5 already cites `TPA @ 00:17:50` for. The **break-even trigger**
  (`TPA @ 00:13:00`, once price takes out the PTB) is now **D-25**, which takes `ET`'s later trigger
  instead and records `TPA`'s as a divergence. **Still missing:** **HTF nesting**,
  where the *higher* timeframe's confirmed Step 3 is what licenses the 5m PTB entries
  (`TPA @ 00:45:01`–`00:45:43`) — stronger than §9's current reading of the execute timeframe as a
  timing aid. Also qualifying D-7: the 1m is explicitly discouraged, *"one minute is tricky… it could
  have fake outs"* (`TPA @ 00:18:57`).
- **Three marked charts still need citation keys and worked examples** — `stoic_trade2.png`,
  `stoic_live_trade3.png`, `stoic_live_trade4.png` (F-13). They are read but not yet wired into §0
  or §10, so no rule can cite them and Phase 3 cannot use them as fixtures. `stoic_trade2.png` is the
  denser reset fixture; the other two are one trade at two snapshots.
- **`PWC` and `PLOW` are undefined in §7.3** — previous weekly close and previous low of the week.
  The material uses `PWC` as an explicit target (`PTBV @ 00:25:54`) and `CST` teaches previous-week
  levels throughout; §7.3 defines only `PDH`/`PDL`/`PDC` and `HCOM`/`LCOM`, while §10.1–§10.2 already
  name `PLOW` without defining it. Needs an open row.
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
