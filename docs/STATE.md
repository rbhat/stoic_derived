# Current state — what is true right now

The `PTB Entries` set is complete — 748 segments, the full 01:37:54, all four stages `done` in
`edu/derived/manifest.json`. `PTBV` in §0 has a file behind it, and 34 citations at 32 distinct
timestamps point at it.

**Phases 0 and 1 are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and one row
short of its gate.** The spec is written and every rule cites the material (157 timestamp citations,
all verified, negative control passing). §12 is down to **one blocking row, O-5** — the three
constants in the ATR stop floor — from eight on 2026-08-01.

**Two things now block Phase 5, not one.** O-5 above, and **Phase 2a — the invented-rule audit**
(`docs/PLAN.md`), opened 2026-08-08 on the user's directive. Phase 2 made the rules computable, and
the risk it took on is that a silence in the material got closed with a crisp predicate that reads as
settled. Every rule in §1–§9 has to be classed *cited* / *human decision* / *invented*, and the third
class leaves the spec. The standing rule behind it is in
`claude_memories/audit-hard-rules-not-in-material.md`: never invent a predicate to fill a gap — it
pre-decides what Phase 4's SLM exists to discover.

**Nine rows closed on 2026-08-03** (D-15…D-23 in §11), from the user's answers plus the `PTB Entries`
video. The three that came out of the video: a continuation entry **reuses** the sequence state, with
one Step 3 High per state frozen per entry (**D-21**); a gap through the trigger is a **market fill at
the bar's open**, never better than the trigger, with R taken from the fill (**D-22**); a **correction
bar** is one whose body opposes the sequence direction — `close < open` for a long (**D-23**).

**D-23 was the consequential one.** The alternative reading — any bar making a lower high — picks a
different anchor bar on **62.8%** of candidates (NQ 5m RTH 2019–2026, counted in
`.artifacts/ptb_atr_distribution.md`), and the anchor sets the entry level, the stop and R.

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
  bar, two inside bars, a breakout bar). **Neither has been read**, and neither has a citation key in
  `docs/RULEBOOK.md` §0.
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

1. **Run Phase 2a — the invented-rule audit.** Sweep `docs/RULEBOOK.md` §1–§9 and class every rule.
   The plan lists the known candidates and the exit gate. This is the next thing to run.
2. **Close O-5** — `k` and `n` in the `k × ATR(n)` stop floor, plus the pivot width that defines
   "swing". The distribution is measured: `.artifacts/ptb_atr_distribution.md`, regenerate with
   `.venv/bin/python scripts/measure_ptb_atr.py`. Read it as counts and set the number;
   **do not search for the best-performing cell** (`CLAUDE.md`). The pivot width is not measurable
   that way and is an unaided choice. No further reading of the material will settle any of it.
3. **Read the ninth transcript** - it is done, and register a citation key for it in §0 if it earns
   one. Read it for what it settles — do **not** mine it for predicates to harden (Phase 2a).
4. Then Phase 3 (labelled reference set) can start against a spec that says the same thing twice.
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
