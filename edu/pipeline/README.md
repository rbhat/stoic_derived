# Video knowledge pipeline

Turns the trading-education videos under `edu/` into transcripts and aligned
key-moment screenshots, plus a training-ready dataset. Idempotent and resumable —
drop in new videos any time and rerun; only the new work is done.

## What it produces

Everything lands under `edu/derived/`:

```
edu/derived/
├── index.json          manifest: every video, category, status, counts
├── dataset.jsonl       one row per screenshot (image + label + why + narration)
└── <video_id>/
    ├── meta.json          id, category, volume, title, source, duration
    ├── transcript.json    timestamped segments
    ├── transcript.md      human-readable, [hh:mm:ss] per line
    ├── transcript.txt     plain text
    ├── moments.json       LLM-selected teaching moments
    ├── keyframes.json     per frame: t, file, label, why, narration, source
    ├── keyframes/*.jpg     the screenshots
    └── state.json         per-stage resume tracking
```

`video_id` is short and stable, prefixed by category: `concept_*`, `cs_vol{N}_*`,
`live_*`. `dataset.jsonl` is the artefact a downstream model trains on.

## Prerequisites

- The repo `.venv` with `requirements.txt` installed:
  `.venv/bin/pip install -r edu/pipeline/requirements.txt`
- `ffmpeg` / `ffprobe` on PATH (`brew install ffmpeg`)
- **LM Studio** running at `http://localhost:1234` with a vision-capable model
  available (default `qwen3-vl-30b-a3b-instruct-mlx`; JIT-loaded on first call).

## Adding more videos

1. Drop the video anywhere under `edu/` (any of `.mp4 .mov .mkv .m4v .webm`).
   Location decides its category:
   - `edu/resources/case_studies/volN/...` → `case_study`
   - `edu/resources/live_trading_sessions/...` → `live_session`
   - anywhere else → `concept`
2. Run the pipeline. Already-processed videos are skipped; only new ones run.

```bash
.venv/bin/python edu/pipeline/extract_video_knowledge.py
```

## Commands

```bash
# process every video (resumable; safe to re-run)
.venv/bin/python edu/pipeline/extract_video_knowledge.py

# see status of every video without doing work
.venv/bin/python edu/pipeline/extract_video_knowledge.py --list

# only videos whose path or id matches a substring
.venv/bin/python edu/pipeline/extract_video_knowledge.py --only vol7

# force a stage to redo (repeatable): probe audio transcribe moments keyframes
.venv/bin/python edu/pipeline/extract_video_knowledge.py --only vol7 --force moments

# also caption every frame with the local VLM (slow, optional)
.venv/bin/python edu/pipeline/extract_video_knowledge.py --caption

# validate all output; writes .scratch/qa_report.json, exit 1 if anything needs redo
.venv/bin/python edu/pipeline/qa_check.py

# visual spot-check: sample frames, judge chart-readability via local VLM
.venv/bin/python edu/pipeline/visual_qa.py --per-video 2
```

## Stages (per video)

| stage       | output                       | tool |
|-------------|------------------------------|------|
| probe       | `meta.json`                  | ffprobe |
| audio       | wav in `.scratch/audio/`     | ffmpeg |
| transcribe  | `transcript.{json,md,txt}`   | mlx-whisper large-v3-turbo (Metal) |
| moments     | `moments.json`               | local LLM picks teaching moments |
| keyframes   | `keyframes/*.jpg`, json      | ffmpeg + LLM/drift/gap selection |
| caption     | `captions.json` (opt-in)     | local VLM describes each frame |

## Resumability

Each video's `state.json` records every stage with a heartbeat. A killed or
stalled stage (dead PID, or heartbeat older than 15 min) is detected and redone
on the next run. Changing a source file re-triggers all its stages. A failed
stage retries up to 3 times across runs. Just rerun the same command to continue.

## Configuration

Environment variables override the defaults:

| var                  | default |
|----------------------|---------|
| `LMSTUDIO_URL`       | `http://localhost:1234/v1` |
| `STOIC_LLM_MODEL`    | `qwen3-vl-30b-a3b-instruct-mlx` |
| `STOIC_VLM_MODEL`    | (same as LLM) |
| `STOIC_WHISPER`      | `mlx-community/whisper-large-v3-turbo` |

Keyframe density and thresholds (drift, min/max gap, narration lag) are constants
near the top of `extract_video_knowledge.py`.

## Notes

- These are continuous screencasts with no scene cuts, so classic scene-detection
  yields nothing; keyframes come from transcript-driven moments + pixel-drift +
  gap-fill instead.
- Screenshots are grabbed a few seconds *after* the narration cue so the on-screen
  chart has caught up to what the instructor is describing.
