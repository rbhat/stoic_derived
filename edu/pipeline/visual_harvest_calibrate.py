#!/usr/bin/env python3
"""
WP-V §3.1 fix v2 — FINE_FRAC calibration sweep (Change 3 of wpv_31_fix_spec.md).

Before committing to a FINE_FRAC threshold for the two-criterion run
clustering in visual_harvest.py, sweep candidate values over five videos (one
per content type) and report state counts, duration distributions, and an
*independent* residual under-split yardstick, plus a corpus-wide
extrapolation. This script reports and stops -- it never picks the final
threshold (a human does, per ADR-0004: parameters come from evidence, never a
grid search for "the best cell"; this sweep IS the evidence, not the
decision) and it never re-runs the full 16-video harvest.

It never touches the real per-video harvest directories (decode/states/
extract, all already "done" at the pre-fix resolution for the full corpus).
Both the production-resolution gray cache and the independent yardstick
decode are cached under a private `_calibration/` subtree instead, so this
script is fully resumable and cannot leave the production tree in a
partially-migrated state.

Usage
  .venv/bin/python edu/pipeline/visual_harvest_calibrate.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from visual_harvest import (
    FFMPEG,
    FINE_DELTA,
    GRAY_H,
    GRAY_W,
    HAMMING_MAX,
    SAMPLE_FPS,
    VISUAL_HOME,
    cluster_runs,
    compute_dhashes,
    compute_fine_cells,
    discover_jobs,
    human,
    log,
    write_json,
    yardstick_changes,
)

FINE_FRAC_SWEEP = [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]

# one video per content type, per the fix spec
CALIBRATION_VIDEOS = [
    "concept_simple_stoic_setups_sss",            # pure slide deck
    "concept_htf_stoic_trader_protocol",           # slides + annotated charts
    "cs_vol1_stoic_edge_in_action_case_studies",   # chart walkthrough
    "cs_vol5_nq_v_shape_fomo_study",               # chart walkthrough
    "live_4_2r_on_nq",                             # live session, constant ticking
]

SSS_VIDEO = "concept_simple_stoic_setups_sss"
SSS_TARGET = (2112, 2157)  # known-held sub-window that must survive as one state

VLM_SECONDS_PER_FRAME = 6.0

CAL_HOME = VISUAL_HOME / "_calibration"


# ------------------------------------------------------------------- decode + cache

def decode_gray(src: Path, w: int, h: int) -> np.ndarray:
    """One 1 fps grayscale ffmpeg decode at (w, h) -- mirrors
    visual_harvest.stage_decode's ffmpeg invocation exactly, parameterized so
    the same helper serves both the production resolution and the
    independent yardstick resolution.
    """
    frame_bytes = w * h
    cmd = [
        FFMPEG, "-v", "error", "-i", str(src),
        "-vf", f"fps={SAMPLE_FPS},scale={w}:{h},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(out) // frame_bytes
    return np.frombuffer(out[:n * frame_bytes], dtype=np.uint8).reshape(n, h, w)


def cached_decode(video_id: str, src: Path, w: int, h: int, tag: str) -> np.ndarray:
    """Resumable: caches the decode under _calibration/<video_id>/<tag>.npy so
    re-running this sweep script never redoes a multi-minute ffmpeg pass, and
    never touches the real per-video gray_1fps.npy (see module docstring).
    """
    out_dir = CAL_HOME / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{tag}.npy"
    if path.exists():
        return np.load(path)
    arr = decode_gray(src, w, h)
    tmp = path.with_suffix(".npy.tmp")
    with open(tmp, "wb") as fh:
        np.save(fh, arr)
    os.replace(tmp, path)
    return arr


def cached_yardstick_changes(video_id: str, src: Path) -> np.ndarray:
    """Same resumability contract as cached_decode: the yardstick's own ffmpeg
    pass + numpy reduction is cached so a re-run of this sweep script never
    redoes it."""
    out_dir = CAL_HOME / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "yardstick_changes.npy"
    if path.exists():
        return np.load(path)
    arr = yardstick_changes(src)
    tmp = path.with_suffix(".npy.tmp")
    with open(tmp, "wb") as fh:
        np.save(fh, arr)
    os.replace(tmp, path)
    return arr


# ------------------------------------------------------------------------ statistics

def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, round(p * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def print_table(rows: list[dict]) -> None:
    print()
    print("=" * 100)
    print("WP-V §3.1 fix v2 — FINE_FRAC calibration sweep")
    print(f"HAMMING_MAX={HAMMING_MAX} (fixed)  FINE_DELTA={FINE_DELTA} (fixed)  "
          f"{GRAY_W}x{GRAY_H} cache")
    print("=" * 100)
    current_frac = None
    for r in rows:
        if r["fine_frac"] != current_frac:
            current_frac = r["fine_frac"]
            print(f"\nFINE_FRAC = {current_frac}")
            print(f"  {'video':50s} {'states':>7s} {'dur_med':>8s} {'dur_p95':>8s}"
                  f" {'pct_1s':>7s} {'resid_in':>9s} {'resid_tot':>9s} {'resid_%':>8s}")
        if r["video"] == "__CORPUS_EXTRAPOLATION__":
            print(f"  {'-> corpus extrapolation':50s} states~{r['extrapolated_states']:<8d}"
                  f" VLM_wall~{r['vlm_wall_hours']}h"
                  f"  sss_2112_2157_intact={r['sss_hold_2112_2157_intact']}")
        else:
            print(f"  {r['video']:50s} {r['states']:7d} {r['duration_median']:8.1f}"
                  f" {r['duration_p95']:8.1f} {r['pct_1s_states']:7.1%}"
                  f" {r['residual_inside']:9d} {r['residual_total']:9d}"
                  f" {r['residual_pct']:8.1%}")
    print()
    print("=" * 100)


# ---------------------------------------------------------------------------- main

def main() -> int:
    all_jobs = {j.id: j for j in discover_jobs()}
    missing = [v for v in CALIBRATION_VIDEOS if v not in all_jobs]
    if missing:
        log(f"ERROR: calibration videos not found: {missing}")
        return 1

    corpus_total_sec = sum(j.duration_sec for j in all_jobs.values())
    sample_total_sec = sum(all_jobs[v].duration_sec for v in CALIBRATION_VIDEOS)
    scale = corpus_total_sec / sample_total_sec
    log(f"calibration set: {len(CALIBRATION_VIDEOS)} videos, "
        f"{human(sample_total_sec)} of {human(corpus_total_sec)} corpus "
        f"(scale factor {scale:.2f}x)")

    per_video: dict[str, dict] = {}
    for vid in CALIBRATION_VIDEOS:
        job = all_jobs[vid]
        t0 = time.time()
        gray = cached_decode(vid, job.src, GRAY_W, GRAY_H, "gray_prod")
        dhashes = compute_dhashes(gray)
        fine = compute_fine_cells(gray)
        changes = cached_yardstick_changes(vid, job.src)
        per_video[vid] = {"dhashes": dhashes, "fine": fine, "changes": changes}
        log(f"  {vid}: ready ({human(time.time() - t0)}), "
            f"{gray.shape[0]} frames, {len(changes)} yardstick changes")

    sweep_rows = []
    for fine_frac in FINE_FRAC_SWEEP:
        extrapolated_states = 0
        sss_holds = None
        for vid in CALIBRATION_VIDEOS:
            v = per_video[vid]
            runs = cluster_runs(v["dhashes"], v["fine"], HAMMING_MAX, fine_frac)
            durations = sorted(r["end"] - r["start"] for r in runs)  # whole seconds
            n_states = len(runs)
            single_sec = sum(1 for d in durations if d == 0)
            bounds = {r["start"] for r in runs}
            inside = [int(t) for t in v["changes"] if int(t) not in bounds]
            residual_pct = (len(inside) / len(v["changes"])) if len(v["changes"]) else 0.0

            if vid == SSS_VIDEO:
                sss_holds = any(
                    r["start"] <= SSS_TARGET[0] and r["end"] >= SSS_TARGET[1] for r in runs
                )

            sweep_rows.append({
                "fine_frac": fine_frac, "video": vid, "states": n_states,
                "duration_median": percentile(durations, 0.5),
                "duration_p95": percentile(durations, 0.95),
                "pct_1s_states": round(single_sec / n_states, 4) if n_states else None,
                "residual_inside": len(inside), "residual_total": len(v["changes"]),
                "residual_pct": round(residual_pct, 4),
            })
            extrapolated_states += n_states

        extrapolated_total = round(extrapolated_states * scale)
        vlm_hours = extrapolated_total * VLM_SECONDS_PER_FRAME / 3600.0
        sweep_rows.append({
            "fine_frac": fine_frac, "video": "__CORPUS_EXTRAPOLATION__",
            "extrapolated_states": extrapolated_total,
            "vlm_wall_hours": round(vlm_hours, 2),
            "sss_hold_2112_2157_intact": sss_holds,
        })

    print_table(sweep_rows)

    out_path = VISUAL_HOME / "calibration_31.json"
    write_json(out_path, {
        "sweep": FINE_FRAC_SWEEP, "videos": CALIBRATION_VIDEOS,
        "scale_factor": round(scale, 4), "rows": sweep_rows,
    })
    log(f"wrote {out_path}")
    log("threshold NOT chosen -- human decides (fix spec Change 3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
