#!/usr/bin/env python3
"""
WP-V §3.1 — deterministic frame harvest + perceptual-hash dedupe.

Sample every one of the 16 education videos at 1 fps, collapse consecutive
near-duplicate frames into "distinct visual states" with a t_start/t_end run,
and extract one full-resolution JPEG per state. A frame joins a run only when
BOTH a coarse 64-bit dHash (Hamming <= HAMMING_MAX, global layout) and a fine
720-cell localized-change fraction (<= FINE_FRAC) hold against the run's
anchor frame -- v1 used dHash alone and was blind to localized change (a
drawn level, an added bullet, price action), see wpv_31_fix_spec.md. This is
the *harvest* stage of WP-V; classification (OCR / chart reading) is a
separate, model-driven pass and is explicitly out of scope here. Nothing in
this file calls a model — it is pure ffmpeg + numpy.

Stages (per video, each idempotent and independently resumable)
  decode   gray_1fps.npy         one 1 fps grayscale decode pass via ffmpeg
  states   frames_index.jsonl,   pure numpy: dHash, run-clustering,
           states.jsonl          recurrence groups, narration windows
  extract  keyframes_v2/*.jpg    one full-res JPEG per distinct state

Usage
  .venv/bin/python edu/pipeline/visual_harvest.py
  .venv/bin/python edu/pipeline/visual_harvest.py --list
  .venv/bin/python edu/pipeline/visual_harvest.py --only concept_simple_stoic_setups_sss
  .venv/bin/python edu/pipeline/visual_harvest.py --force states

This file intentionally does not import edu/pipeline/extract_video_knowledge.py
(per spec) so it stands alone; the small set of shared idioms (log/hhmmss/
human/fname_ts, atomic writes, heartbeat-style stage state) are copied here
in the same house style.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------- config

# this file lives in edu/pipeline/, so edu/ is one level up and the repo root two
EDU_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDU_ROOT.parent
DERIVED_ROOT = EDU_ROOT / "derived"

_DEFAULT_VISUAL_HOME = REPO_ROOT / ".artifacts" / "research" / "visual"
VISUAL_HOME = Path(os.environ.get("STOIC_VISUAL_HOME", str(_DEFAULT_VISUAL_HOME))).resolve()
# STOIC_VISUAL_HOME is overridable (e.g. for a scratch relocation during
# testing) but the project contract is absolute: every run artefact lives
# under <repo>/.artifacts/. A misconfigured override must fail loudly, not
# quietly write somewhere the rest of the repo does not expect.
if REPO_ROOT / ".artifacts" not in VISUAL_HOME.parents and VISUAL_HOME != REPO_ROOT / ".artifacts":
    raise RuntimeError(
        f"STOIC_VISUAL_HOME must resolve under {REPO_ROOT / '.artifacts'}, got {VISUAL_HOME}"
    )

SAMPLE_FPS = 1
# WP-V §3.1 fix v2: the original 72x64 (8x the 9x8 dHash grid) only detects
# *global* layout change and is blind to localized change (a drawn level, an
# added bullet line, price action) -- measured at 7-214 missed content
# changes per video absorbed inside a single "state". 288x160 is one cache
# that serves TWO exact-integer reductions with no interpolation:
#   - coarse dHash grid, 8 rows x 9 cols: 20x32 px blocks (160/8=20, 288/9=32)
#   - fine localized-change grid, 8x8 px cells: 20 rows x 36 cols = 720 cells
GRAY_W, GRAY_H = 288, 160
DHASH_ROWS, DHASH_COLS = 8, 9   # classic dHash grid shape, unchanged since v1
FINE_CELL_PX = 8                # fine localized-change cell size in pixels
FINE_ROWS, FINE_COLS = GRAY_H // FINE_CELL_PX, GRAY_W // FINE_CELL_PX  # 20 x 36 = 720 cells
assert GRAY_H % DHASH_ROWS == 0 and GRAY_W % DHASH_COLS == 0, "dHash reduction must be exact"
assert GRAY_H % FINE_CELL_PX == 0 and GRAY_W % FINE_CELL_PX == 0, "fine reduction must be exact"

HAMMING_MAX = 4              # per the plan: dHash Hamming <= 4 joins the same state
# FINE_FRAC chosen 2026-07-26 from the visual_harvest_calibrate.py sweep over 5 videos.
# 0.0075 -> 0.01 is a sensitivity cliff (residual under-split jumps 4.5% -> 17%); 0.005 is the
# only swept value clearing the A8 gate on every video (worst 1.1%) while leaving the 115 s
# SSS slide hold as one state. Under-splitting loses content the VLM never sees and is
# unrecoverable; over-splitting only costs VLM wall time -- so the bias is deliberate.
FINE_DELTA = 6.0             # gray levels a fine cell's mean must move to count as "changed"
FINE_FRAC = 0.005            # fraction of the 720 cells that must change to split a run
JPEG_QUALITY = 2             # ffmpeg -q:v ; 2 = near-best, this feeds OCR
NARRATION_PAD = 15.0         # seconds either side of the state for narration_window
STALL_SECONDS = 900          # a "running" stage with an older heartbeat is dead -> redo
MAX_ATTEMPTS = 3
REP_CANDIDATE_CAP = 600      # cap on frames used for the pairwise representative pick

STAGE_NAMES = ["decode", "states", "extract"]

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


# ------------------------------------------------------------------------------ utils

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def hhmmss(t: float) -> str:
    t = max(0.0, float(t))
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fname_ts(t: float) -> str:
    return hhmmss(t).replace(":", "")


def human(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def write_atomic(path: Path, data: str | bytes) -> None:
    """Write via temp + rename so a partial file can never be mistaken for done."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(tmp, mode, **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as fh:
        fh.write(data)
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    write_atomic(path, json.dumps(obj, indent=2, ensure_ascii=False))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    write_atomic(path, body + ("\n" if body else ""))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------- dHash math

