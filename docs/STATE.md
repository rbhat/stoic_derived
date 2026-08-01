# Current state — what is true right now

**Updated: 2026-08-01.** One file, overwritten in place.

## Running now

Nothing. **Phases 0 and 1 are complete.** **Phase 2 has a deliverable — `docs/RULEBOOK.md` — and its
gate is not yet met.** The spec is written and every rule cites the material (101 timestamp
citations, all verified against the transcripts). What is missing is agreement on the terms the
material leaves open: `docs/RULEBOOK.md` §12 lists 12 of them, **8 blocking**. Phase 5 must not start
until those close — that is the failure `docs/PLAN.md` is shaped to avoid.

**The decision register has moved.** `docs/RULEBOOK.md` §11 holds the closed decisions and §12 the
open ones. The table in `docs/PLAN.md` was the intake form and is now historical.

## The material

- **`edu/123sequence/` — the main source.** The 1-2-3 sequence: 3 videos, the entry-technique
  write-up and diagrams, the concepts files, the war map, and the new `discussion/` and
  `concepts/PTB Questions.md` notes from the user.
- **`edu/videos/` — supporting.** 3 concept videos (Candle Swing Theory, HTF Protocol, Simple Stoic
  Setups).
- **`edu/resources/` — 8 case-study PDFs.** Validation material for the rulebook, not training input.
- **`edu/derived/` — 7 transcript sets, one per video. The corpus is complete.** Every video under
  `edu/` is now readable as transcript + keyframes, indexed by `edu/derived/manifest.json`.

**A duplicate was removed on 2026-08-01.** `Universal 1-2-3 Sequence …mp4` was a byte-identical
recording of `Stoic Edge System Module 1 is Live …mp4` — same full-audio md5
(`12902a8cf8bc6c6632273491aefe5bde`), same 86,654 frames. The Module 1 copy was kept because
`videos.zip` backs it up at exactly its 48,245,311 bytes and does not contain the Universal file.
So Phase 1 produced **2** new transcript sets, not the 3 its exit gate named.

## Next

**`docs/PLAN.md` is the plan, end to end.** Position: Phases 0 and 1 closed, **Phase 2 open on its
gate, not on its deliverable**.

Close the 8 blocking rows in `docs/RULEBOOK.md` §12. They are the human's to settle, per the standing
directive in `CLAUDE.md` — not a grid search. Then Phase 3 (labelled reference set) can start against
a spec that says the same thing twice.

`docs/RULEBOOK.md` §13 records a scope boundary worth knowing before opening any transcript: the
corpus contains a **second system** (Simple Stoic Setups / HTF Protocol / Candle Swing Theory / the
war map) built on daily closes, a three-day cycle and an MA chop zone. It is not the 1-2-3 sequence
and none of its rules are imported.

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
