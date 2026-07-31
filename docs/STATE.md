# Current state — what is true right now

**Updated: 2026-07-31.** One file, overwritten in place.

## Running now

Nothing. Branch `123seq` was cut from `main` on 2026-07-31 and the scope narrowed to the **1-2-3
sequence**. `edu/` was culled to the material that teaches it; the rest was removed (see
"What was removed" below for how to get any of it back).

## The material

- **`edu/123sequence/` — the main source.** The 1-2-3 sequence itself: 5 videos, the entry-technique
  write-up and diagrams, the concepts files, the war map.
- **`edu/videos/` — supporting.** 3 concept videos (Candle Swing Theory, HTF Protocol, Simple Stoic
  Setups). Transcribed already.
- **`edu/resources/` — 8 case-study PDFs.** Labelled setups, kept for validating the rulebook later.
  Not part of the SLM's training material right now.
- **`edu/derived/` — 5 transcript sets**, one per already-transcribed video. Produced by the retired
  pipeline; format is transcript + moments + keyframes per video.

**3 of the 5 `edu/123sequence/` videos have no transcript yet** — Universal 1-2-3 Sequence, Stoic
Traders Marker Study, Scalping Example. They are the newest and most on-scope material.

## Next, in order

1. Rebuild a transcription/keyframe pipeline, aimed at the 1-2-3 sequence rather than the broad
   course. The old one is gone from the tree — `git show main:edu/pipeline/` if it is useful as
   reference. Its dependencies are still in `pyproject.toml`.
2. Transcribe the 3 untranscribed videos.
3. Read the material and build the SLM that helps derive the rulebook.
4. Turn the rulebook into a deterministic signal generator — plain code, no LLM/SLM in the live
   path. See `CLAUDE.md`, "The one rule that governs everything".

No architecture, ADRs, or parameter decisions carry over.

## Open

- **The 3 new videos in `edu/123sequence/` exist only on this disk.** They are gitignored (`*.mp4`)
  and are *not* in `videos.zip`, which predates them. Nothing restores them if the disk is lost.
  They need to go to Google Drive and into `videos.zip`.

## What was removed on 2026-07-31, and how to restore it

Restore any of this with `git show main:<path>` or `git checkout main -- <path>`, on the `main`
commit this branch was cut from.

| Removed | Restore from |
|---|---|
| `edu/derived/` for 7 case-study + live-session videos, `dataset.jsonl`, `index.json` | `main` (transcripts); keyframes are regenerable |
| 12 `.mp4` under `edu/resources/` | `videos.zip` → `./unzip_videos.sh` |
| `edu/pipeline/` (14 files) | `main` |
| root `requirements.txt` | superseded by `pyproject.toml` |

## What does not belong in this file

Completed work. This file says what is true now; `git log` says what happened.