# 8-bit popcount lookup: turns "count set bits in a byte" into an array index,
# so Hamming distance over the 8 dHash bytes is a table lookup + sum, never a
# per-pair Python loop.
POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def compute_dhashes(gray: np.ndarray) -> np.ndarray:
    """Vectorized 64-bit dHash for a batch of (GRAY_H, GRAY_W) gray frames.

    GRAY_W x GRAY_H (288x160) was chosen so this box-reduce is an exact
    integer average of (GRAY_H/DHASH_ROWS) x (GRAY_W/DHASH_COLS) = 20x32 pixel
    blocks -- no interpolation, no resampling artefacts to reason about. (The
    same cache also reduces exactly to the 8x8 px fine grid; see
    compute_fine_cells.) Returns (N, 8) uint8: 8 bytes = 64 bits, row-major,
    MSB = bits[0, 0].
    """
    n = gray.shape[0]
    block_h, block_w = GRAY_H // DHASH_ROWS, GRAY_W // DHASH_COLS
    blocks = gray.reshape(n, DHASH_ROWS, block_h, DHASH_COLS, block_w).astype(np.float32)
    reduced = blocks.mean(axis=(2, 4))              # (n, 8, 9) box-reduced grid
    bits = reduced[:, :, :-1] > reduced[:, :, 1:]    # (n, 8, 8) horizontal gradient -> 64 bits
    packed = np.packbits(bits, axis=-1)              # MSB-first per row -> row-major MSB overall
    return packed.reshape(n, 8)


def dhash_hex(row: np.ndarray) -> str:
    return row.tobytes().hex()


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(POPCOUNT[np.bitwise_xor(a, b)].sum())


def compute_fine_cells(gray: np.ndarray) -> np.ndarray:
    """Vectorized 8x8-pixel box-reduce to a (FINE_ROWS, FINE_COLS) = (20, 36) =
    720-cell grid per frame -- the localized-content-change signal (criterion
    2) that the coarse 64-bit dHash is blind to. Exact integer average of the
    same 288x160 cache the dHash uses; no separate decode. Returns (N,
    FINE_ROWS, FINE_COLS) float32 cell means.
    """
    n = gray.shape[0]
    blocks = gray.reshape(n, FINE_ROWS, FINE_CELL_PX, FINE_COLS, FINE_CELL_PX)
    return blocks.astype(np.float32).mean(axis=(2, 4))


def changed_cell_frac(fine_a: np.ndarray, fine_b: np.ndarray) -> float:
    """Fraction of the 720 fine cells whose mean gray level differs by more
    than FINE_DELTA -- fully vectorized over cells, never a per-cell loop.
    """
    return float((np.abs(fine_a - fine_b) > FINE_DELTA).mean())


