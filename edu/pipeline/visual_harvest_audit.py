#!/usr/bin/env python3
"""
WP-V §3.1 audit gate (ADR-0021: every derived number is presumed invalid until
adversarially audited).

Reports counts, never verdicts. Eight checks (A1-A8); A1, A2, A3, A5, A6, A8
are HARD -- a failure there means the harvest cannot be trusted downstream and
the process exits non-zero. A4 and A7 are soft: they surface numbers for a
human to eyeball (held slides, dedupe shape) and never fail the run.

A check whose prerequisite video was never harvested (e.g. this ran with
--only restricting the corpus to one video) is reported as "skipped", not
"failed" -- absence of data is not the same claim as a verified defect.

Usage
  .venv/bin/python edu/pipeline/visual_harvest_audit.py
  .venv/bin/python edu/pipeline/visual_harvest_audit.py --only concept_simple_stoic_setups_sss
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from visual_harvest import (
    FFMPEG,
    FFPROBE,
    GRAY_H,
    GRAY_W,
    SAMPLE_FPS,
    VISUAL_HOME,
    VideoJob,
    compute_dhashes,
    dhash_hex,
    discover_jobs,
    hamming,
    human,
    log,
    read_json,
    read_jsonl,
    sha256_file,
    write_json,
    yardstick_changes,
)

SEED = 0
KNOWN_SLIDE_VIDEO = "concept_simple_stoic_setups_sss"
# WP-V §3.1 fix v2: the First Red/Green Day slide is held continuously from
# 2105 s to 2220 s (verified visually at 2108/2120/2150/2175/2210 s -- the
# original plan note's "00:35:12-00:35:57" i.e. 2112-2157 is stale, derived
# from two old sparse keyframes). KNOWN_SLIDE_TARGET below is a sub-window
# fully inside that verified hold, not the full extent of it: the HARD gate
# asserts one state contiguously covers this sub-window, rather than the
# exact (unverified second-by-second) boundary of the true hold.
KNOWN_SLIDE_FULL_HOLD = (2105.0, 2220.0)
KNOWN_SLIDE_TARGET = (2112.0, 2157.0)
KNOWN_SLIDE_MIN_DURATION = 45.0  # t_end - t_start of the target sub-window


def pct(share: float | None) -> str:
    return "n/a" if share is None else f"{share:.1%}"


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, round(p * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def redecode_gray(src: Path) -> np.ndarray:
    """Independently re-run the same 1 fps gray decode ffmpeg would produce.

    Used only by A5 (determinism) -- the point is to prove the *pipeline* is
    reproducible bit-for-bit, so this deliberately mirrors stage_decode's
    ffmpeg invocation rather than reading a cached result.
    """
    frame_bytes = GRAY_W * GRAY_H
    cmd = [
        FFMPEG, "-v", "error", "-i", str(src),
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
    if proc.wait() != 0:
        raise RuntimeError(f"redecode failed: {stderr.decode(errors='replace')[:300]}")
    if chunks and len(chunks[-1]) != frame_bytes:
        chunks.pop()
    buf = b"".join(chunks)
    return np.frombuffer(buf, dtype=np.uint8).reshape(-1, GRAY_H, GRAY_W)


def jpg_dhash(jpg_path: Path) -> str | None:
    """Re-derive a dHash straight from a saved JPEG, independent of any
    cached array -- this is what actually checks the ffmpeg seek landed on
    the frame the harvest thinks it did."""
    cmd = [
        FFMPEG, "-v", "error", "-i", str(jpg_path),
        "-vf", f"scale={GRAY_W}:{GRAY_H},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    expected = GRAY_W * GRAY_H
    if proc.returncode != 0 or len(proc.stdout) < expected:
        return None
    arr = np.frombuffer(proc.stdout[:expected], dtype=np.uint8).reshape(1, GRAY_H, GRAY_W)
    return dhash_hex(compute_dhashes(arr)[0])


# --------------------------------------------------------------------------------- A1

def check_a1(jobs: list[VideoJob]) -> dict:
    videos = []
    for j in jobs:
        if not j.gray_path.exists() or not j.frames_index_path.exists():
            videos.append({"video": j.id, "status": "not_run"})
            continue
        npy_count = int(np.load(j.gray_path, mmap_mode="r").shape[0])
        idx_rows = read_jsonl(j.frames_index_path)
        idx_count = len(idx_rows)
        ts = [r["t"] for r in idx_rows]
        ascending_step1 = ts == list(range(len(ts)))
        expected = round(j.duration_sec)
        count_match = npy_count == idx_count and abs(npy_count - expected) <= 2
        ok = count_match and ascending_step1
        videos.append({
            "video": j.id, "status": "checked", "ok": ok,
            "npy_frame_count": npy_count, "idx_row_count": idx_count,
            "expected_duration_round": expected, "ascending_step1": ascending_step1,
        })
    checked = [v for v in videos if v["status"] == "checked"]
    return {
        "hard_pass": all(v["ok"] for v in checked) if checked else True,
        "checked_count": len(checked),
        "skipped_count": len(videos) - len(checked),
        "videos": videos,
    }


# --------------------------------------------------------------------------------- A2

PHASE_OFFSET_RANGE = range(-2, 3)  # rep_t-2 .. rep_t+2, per spec

# WP-V §3.1 fix v3 -- what A2 asks, and why the earlier form was unanswerable.
#
# The question is: is the JPEG handed to the VLM really the frame the harvest
# clustered? v2 answered it with argmin(Hamming) over rep_t +/- 2 and gated on
# that argmin being 0. But over HELD content every candidate second is
# byte-identical, so every candidate ties at the same distance and the "argmin"
# is decided entirely by the tie-break rule -- it measured the tie-break, not a
# seek phase. (An early probe scored -2 in 52/60 cases purely by preferring the
# more-negative offset.) A number that clean out of a degenerate comparison is
# the ADR-0021 symptom of a broken generator.
#
# The answerable question is a membership test, not an argmin: is rep_t AMONG
# the minimum-Hamming candidates? Ties then count as success, which is the
# correct reading -- indistinguishable seconds mean the seek cannot be wrong.
#
# That membership test alone is weak on its own, and measuring it says so: fed
# a JPEG from a state >= 60 s away, it still "passes" 64 % of the time, because
# a wholly wrong frame is roughly equally wrong at all five candidate seconds
# and so ties them. It can only see misalignment of <= 2 s, by construction. So
# it is paired with an absolute bound on the distance AT rep_t. Bucketing is
# what makes that bound usable: over held states the true distribution is
# median 0 / p95 2 / max 5 against 24 / 31 / 40 for a deliberately wrong frame,
# where the old corpus-wide sample's fat tail (p95 15) made any absolute bound
# look untenable. The bound itself is the v2 spec's 8, not a number fitted to
# this data.
#
# Buckets by state duration, because the answer is only meaningful for one of
# them. On a 1-second state the content genuinely changes within the second, so
# a +/-1 frame ambiguity is inherent to seeking rather than a defect; gating on
# it would gate on video motion. So: gate the held bucket, report the rest.
A2_BUCKET_SAMPLE = 60           # per bucket, per run
A2_GATED_BUCKET = "held_ge_10s"
A2_MIN_SHARE = 0.90             # of held samples, for both gated metrics
A2_MAX_HAMMING_AT_REP = 8       # absolute per-sample bound, inherited from the v2 spec
A2_LOW_SAMPLE_N = 30            # below this the shares are reported as weak, not trusted


def _duration_bucket(duration_sec: float) -> str:
    """duration_sec is t_end - t_start, so a single-second state is 0.0."""
    if duration_sec >= 10.0:
        return A2_GATED_BUCKET
    if duration_sec > 0.0:
        return "mid_1_to_9s"
    return "single_second"


A2_BUCKET_ORDER = [A2_GATED_BUCKET, "mid_1_to_9s", "single_second"]


def _rep_alignment(fresh_hex: str, state: dict, frame_lookup: dict[int, str]) -> dict | None:
    """Hamming distance from the JPEG's freshly derived dHash to the cached
    per-second dHash at each of rep_t-2 .. rep_t+2, whether rep_t is among the
    minimum-distance candidates, and whether every best-matching second still
    falls inside the state's own [t_start, t_end]. None if rep_t itself is not
    in the index (which A6 would already have failed on).

    best_inside_span is the consequence-level question behind A2: even where
    the seek lands a second off, the JPEG still shows this state's content and
    the VLM is not handed a frame belonging to a neighbouring state. For a
    1-second state the span is one second, so it necessarily collapses to
    rep_optimal -- reported, not gated, for exactly that reason.
    """
    fresh = np.frombuffer(bytes.fromhex(fresh_hex), dtype=np.uint8)
    rep_t = state["rep_t"]
    rep_t_int = round(rep_t)
    by_offset: dict[int, int] = {}
    for off in PHASE_OFFSET_RANGE:
        cand_hex = frame_lookup.get(rep_t_int + off)
        if cand_hex is None:
            continue
        cand = np.frombuffer(bytes.fromhex(cand_hex), dtype=np.uint8)
        by_offset[off] = hamming(fresh, cand)
    if 0 not in by_offset:
        return None
    d_rep = by_offset[0]
    d_min = min(by_offset.values())
    best = [off for off, d in by_offset.items() if d == d_min]
    return {
        "hamming_at_rep": d_rep,
        "hamming_min": d_min,
        "excess": d_rep - d_min,
        "rep_optimal": d_rep == d_min,
        "close_at_rep": d_rep <= A2_MAX_HAMMING_AT_REP,
        "best_inside_span": any(
            state["t_start"] <= rep_t + off <= state["t_end"] for off in best
        ),
        "candidates": len(by_offset),
        "tied_at_min": sum(1 for d in by_offset.values() if d == d_min),
    }


def _bucket_sample(
    eligible: list[VideoJob], per_video_states: dict[str, list[dict]],
    bucket: str, rng: random.Random,
) -> list[tuple[VideoJob, dict]]:
    """Even per-video quota over one duration bucket, so a slide-heavy video
    cannot be drowned out by the live sessions (which hold 70 % of all states
    but almost none of the held ones). rng is walked in sorted-job order.
    """
    population = {
        j.id: [s for s in per_video_states[j.id] if _duration_bucket(s["duration_sec"]) == bucket]
        for j in eligible
    }
    non_empty = [j for j in eligible if population[j.id]]
    if not non_empty:
        return []
    base, remainder = divmod(A2_BUCKET_SAMPLE, len(non_empty))
    picks: list[tuple[VideoJob, dict]] = []
    for i, j in enumerate(non_empty):
        states = population[j.id]
        quota = min(base + (1 if i < remainder else 0), len(states))
        chosen = rng.sample(states, quota) if quota < len(states) else list(states)
        picks.extend((j, s) for s in chosen)
    return picks


def check_a2(jobs: list[VideoJob]) -> dict:
    eligible = [j for j in jobs if j.states_path.exists()]
    if not eligible:
        return {"hard_pass": True, "status": "skipped", "reason": "no video has states.jsonl yet"}

    per_video_states = {j.id: read_jsonl(j.states_path) for j in eligible}
    frame_lookup_cache: dict[str, dict[int, str]] = {}

    def frame_lookup(job: VideoJob) -> dict[int, str]:
        if job.id not in frame_lookup_cache:
            rows = read_jsonl(job.frames_index_path) if job.frames_index_path.exists() else []
            frame_lookup_cache[job.id] = {r["t"]: r["dhash"] for r in rows}
        return frame_lookup_cache[job.id]

    rng = random.Random(SEED)  # one RNG, walked in fixed bucket-then-job order
    unreadable: list[str] = []
    no_candidates: list[str] = []
    # states.jsonl's own dhash must equal the frames_index entry at rep_t -- if
    # those two disagree the whole comparison below is against the wrong row.
    index_mismatch: list[str] = []
    buckets: dict[str, dict] = {}

    for bucket in A2_BUCKET_ORDER:
        picks = _bucket_sample(eligible, per_video_states, bucket, rng)
        rows: list[dict] = []
        for j, s in picks:
            jpg = j.out / s["source_frame"]
            fresh_hex = jpg_dhash(jpg) if jpg.exists() else None
            if fresh_hex is None:
                unreadable.append(s["id"])
                continue
            lookup = frame_lookup(j)
            if lookup.get(round(s["rep_t"])) != s["dhash"]:
                index_mismatch.append(s["id"])
            row = _rep_alignment(fresh_hex, s, lookup)
            if row is None:
                no_candidates.append(s["id"])
                continue
            rows.append(row)

        n = len(rows)
        at_rep = sorted(r["hamming_at_rep"] for r in rows)
        excess_hist: dict[int, int] = {}
        for r in rows:
            excess_hist[r["excess"]] = excess_hist.get(r["excess"], 0) + 1

        def share_of(key: str, rows: list[dict] = rows, n: int = n) -> float | None:
            return round(sum(1 for r in rows if r[key]) / n, 4) if n else None

        buckets[bucket] = {
            "population": sum(
                1 for st in per_video_states.values() for s in st
                if _duration_bucket(s["duration_sec"]) == bucket
            ),
            "sampled": n,
            "rep_optimal": sum(1 for r in rows if r["rep_optimal"]),
            "rep_optimal_share": share_of("rep_optimal"),
            "close_at_rep_share": share_of("close_at_rep"),
            "best_inside_span_share": share_of("best_inside_span"),
            "hamming_at_rep_median": percentile(at_rep, 0.5),
            "hamming_at_rep_p95": percentile(at_rep, 0.95),
            "hamming_at_rep_max": at_rep[-1] if at_rep else None,
            "excess_histogram": dict(sorted(excess_hist.items())),
            "mean_tied_at_min": (
                round(sum(r["tied_at_min"] for r in rows) / n, 2) if n else None
            ),
        }

    gated = buckets[A2_GATED_BUCKET]
    low_sample = 0 < gated["sampled"] < A2_LOW_SAMPLE_N
    if gated["sampled"] == 0:
        # no held state in the selected corpus (e.g. --only on a live session):
        # absence of data is not a verified defect
        gate_pass, gate_note = True, "skipped: no state held >= 10 s in the selected videos"
    else:
        gate_pass = all(
            gated[k] is not None and gated[k] >= A2_MIN_SHARE
            for k in ("rep_optimal_share", "close_at_rep_share")
        )
        gate_note = "low sample -- gate is weak" if low_sample else "ok"

    hard_pass = gate_pass and not unreadable and not index_mismatch and not no_candidates
    return {
        "hard_pass": hard_pass, "status": "checked",
        "gate": (
            f"of states held >= 10 s, >= {A2_MIN_SHARE:.0%} have rep_t among the min-Hamming "
            f"candidates AND hamming(JPEG, cached rep_t) <= {A2_MAX_HAMMING_AT_REP}; "
            f"other buckets reported, not gated"
        ),
        "gate_note": gate_note, "low_sample": low_sample,
        "bucket_sample_target": A2_BUCKET_SAMPLE,
        "unreadable_count": len(unreadable), "unreadable": unreadable,
        "index_mismatch_count": len(index_mismatch), "index_mismatch": index_mismatch,
        "no_candidate_count": len(no_candidates), "no_candidates": no_candidates,
        "buckets": buckets,
    }


# --------------------------------------------------------------------------------- A3

def check_a3(jobs: list[VideoJob]) -> dict:
    """Known-slide recall, corrected ground truth (WP-V §3.1 fix v2).

    v1 only required a state to *overlap* [2100, 2170] with rep_t inside
    [2112, 2157] -- that passes even if the hold got shattered into several
    short states, exactly the under-split failure mode this fix targets. The
    corrected gate requires a SINGLE state to CONTIGUOUSLY COVER the target
    sub-window (its own rep_t inside its own span, duration >= 45 s).
    """
    job = next((j for j in jobs if j.id == KNOWN_SLIDE_VIDEO), None)
    if job is None or not job.states_path.exists():
        return {
            "hard_pass": True, "status": "skipped",
            "reason": f"{KNOWN_SLIDE_VIDEO} not in the selected/harvested job set",
        }
    states = read_jsonl(job.states_path)
    lo, hi = KNOWN_SLIDE_FULL_HOLD
    overlapping = [s for s in states if s["t_end"] >= lo and s["t_start"] <= hi]

    t_lo, t_hi = KNOWN_SLIDE_TARGET
    covering_candidates = [s for s in states if s["t_start"] <= t_lo and s["t_end"] >= t_hi]
    if not covering_candidates:
        return {
            "hard_pass": False, "status": "checked",
            "overlapping": overlapping, "covering_candidates": [],
            "reason": f"no single state covers [{t_lo}, {t_hi}] contiguously",
        }
    # more than one state fully containing the sub-window would itself be a
    # bug (states in a run-clustering pass cannot nest) -- surfaced, not hidden
    covering = covering_candidates[0]
    rep_in_span = covering["t_start"] <= covering["rep_t"] <= covering["t_end"]
    duration_ok = covering["duration_sec"] >= KNOWN_SLIDE_MIN_DURATION
    hard_pass = rep_in_span and duration_ok and len(covering_candidates) == 1
    return {
        "hard_pass": hard_pass, "status": "checked",
        "overlapping": overlapping,
        "covering_candidate_count": len(covering_candidates),
        "covering_state_id": covering["state_id"], "covering_rep_t": covering["rep_t"],
        "covering_duration_sec": covering["duration_sec"],
        "rep_in_span": rep_in_span, "duration_ok": duration_ok,
    }


# --------------------------------------------------------------------------------- A4

def check_a4(jobs: list[VideoJob]) -> dict:
    videos = []
    for j in jobs:
        if not j.states_path.exists():
            continue
        states = read_jsonl(j.states_path)
        frames_sampled = (
            int(np.load(j.gray_path, mmap_mode="r").shape[0]) if j.gray_path.exists() else None
        )
        n_states = len(states)
        durations = sorted(s["duration_sec"] for s in states)
        single_sec = sum(1 for d in durations if d == 0.0)
        share = (single_sec / n_states) if n_states else 0.0
        videos.append({
            "video": j.id, "frames_sampled": frames_sampled, "states": n_states,
            "compression_ratio": (
                round(frames_sampled / n_states, 2) if frames_sampled and n_states else None
            ),
            "duration_min": durations[0] if durations else None,
            "duration_median": percentile(durations, 0.5),
            "duration_p95": percentile(durations, 0.95),
            "duration_max": durations[-1] if durations else None,
            "single_second_states": single_sec, "single_second_share": round(share, 3),
            "flag_low_states": n_states < 20,
            "flag_high_single_second_share": share > 0.30,
        })
    totals = {
        "videos_checked": len(videos),
        "total_frames_sampled": sum(v["frames_sampled"] or 0 for v in videos),
        "total_states": sum(v["states"] for v in videos),
        "flagged_videos": [
            v["video"] for v in videos if v["flag_low_states"] or v["flag_high_single_second_share"]
        ],
    }
    return {"hard_pass": True, "videos": videos, "totals": totals}  # soft: informational only


# --------------------------------------------------------------------------------- A5

def check_a5(jobs: list[VideoJob]) -> dict:
    eligible = [j for j in jobs if j.gray_path.exists()]
    if not eligible:
        return {
            "hard_pass": True, "status": "skipped", "reason": "no video has a decode result yet",
        }
    shortest = min(eligible, key=lambda j: j.duration_sec)
    state_data = read_json(shortest.state_path) or {}
    stored_sha = state_data.get("stages", {}).get("decode", {}).get("sha256")
    if not stored_sha:
        return {
            "hard_pass": False, "status": "checked", "video": shortest.id,
            "reason": "no decode.sha256 recorded in state.json",
        }
    tmp_dir = VISUAL_HOME / "_audit_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{shortest.id}_redecode.npy"
    arr = redecode_gray(shortest.src)
    np.save(tmp_path, arr)
    fresh_sha = sha256_file(tmp_path)
    match = fresh_sha == stored_sha
    return {
        "hard_pass": match, "status": "checked", "video": shortest.id,
        "duration_sec": shortest.duration_sec,
        "stored_sha256": stored_sha, "redecoded_sha256": fresh_sha,
    }


# --------------------------------------------------------------------------------- A6

def check_a6(jobs: list[VideoJob]) -> dict:
    videos = []
    for j in jobs:
        if not j.states_path.exists():
            continue
        states = read_jsonl(j.states_path)
        idx_rows = read_jsonl(j.frames_index_path) if j.frames_index_path.exists() else []
        state_ids_in_index: set[int] = set()
        rep_rows_by_state: dict[int, list[dict]] = {}
        for r in idx_rows:
            state_ids_in_index.add(r["state_id"])
            if r["representative"]:
                rep_rows_by_state.setdefault(r["state_id"], []).append(r)

        expected_w = j.width or 1920
        expected_h = j.height or 1080
        missing_files, too_small, bad_res = [], [], []
        missing_in_index, rep_count_wrong, rep_t_mismatch = [], [], []

        for s in states:
            frame_path = j.out / s["source_frame"]
            if not frame_path.exists():
                missing_files.append(s["id"])
                continue
            if frame_path.stat().st_size <= 5000:
                too_small.append(s["id"])
            proc = subprocess.run(
                [FFPROBE, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(frame_path)],
                capture_output=True,
            )
            ok_res = False
            if proc.returncode == 0:
                try:
                    w, h = (int(x) for x in proc.stdout.decode().strip().split(","))
                    ok_res = (w, h) == (expected_w, expected_h)
                except ValueError:
                    ok_res = False
            if not ok_res:
                bad_res.append(s["id"])
            if s["state_id"] not in state_ids_in_index:
                missing_in_index.append(s["id"])
            reps = rep_rows_by_state.get(s["state_id"], [])
            if len(reps) != 1:
                rep_count_wrong.append(s["id"])
            elif reps[0]["t"] != s["rep_t"]:
                rep_t_mismatch.append(s["id"])

        ok = not any(
            [missing_files, too_small, bad_res, missing_in_index, rep_count_wrong, rep_t_mismatch]
        )
        videos.append({
            "video": j.id, "state_count": len(states), "ok": ok,
            "missing_files": missing_files, "too_small": too_small, "bad_resolution": bad_res,
            "missing_in_index": missing_in_index, "rep_count_wrong": rep_count_wrong,
            "rep_t_mismatch": rep_t_mismatch,
        })
    return {"hard_pass": all(v["ok"] for v in videos) if videos else True, "videos": videos}


# --------------------------------------------------------------------------------- A7

def check_a7(jobs: list[VideoJob]) -> dict:
    all_states = []
    for j in jobs:
        if j.states_path.exists():
            all_states.extend(read_jsonl(j.states_path))
    top = sorted(all_states, key=lambda s: -s["duration_sec"])[:15]
    rows = [
        {
            "video": s["video"], "state_id": s["state_id"],
            "hms_start": s["hms_start"], "hms_end": s["hms_end"],
            "duration_sec": s["duration_sec"],
            "narration_snippet": s["narration_window"][:150],
        }
        for s in top
    ]
    return {"hard_pass": True, "top": rows}


# --------------------------------------------------------------------------------- A8

# HARD gate threshold for the shared yardstick_changes() measurement (see
# visual_harvest.py) -- kept local to the audit since it's a pass/fail bar,
# not part of the yardstick metric itself.
A8_MAX_INSIDE_SHARE = 0.05


def check_a8(jobs: list[VideoJob]) -> dict:
    """Residual under-split, per video: how many of the yardstick's
    independent content-change detections still land inside a state rather
    than at its boundary. Fails HARD if any video exceeds A8_MAX_INSIDE_SHARE.
    """
    videos = []
    for j in jobs:
        if not j.states_path.exists():
            continue
        states = read_jsonl(j.states_path)
        changes = yardstick_changes(j.src)
        bounds = {int(s["t_start"]) for s in states}
        inside = [int(t) for t in changes if int(t) not in bounds]
        inside_share = (len(inside) / len(changes)) if len(changes) else 0.0
        videos.append({
            "video": j.id, "states": len(states),
            "changes_total": len(changes), "changes_inside": len(inside),
            "inside_share": round(inside_share, 4),
            "ok": inside_share <= A8_MAX_INSIDE_SHARE,
        })
    return {
        "hard_pass": all(v["ok"] for v in videos) if videos else True,
        "max_inside_share": A8_MAX_INSIDE_SHARE,
        "videos": videos,
    }


# --------------------------------------------------------------------------------- report

HARD_CHECK_IDS = ["A1", "A2", "A3", "A5", "A6", "A8"]


def print_report(results: dict) -> None:
    print()
    print("=" * 88)
    print("WP-V audit_31 — deterministic frame harvest")
    print("=" * 88)

    a1 = results["A1"]
    print(f"\nA1 coverage  [{'HARD'}]  checked={a1['checked_count']} skipped={a1['skipped_count']}"
          f"  pass={a1['hard_pass']}")
    for v in a1["videos"]:
        if v["status"] == "not_run":
            print(f"    {v['video']:55s} not_run")
        else:
            print(f"    {v['video']:55s} npy={v['npy_frame_count']:6d} idx={v['idx_row_count']:6d}"
                  f" expected~{v['expected_duration_round']:6d} ascending={v['ascending_step1']}"
                  f" ok={v['ok']}")

    a2 = results["A2"]
    print(f"\nA2 seek alignment  [HARD]  pass={a2['hard_pass']}")
    if a2.get("status") == "skipped":
        print(f"    skipped: {a2['reason']}")
    else:
        print(f"    gate: {a2['gate']}  ({a2['gate_note']})")
        print(f"    unreadable={a2['unreadable_count']} index_mismatch={a2['index_mismatch_count']}"
              f" no_candidates={a2['no_candidate_count']}")
        for name in A2_BUCKET_ORDER:
            b = a2["buckets"][name]
            mark = " [GATED]" if name == A2_GATED_BUCKET else ""
            print(f"    {name:14s} pop={b['population']:5d} sampled={b['sampled']:3d}"
                  f"  rep_optimal={pct(b['rep_optimal_share'])}"
                  f" close@rep={pct(b['close_at_rep_share'])}"
                  f" best_inside_span={pct(b['best_inside_span_share'])}{mark}")
            print(f"    {'':14s} hamming@rep med/p95/max={b['hamming_at_rep_median']}"
                  f"/{b['hamming_at_rep_p95']}/{b['hamming_at_rep_max']}"
                  f"  excess={b['excess_histogram']}  mean_ties={b['mean_tied_at_min']}")

    a3 = results["A3"]
    print(f"\nA3 known-slide recall  [HARD]  pass={a3['hard_pass']}")
    if a3.get("status") == "skipped":
        print(f"    skipped: {a3['reason']}")
    else:
        print(f"    states overlapping full hold {KNOWN_SLIDE_FULL_HOLD}:")
        for s in a3["overlapping"]:
            print(f"      state#{s['state_id']:04d} [{s['hms_start']}-{s['hms_end']}] "
                  f"rep_t={s['rep_t']} dur={s['duration_sec']}s split={s.get('split_reason')}")
        if "reason" in a3:
            print(f"    FAIL: {a3['reason']}")
        else:
            print(f"    covering target {KNOWN_SLIDE_TARGET}: state_id={a3['covering_state_id']}"
                  f" rep_t={a3['covering_rep_t']} duration_sec={a3['covering_duration_sec']}"
                  f" candidates={a3['covering_candidate_count']}"
                  f" rep_in_span={a3['rep_in_span']} duration_ok={a3['duration_ok']}")

    a4 = results["A4"]
    print(f"\nA4 dedupe shape  [soft]  totals={a4['totals']}")
    for v in a4["videos"]:
        flag = " FLAG" if (v["flag_low_states"] or v["flag_high_single_second_share"]) else ""
        print(f"    {v['video']:55s} frames={v['frames_sampled']} states={v['states']}"
              f" ratio={v['compression_ratio']} dur[min/med/p95/max]="
              f"{v['duration_min']}/{v['duration_median']}/{v['duration_p95']}/{v['duration_max']}"
              f" 1s_states={v['single_second_states']} ({v['single_second_share']:.1%}){flag}")

    a5 = results["A5"]
    print(f"\nA5 determinism  [HARD]  pass={a5['hard_pass']}")
    if a5.get("status") == "skipped":
        print(f"    skipped: {a5['reason']}")
    else:
        print(f"    video={a5.get('video')} stored={a5.get('stored_sha256')}"
              f" redecoded={a5.get('redecoded_sha256')}")

    a6 = results["A6"]
    print(f"\nA6 artefact integrity  [HARD]  pass={a6['hard_pass']}")
    for v in a6["videos"]:
        print(f"    {v['video']:55s} states={v['state_count']} ok={v['ok']}"
              + (f" missing_files={v['missing_files']}" if v["missing_files"] else "")
              + (f" too_small={v['too_small']}" if v["too_small"] else "")
              + (f" bad_resolution={v['bad_resolution']}" if v["bad_resolution"] else "")
              + (f" missing_in_index={v['missing_in_index']}" if v["missing_in_index"] else "")
              + (f" rep_count_wrong={v['rep_count_wrong']}" if v["rep_count_wrong"] else "")
              + (f" rep_t_mismatch={v['rep_t_mismatch']}" if v["rep_t_mismatch"] else ""))

    a7 = results["A7"]
    print("\nA7 longest-held states (top 15)  [soft, eyeball]")
    for r in a7["top"]:
        print(f"    {r['video']:45s} #{r['state_id']:04d} [{r['hms_start']}-{r['hms_end']}]"
              f" {r['duration_sec']:7.1f}s  {r['narration_snippet']!r}")

    a8 = results["A8"]
    print(f"\nA8 residual under-split  [HARD]  pass={a8['hard_pass']}"
          f"  max_inside_share={a8['max_inside_share']}")
    for v in a8["videos"]:
        print(f"    {v['video']:55s} states={v['states']} changes={v['changes_total']}"
              f" inside={v['changes_inside']} inside_share={v['inside_share']:.1%} ok={v['ok']}")

    print()
    overall = all(results[cid]["hard_pass"] for cid in HARD_CHECK_IDS)
    print(f"HARD checks: {HARD_CHECK_IDS} -> overall_pass={overall}")
    print("=" * 88)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", help="substring filter on the video id")
    args = ap.parse_args()

    all_jobs = discover_jobs()
    jobs = all_jobs
    if args.only:
        needle = args.only.lower()
        jobs = [j for j in all_jobs if needle in j.id.lower()]
    if not jobs:
        log(f"no video id matches --only {args.only!r}")
        return 1

    footage = human(sum(j.duration_sec for j in jobs))
    log(f"auditing {len(jobs)}/{len(all_jobs)} video(s), {footage} of footage")

    results = {
        "A1": check_a1(jobs),
        "A2": check_a2(jobs),
        "A3": check_a3(jobs),
        "A4": check_a4(jobs),
        "A5": check_a5(jobs),
        "A6": check_a6(jobs),
        "A7": check_a7(jobs),
        "A8": check_a8(jobs),
    }
    overall = all(results[cid]["hard_pass"] for cid in HARD_CHECK_IDS)

    write_json(VISUAL_HOME / "audit_31.json", {
        "hard_check_ids": HARD_CHECK_IDS,
        "overall_hard_pass": overall,
        "videos_audited": [j.id for j in jobs],
        "results": results,
    })
    print_report(results)

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
