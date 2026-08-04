# Current state — what is true right now

**Updated: 2026-08-03.** One file, overwritten in place.

## Running now

**One unfinished job: the `PTB Entries` transcript.** `edu/derived/concept_ptb_entries_nq_live_trading_10r/`
has `probe` and `audio` done and `transcribe` stopped at **01:21:23 of 01:37:54** (618 segments in
`transcript.partial.jsonl`). The stage is resumable —
`.venv/bin/python scripts/build_corpus.py --only ptb_entries` picks up from the partial. Until it
finishes there is **no `transcript.md`**, so the `PTBV` citation key in `docs/RULEBOOK.md` §0 has no
file behind it yet and nothing cites it.

**Phases 0 and 1 are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and its
gate is not yet met.** The spec is written and every rule cites the material (129 timestamp
citations, all verified, negative control passing). What is missing is agreement on the terms the
material leaves open: `docs/RULEBOOK.md` §12 lists **4 blocking** — O-2, O-5, O-12, O-13 — down from
8 on 2026-08-01. Phase 5 must not start until those close.

**Six blocking rows closed on 2026-08-03** (D-15…D-20 in §11), from the user's answers plus new
material: O-1 (no three-bar cap), O-3 (reset keys off the 10/20), O-4 (the Step 3 High never has to
be final), O-6 (the fib extension anchors on the first pullback), O-8 (no chop detector). O-5 was
narrowed to three constants. **O-13 is new** — the residue of closing O-1: with no bar cap, the
definition of "correction bar" becomes load-bearing.

**The decision register has moved.** `docs/RULEBOOK.md` §11 holds the closed decisions and §12 the
open ones. The table in `docs/PLAN.md` was the intake form and is now historical.

## The material

- **`edu/123sequence/` — the main source.** The 1-2-3 sequence: 4 videos, the entry-technique
  write-up and diagrams, the concepts files, the war map, and the `discussion/` and
  `concepts/PTB Questions.md` notes from the user.
- **Added 2026-08-03:** the `PTB Entries - NQ Live Trading 10R` video (1h38m, transcript in
  progress), `1-2-3-PTB-Long.svg` (`DIA-P` — `DIA-L` re-drawn with the Step 3 High and PTB labelled),
  `nq-1-2-3.png` (`NQ3` — the first fully-marked live chart with real prices, worked at
  `docs/RULEBOOK.md` §10.7), and one clarifying sentence appended to `PTB Questions.md`.
- **`edu/videos/` — supporting.** 3 concept videos (Candle Swing Theory, HTF Protocol, Simple Stoic
  Setups).
- **`edu/resources/` — 8 case-study PDFs.** Validation material for the rulebook, not training input.
- **`edu/derived/` — 7 complete transcript sets plus one in progress**, one per video, indexed by
  `edu/derived/manifest.json`. The eighth (`PTB Entries`) is the unfinished job above.

**A duplicate was removed on 2026-08-01.** `Universal 1-2-3 Sequence …mp4` was a byte-identical
recording of `Stoic Edge System Module 1 is Live …mp4` — same full-audio md5
(`12902a8cf8bc6c6632273491aefe5bde`), same 86,654 frames. The Module 1 copy was kept because
`videos.zip` backs it up at exactly its 48,245,311 bytes and does not contain the Universal file.
So Phase 1 produced **2** new transcript sets, not the 3 its exit gate named.

## Next

**`docs/PLAN.md` is the plan, end to end.** Position: Phases 0 and 1 closed, **Phase 2 open on its
gate, not on its deliverable**.

1. **Finish the `PTB Entries` transcript** (one command, resumable). The user's read is that it
   answers **O-2** (gaps and fills) and **O-12** (whether a continuation entry needs its own Step 3
   High) directly — *"I think the others are covered in the video."* Both are still open pending
   that read.
2. **Close the remaining blocking rows** in `docs/RULEBOOK.md` §12: O-2 and O-12 from the video,
   **O-13** (what counts as a correction bar) and **O-5** (the three constants in the ATR stop floor)
   from the human. They are the human's to settle, per the standing directive in `CLAUDE.md` — not a
   grid search. **O-5 in particular:** measure the distribution of PTB range ÷ ATR and report counts;
   do not search for the best-performing cell.
3. Then Phase 3 (labelled reference set) can start against a spec that says the same thing twice.
   `NQ3` (§10.7) is the first candidate fixture — one instance, so small-*n* rules apply.

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
  predates the 1-2-3 material, so it does not contain the Marker Study or Scalping Example. Nothing
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