def cluster_runs(
    dhashes: np.ndarray, fine: np.ndarray, hamming_max: int, fine_frac: float
) -> list[dict]:
    """Two-criterion anchor-based run clustering (WP-V §3.1 fix v2).

    A frame joins the current run iff BOTH hold against the run *anchor*
    (never the previous frame -- comparing to the anchor, not the previous
    frame, is what stops slow drift from walking a run away from its
    starting look one small step at a time):
      1. hamming(dhash_i, dhash_anchor) <= hamming_max      (global layout)
      2. changed_cell_frac(fine_i, fine_anchor) <= fine_frac (localized content)
    Under-splitting is unrecoverable (a missed state is never seen by the
    downstream VLM pass); over-splitting only costs VLM time. Bias to
    over-split: either criterion failing alone is enough to end the run.

    Returns one dict per run, in order: start/end (inclusive frame/second
    indices), split_reason ("dhash" | "fine" | "eof" -- which criterion ended
    it), and max_fine_frac (the largest changed_cell_frac seen by a frame
    that actually *joined* this run against its anchor).
    """
    n = dhashes.shape[0]
    runs: list[dict] = []
    run_start = 0
    anchor = 0
    max_frac = 0.0
    for i in range(1, n):
        d = hamming(dhashes[i], dhashes[anchor])
        frac = changed_cell_frac(fine[i], fine[anchor])
        if d <= hamming_max and frac <= fine_frac:
            max_frac = max(max_frac, frac)
            continue
        reason = "dhash" if d > hamming_max else "fine"
        runs.append(
            {"start": run_start, "end": i - 1, "split_reason": reason, "max_fine_frac": max_frac}
        )
        run_start = i
        anchor = i
        max_frac = 0.0
    runs.append(
        {"start": run_start, "end": n - 1, "split_reason": "eof", "max_fine_frac": max_frac}
    )
    return runs


# ---------------------------------------------------------- under-split yardstick

# Independent under-split measurement, shared by visual_harvest_audit.py's A8
# check and visual_harvest_calibrate.py's residual-under-split column.
# Deliberately its OWN resolution and thresholds, distinct from
# GRAY_W/H/FINE_DELTA/FINE_FRAC above -- grading the clustering against its
# own numbers would be circular. Copied verbatim from the undersplit_probe.py
# reference measurement that motivated this fix (see wpv_31_fix_spec.md).
YARDSTICK_W, YARDSTICK_H = 256, 144
YARDSTICK_CELL_PX = 8
YARDSTICK_DELTA = 6.0
YARDSTICK_FRAC = 0.01


def yardstick_gray(src: Path) -> np.ndarray:
    """One 1 fps grayscale decode at the yardstick's own resolution -- a
    separate ffmpeg pass from the production GRAY_W x GRAY_H cache."""
    frame_bytes = YARDSTICK_W * YARDSTICK_H
    cmd = [
        FFMPEG, "-v", "error", "-i", str(src),
        "-vf", f"fps={SAMPLE_FPS},scale={YARDSTICK_W}:{YARDSTICK_H},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(out) // frame_bytes
    return np.frombuffer(out[:n * frame_bytes], dtype=np.uint8).reshape(n, YARDSTICK_H, YARDSTICK_W)


def yardstick_changes(src: Path) -> np.ndarray:
    """Seconds at which a content change crosses YARDSTICK_FRAC, per the
    undersplit_probe.py consecutive-second cell-diff metric -- entirely
    independent of the production dHash/fine-cell pipeline."""
    gray = yardstick_gray(src).astype(np.float32)
    n = gray.shape[0]
    cells = gray.reshape(
        n, YARDSTICK_H // YARDSTICK_CELL_PX, YARDSTICK_CELL_PX,
        YARDSTICK_W // YARDSTICK_CELL_PX, YARDSTICK_CELL_PX,
    ).mean(axis=(2, 4))
    diff = np.abs(np.diff(cells, axis=0))
    frac = (diff > YARDSTICK_DELTA).mean(axis=(1, 2))
    return np.where(frac > YARDSTICK_FRAC)[0] + 1


def pairwise_hamming(rows: np.ndarray) -> np.ndarray:
    """Full k x k Hamming distance matrix for a small (k, 8) uint8 batch."""
    xor = rows[:, None, :] ^ rows[None, :, :]
    return POPCOUNT[xor].astype(np.int32).sum(axis=-1)


def evenly_subsample(n_total: int, cap: int) -> np.ndarray:
    """Deterministic, evenly-spaced index subsample of range(n_total), size <= cap."""
    if n_total <= cap:
        return np.arange(n_total)
    idx = np.linspace(0, n_total - 1, cap)
    return np.unique(np.round(idx).astype(int))


# ------------------------------------------------------------------------------- jobs

@dataclass
class VideoJob:
    id: str
    src: Path             # absolute path to the source video
    duration_sec: float
    width: int | None
    height: int | None

    @property
    def out(self) -> Path:
        return VISUAL_HOME / self.id

    @property
    def state_path(self) -> Path:
        return self.out / "state.json"

    @property
    def gray_path(self) -> Path:
        return self.out / "gray_1fps.npy"

    @property
    def frames_index_path(self) -> Path:
        return self.out / "frames_index.jsonl"

    @property
    def states_path(self) -> Path:
        return self.out / "states.jsonl"

    @property
    def keyframes_dir(self) -> Path:
        return self.out / "keyframes_v2"

    @property
    def transcript_path(self) -> Path:
        return DERIVED_ROOT / self.id / "transcript.json"


def discover_jobs() -> list[VideoJob]:
    """Every video is enumerated from edu/derived/*/meta.json (source of truth)."""
    jobs = []
    for meta_path in sorted(DERIVED_ROOT.glob("*/meta.json")):
        meta = read_json(meta_path)
        if not meta or "source" not in meta or "id" not in meta:
            continue
        jobs.append(VideoJob(
            id=meta["id"],
            src=EDU_ROOT / meta["source"],
            duration_sec=float(meta["duration_sec"]),
            width=meta.get("width"),
            height=meta.get("height"),
        ))
    jobs.sort(key=lambda j: j.id)
    return jobs


# ------------------------------------------------------------------------ state engine

class VideoState:
    """Per-video stage tracker: status/attempts/elapsed/heartbeat, one entry per stage."""

    def __init__(self, job: VideoJob):
        self.job = job
        self.path = job.state_path
        self.data = read_json(self.path) or {}
        self.data.setdefault("source", str(job.src.relative_to(EDU_ROOT)))
        self.data.setdefault("stages", {})

    def _flush(self) -> None:
        write_json(self.path, self.data)

    def entry(self, stage: str) -> dict:
        return self.data["stages"].get(stage, {})

    def status(self, stage: str) -> str:
        e = self.entry(stage)
        if not e:
            return "pending"
        if e.get("status") != "running":
            return e.get("status", "pending")
        # A running stage is only real if its heartbeat is fresh; otherwise the
        # process that owned it is gone (killed, crashed, powered off) and the
        # stage must be redone from scratch.
        if (time.time() - e.get("heartbeat", 0)) < STALL_SECONDS:
            return "running"
        log(f"    ! recovering stalled stage '{stage}' (heartbeat stale)")
        e["status"] = "pending"
        self._flush()
        return "pending"

    def attempts(self, stage: str) -> int:
        return self.entry(stage).get("attempts", 0)

    def start(self, stage: str) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(status="running", heartbeat=time.time(), attempts=e.get("attempts", 0) + 1)
        self._flush()

    def beat(self, stage: str) -> None:
        e = self.data["stages"].get(stage)
        if e is not None:
            e["heartbeat"] = time.time()
            self._flush()

    def done(self, stage: str, elapsed_sec: float, **extra) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(
            status="done", elapsed_sec=round(elapsed_sec, 3),
            finished=datetime.now().isoformat(timespec="seconds"), **extra,
        )
        e.pop("error", None)
        self._flush()

    def failed(self, stage: str, elapsed_sec: float, error: str) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(status="failed", elapsed_sec=round(elapsed_sec, 3), error=error[:500])
        self._flush()

    def reset_from(self, stage: str) -> None:
        """Drop `stage` and everything downstream of it (for --force)."""
        idx = STAGE_NAMES.index(stage)
        for name in STAGE_NAMES[idx:]:
            self.data["stages"].pop(name, None)
        self._flush()


# ----------------------------------------------------------------------------- stage: decode

def stage_decode(job: VideoJob, state: VideoState) -> dict:
    """One 1 fps grayscale ffmpeg pass, cached as a single .npy for the states stage.

    Frame i in the resulting array corresponds to video timestamp t = i seconds,
    because the `fps=1` filter samples exactly once per integer second starting
    at t=0. The audit's A1 check verifies this empirically rather than trusting
    the comment.
    """
    frame_bytes = GRAY_W * GRAY_H
    cmd = [
        FFMPEG, "-v", "error", "-i", str(job.src),
        "-vf", f"fps={SAMPLE_FPS},scale={GRAY_W}:{GRAY_H},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    chunks: list[bytes] = []
    while True:
        chunk = proc.stdout.read(frame_bytes)
        if not chunk:
            break
        chunks.append(chunk)
    stderr = proc.stderr.read() if proc.stderr else b""
    returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {stderr.decode(errors='replace')[:300]}")
    if chunks and len(chunks[-1]) != frame_bytes:
        chunks.pop()  # a short trailing read is a partial final frame, not data

    buf = b"".join(chunks)
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(-1, GRAY_H, GRAY_W)
    frame_count = int(arr.shape[0])

    expected = round(job.duration_sec)
    if abs(frame_count - expected) > 2:
        raise RuntimeError(
            f"decode frame_count mismatch: got {frame_count}, expected ~{expected} "
            f"(duration_sec={job.duration_sec})"
        )

    job.out.mkdir(parents=True, exist_ok=True)
    tmp = job.gray_path.with_suffix(".npy.tmp")
    # np.save auto-appends ".npy" to any path that doesn't already end with it,
    # which would silently turn "*.npy.tmp" into "*.npy.tmp.npy" -- passing an
    # open file handle instead of a path bypasses that rewrite.
    with open(tmp, "wb") as fh:
        np.save(fh, arr)
    os.replace(tmp, job.gray_path)
    digest = sha256_file(job.gray_path)
    return {"frame_count": frame_count, "sha256": digest}


# ----------------------------------------------------------------------------- stage: states

def _select_representative(dhashes: np.ndarray, run_start: int, run_end: int) -> int:
    """Pick the most "typical" frame in a run: minimum sum of Hamming distances
    to every other frame considered. A cursor blip or a fade-in/out frame is an
    outlier within its own run and never wins this. Ties go to the later
    timestamp (the slide had more time to settle by then).

    For runs longer than REP_CANDIDATE_CAP frames, both the candidate pool and
    the "every other frame" comparison set are the same deterministic, evenly
    spaced subsample -- an O(n^2) exact computation is unnecessary and this
    keeps the choice reproducible.
    """
    n_total = run_end - run_start + 1
    local_idx = evenly_subsample(n_total, REP_CANDIDATE_CAP)
    candidates = dhashes[run_start + local_idx]
    dist = pairwise_hamming(candidates)
    sums = dist.sum(axis=1)
    best = int(sums.min())
    tied = np.where(sums == best)[0]
    winner_local = int(tied.max())  # later timestamp among ties
    return int(run_start + local_idx[winner_local])


def stage_states(job: VideoJob, state: VideoState) -> dict:
    """Pure-numpy pass over the cached 1 fps gray array: dHash every frame,
    cluster consecutive near-duplicates into runs ("distinct visual states"),
    pick a representative frame per run, group recurring states, and attach
    the narration spoken within +/- NARRATION_PAD seconds of the run.
    """
    gray = np.load(job.gray_path)
    n = gray.shape[0]
    dhashes = compute_dhashes(gray)     # (n, 8) uint8 -- global layout criterion
    fine = compute_fine_cells(gray)     # (n, FINE_ROWS, FINE_COLS) -- localized content criterion

    transcript = read_json(job.transcript_path)
    segments = (transcript or {}).get("segments", [])

    # --- run clustering: two-criterion, anchor-based, walked once in order -
    runs = cluster_runs(dhashes, fine, HAMMING_MAX, FINE_FRAC)

    frame_state_id = np.empty(n, dtype=np.int64)
    frame_representative = np.zeros(n, dtype=bool)
    states: list[dict] = []
    rep_dhash_by_state: list[np.ndarray] = []

    for state_id, run in enumerate(runs):
        r_start, r_end = run["start"], run["end"]
        frame_state_id[r_start:r_end + 1] = state_id
        rep_idx = _select_representative(dhashes, r_start, r_end)
        frame_representative[rep_idx] = True

        t_start, t_end = float(r_start), float(r_end)
        rep_t = float(rep_idx)
        win_lo, win_hi = t_start - NARRATION_PAD, t_end + NARRATION_PAD
        narration = " ".join(
            seg["text"] for seg in segments
            if seg["end"] > win_lo and seg["start"] < win_hi
        )
        narration = re.sub(r"\s+", " ", narration).strip()

        rep_hex = dhash_hex(dhashes[rep_idx])
        rep_dhash_by_state.append(dhashes[rep_idx])
        rep_hms = hhmmss(rep_t)
        states.append({
            "id": f"{job.id}#{state_id:04d}",
            "video": job.id,
            "state_id": state_id,
            "t_start": t_start, "t_end": t_end, "duration_sec": t_end - t_start,
            "hms_start": hhmmss(t_start), "hms_end": hhmmss(t_end),
            "frame_count": r_end - r_start + 1,
            "rep_t": rep_t, "rep_hms": rep_hms,
            "dhash": rep_hex,
            "recur_group": -1,  # filled in below
            "narration_window": narration,
            "source_frame": f"keyframes_v2/{state_id:04d}_{fname_ts(rep_t)}.jpg",
            "split_reason": run["split_reason"],
            "max_fine_frac": round(run["max_fine_frac"], 6),
        })

    # --- recurrence groups: greedy single pass, first matching group wins --
    group_anchors: list[np.ndarray] = []
    for s in states:
        rep = rep_dhash_by_state[s["state_id"]]
        assigned = -1
        for gi, anchor_dhash in enumerate(group_anchors):
            if hamming(rep, anchor_dhash) <= HAMMING_MAX:
                assigned = gi
                break
        if assigned == -1:
            assigned = len(group_anchors)
            group_anchors.append(rep)
        s["recur_group"] = assigned

    # --- writes -------------------------------------------------------------
    frames_index = [
        {
            "t": i, "hms": hhmmss(float(i)), "dhash": dhash_hex(dhashes[i]),
            "state_id": int(frame_state_id[i]), "representative": bool(frame_representative[i]),
        }
        for i in range(n)
    ]
    write_jsonl(job.frames_index_path, frames_index)
    write_jsonl(job.states_path, states)

    # Re-clustering renames representatives, so JPEGs from a previous threshold or cache
    # resolution are now unreferenced. Left in place they would be handed to the VLM as if
    # current -- prune them here, where the new state list is authoritative.
    keep = {s["source_frame"].split("/")[-1] for s in states}
    orphans = [p for p in job.keyframes_dir.glob("*.jpg") if p.name not in keep]
    for p in orphans:
        p.unlink()

    return {"frame_count": n, "state_count": len(states), "orphans_pruned": len(orphans)}


# ----------------------------------------------------------------------------- stage: extract

def _extract_intact(job: VideoJob) -> bool:
    """Cheap on-disk check: does every state's JPEG still exist and non-empty?

    Used to decide whether a "done" extract stage can be trusted as-is or
    must be re-entered to repair frames deleted after the fact.
    """
    states = read_jsonl(job.states_path)
    if not states:
        return False
    return all(
        (job.out / s["source_frame"]).exists() and (job.out / s["source_frame"]).stat().st_size > 0
        for s in states
    )


def stage_extract(job: VideoJob, state: VideoState) -> dict:
    """One ffmpeg input-seek extraction per distinct state, full resolution.

    Resumable at frame granularity: an existing non-empty target is skipped,
    so a killed run (or a deliberately deleted subset of JPEGs) re-extracts
    only what is missing.
    """
    states = read_jsonl(job.states_path)
    job.keyframes_dir.mkdir(parents=True, exist_ok=True)

    todo = []
    for s in states:
        out_path = job.out / s["source_frame"]
        if out_path.exists() and out_path.stat().st_size > 0:
            continue
        todo.append((s, out_path))

    total = len(states)
    start = time.time()
    for done_count, (s, out_path) in enumerate(todo, 1):
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        cmd = [
            FFMPEG, "-v", "error", "-ss", str(s["rep_t"]), "-i", str(job.src),
            "-frames:v", "1", "-q:v", str(JPEG_QUALITY), "-f", "image2", "-y", str(tmp),
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"extract failed for state {s['id']}: {proc.stderr.decode(errors='replace')[:300]}"
            )
        os.replace(tmp, out_path)

        if done_count % 100 == 0 or done_count == len(todo):
            elapsed = time.time() - start
            rate = done_count / elapsed if elapsed > 0 else 0
            remaining = len(todo) - done_count
            eta = remaining / rate if rate > 0 else 0
            state.beat("extract")
            log(f"    extract {done_count}/{len(todo)} (skipped {total - len(todo)} already done)"
                f"  elapsed {human(elapsed)}  eta {human(eta)}")

    return {"total_states": total, "extracted_this_run": len(todo), "skipped": total - len(todo)}


STAGES = [
    ("decode", stage_decode),
    ("states", stage_states),
    ("extract", stage_extract),
]


# ------------------------------------------------------------------------------ driver

def process_video(job: VideoJob, tracker: ProgressTracker, pos: int, total: int) -> bool:
    """Run every pending stage of one video in order. Returns True iff the
    video ends fully done (all stages 'done')."""
    job.out.mkdir(parents=True, exist_ok=True)
    state = VideoState(job)
    ok = True

    for name, fn in STAGES:
        status = state.status(name)
        # decode/states are all-or-nothing: once done, never revisited. extract
        # is different -- files placed on disk can be deleted out from under a
        # "done" stage (the kill-and-resume contract in the spec), so a done
        # extract still gets a cheap on-disk integrity check every run; only a
        # video whose frames are still all intact is truly skipped, so a plain
        # resumed run with nothing missing prints nothing for this stage.
        if status == "done":
            if name != "extract" or _extract_intact(job):
                continue
            log("    extract: marked done but frame(s) missing on disk, repairing")
        if status == "running":
            log(f"    {name}: already running (heartbeat fresh), skipping video")
            return False
        if status == "failed" and state.attempts(name) >= MAX_ATTEMPTS:
            log(f"    {name}: failed {state.attempts(name)}x, giving up on this video")
            return False

        stage_start = time.time()
        state.start(name)
        try:
            extra = fn(job, state)
        except Exception as exc:
            elapsed = time.time() - stage_start
            state.failed(name, elapsed, f"{type(exc).__name__}: {exc}")
            log(f"    {name}: FAILED ({type(exc).__name__}: {str(exc)[:200]})")
            ok = False
            break
        elapsed = time.time() - stage_start
        state.done(name, elapsed, **extra)
        tracker.work_wall_elapsed += elapsed

        if name == STAGE_NAMES[-1]:
            # this video is now fully done -- count it before printing the
            # final stage's own line, so that line's percentage reflects it
            tracker.mark_video_done(job)
        tracker.log_stage_line(job, pos, total, name, elapsed)

    if ok:
        tracker.mark_video_done(job)  # safety net; idempotent if already counted above
    return ok


class ProgressTracker:
    """Corpus-wide progress bookkeeping for the per-stage log line (spec §4).

    `cumulative_done_seconds` reflects true corpus progress (videos fully
    finished, including ones already done before this process started) so the
    displayed percentage always describes "how far through the whole 16-video
    corpus", independent of any --only filter. Throughput for the ETA, by
    contrast, is scoped to *this run's own* work only: `work_done_seconds` and
    `work_wall_elapsed` are both zero until a video this run actually
    processes finishes, so an already-done video that gets skipped in a
    fraction of a second cannot pollute the rate estimate in either direction.
    """

    def __init__(self, all_jobs: list[VideoJob]):
        self.grand_total = sum(j.duration_sec for j in all_jobs) or 1.0
        self.cumulative_done_seconds = 0.0
        for j in all_jobs:
            st = VideoState(j)
            if all(st.status(name) == "done" for name in STAGE_NAMES):
                self.cumulative_done_seconds += j.duration_sec
        self.work_done_seconds = 0.0
        self.work_wall_elapsed = 0.0
        self.run_start = time.time()
        self._done_at_start: set[str] = {
            j.id for j in all_jobs
            if all(VideoState(j).status(name) == "done" for name in STAGE_NAMES)
        }

    def log_stage_line(
        self, job: VideoJob, pos: int, total: int, stage: str, elapsed: float
    ) -> None:
        pct = 100.0 * self.cumulative_done_seconds / self.grand_total
        run_elapsed = time.time() - self.run_start
        throughput = (
            self.work_done_seconds / self.work_wall_elapsed if self.work_wall_elapsed > 0 else 0.0
        )
        remaining = max(0.0, self.grand_total - self.cumulative_done_seconds)
        eta = remaining / throughput if throughput > 0 else 0.0
        log(
            f"[{pos:2d}/{total}] {job.id}  {stage} {elapsed:.1f}s"
            f"  | video {int(self.cumulative_done_seconds)}s/{int(self.grand_total)}s ({pct:.1f}%)"
            f"  | elapsed {human(run_elapsed)}  ETA {human(eta) if throughput > 0 else 'n/a'}"
        )

    def mark_video_done(self, job: VideoJob) -> None:
        if job.id in self._done_at_start:
            return  # already counted before this run started; no double count
        self.cumulative_done_seconds += job.duration_sec
        self.work_done_seconds += job.duration_sec
        self._done_at_start.add(job.id)  # a video only finishes once per run


# ------------------------------------------------------------------------------ manifest

def build_manifest(all_jobs: list[VideoJob]) -> dict:
    videos = []
    for j in all_jobs:
        state = VideoState(j)
        stages = {name: state.entry(name).get("status", "pending") for name in STAGE_NAMES}
        decode_e = state.entry("decode")
        states_e = state.entry("states")
        extract_e = state.entry("extract")
        videos.append({
            "id": j.id,
            "duration_sec": j.duration_sec,
            "stages": stages,
            "frame_count": decode_e.get("frame_count"),
            "state_count": states_e.get("state_count"),
            "extract_total_states": extract_e.get("total_states"),
            "extract_skipped": extract_e.get("skipped"),
            "elapsed_sec": {name: state.entry(name).get("elapsed_sec") for name in STAGE_NAMES},
        })
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "video_count": len(all_jobs),
        "videos": videos,
    }


def write_manifest(all_jobs: list[VideoJob]) -> None:
    write_json(VISUAL_HOME / "manifest.json", build_manifest(all_jobs))


def write_harvest_report(all_jobs: list[VideoJob]) -> None:
    manifest = build_manifest(all_jobs)
    total_frames = sum(v["frame_count"] or 0 for v in manifest["videos"])
    total_states = sum(v["state_count"] or 0 for v in manifest["videos"])
    done_videos = sum(
        1 for v in manifest["videos"] if all(v["stages"][n] == "done" for n in STAGE_NAMES)
    )
    write_json(VISUAL_HOME / "harvest_report.json", {
        "generated": manifest["generated"],
        "video_count": len(all_jobs),
        "videos_fully_done": done_videos,
        "total_frames_sampled": total_frames,
        "total_states": total_states,
        "compression_ratio": round(total_frames / total_states, 2) if total_states else None,
    })


# --------------------------------------------------------------------------------- CLI

def print_list(all_jobs: list[VideoJob]) -> None:
    for j in all_jobs:
        state = VideoState(j)
        marks = " ".join(f"{n}={state.entry(n).get('status', '-')}" for n in STAGE_NAMES)
        print(f"{j.id}  ({human(j.duration_sec)})\n    {marks}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", help="substring filter on the video id")
    ap.add_argument(
        "--force", choices=STAGE_NAMES, help="redo this stage and everything downstream"
    )
    ap.add_argument("--list", action="store_true", help="show videos and stage status, then exit")
    args = ap.parse_args()

    VISUAL_HOME.mkdir(parents=True, exist_ok=True)
    all_jobs = discover_jobs()
    if not all_jobs:
        log("no videos found under edu/derived/*/meta.json")
        return 1

    if args.list:
        print_list(all_jobs)
        return 0

    jobs = all_jobs
    if args.only:
        needle = args.only.lower()
        jobs = [j for j in all_jobs if needle in j.id.lower()]
    if not jobs:
        log(f"no video id matches --only {args.only!r}")
        return 1

    if args.force:
        for j in jobs:
            VideoState(j).reset_from(args.force)

    footage = human(sum(j.duration_sec for j in jobs))
    log(f"{len(jobs)}/{len(all_jobs)} video(s) selected, {footage} of footage")
    tracker = ProgressTracker(all_jobs)

    ok = failed = 0
    for pos, job in enumerate(jobs, 1):
        log(f"[{pos}/{len(jobs)}] {job.id}")
        if process_video(job, tracker, pos, len(jobs)):
            ok += 1
        else:
            failed += 1
        write_manifest(all_jobs)

    write_harvest_report(all_jobs)
    log("")
    log(f"finished: {ok} ok, {failed} incomplete")
    log(f"output: {VISUAL_HOME}")
    if failed:
        log("rerun the same command to retry incomplete videos")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
