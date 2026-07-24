#!/usr/bin/env python3
"""
Deterministic QA over edu/derived/. Validates every video's artefacts and emits a
compact report plus a machine-readable redo plan. No model tokens involved.

Exit code 0 if everything is clean, 1 if any video needs a redo.

Report:  stdout (human) + .scratch/qa_report.json (with a "redo" plan:
         {video_id: [stages]} that extract_video_knowledge.py --only <id> --force <stage>
         can act on directly).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_video_knowledge import (  # noqa: E402
    OUT_ROOT, SCRATCH, STAGES, discover_jobs, read_json,
)

STAGE_NAMES = [n for n, _ in STAGES]

# thresholds
MIN_TRANSCRIPT_COVERAGE = 0.85   # last segment end must reach this fraction of duration
MIN_KEYFRAMES = 3
MIN_JPEG_BYTES = 2000            # a real 1080p chart jpeg is far larger than this
MAX_REPEAT_RATIO = 0.35          # >35% of segments identical to their predecessor => loop


def check_video(job) -> dict:
    """Return {'id','ok','issues':[...], 'redo':[stages], 'stats':{...}}."""
    d = job.out
    issues: list[str] = []
    redo: set[str] = set()
    stats: dict = {}

    meta = read_json(d / "meta.json")
    state = read_json(d / "state.json") or {"stages": {}}
    stages = state.get("stages", {})

    # every stage must be done
    for name in STAGE_NAMES:
        st = stages.get(name, {}).get("status", "pending")
        if st != "done":
            issues.append(f"stage {name}={st}")
            redo.add(name)

    if not meta:
        issues.append("meta.json missing")
        redo.add("probe")
        return {"id": job.video_id, "ok": False, "issues": issues,
                "redo": sorted(redo), "stats": stats}
    duration = float(meta.get("duration_sec") or 0)

    # transcript: non-empty, monotonic, covers the video, no hallucination loop
    tr = read_json(d / "transcript.json")
    if not tr or not tr.get("segments"):
        issues.append("transcript empty")
        redo.add("transcribe")
    else:
        segs = tr["segments"]
        stats["segments"] = len(segs)
        starts = [s["start"] for s in segs]
        if any(b < a - 0.5 for a, b in zip(starts, starts[1:])):
            issues.append("transcript timestamps non-monotonic")
            redo.add("transcribe")
        last_end = max((s["end"] for s in segs), default=0)
        cov = last_end / duration if duration else 0
        stats["coverage"] = round(cov, 3)
        if duration and cov < MIN_TRANSCRIPT_COVERAGE:
            issues.append(f"transcript covers only {cov*100:.0f}% of video")
            redo.add("transcribe")
        texts = [s["text"].strip() for s in segs]
        if len(texts) > 20:
            repeats = sum(1 for a, b in zip(texts, texts[1:]) if a == b and a)
            ratio = repeats / len(texts)
            stats["repeat_ratio"] = round(ratio, 3)
            if ratio > MAX_REPEAT_RATIO:
                issues.append(f"transcript looks like a repetition loop ({ratio*100:.0f}%)")
                redo.add("transcribe")

    # moments: present and in-range (0 is a warning, not a hard redo)
    mo = read_json(d / "moments.json")
    if mo is None:
        issues.append("moments.json missing")
        redo.add("moments")
    else:
        stats["moments"] = mo.get("count", 0)
        bad = [m for m in mo.get("moments", []) if not (0 <= m["t"] <= duration + 2)]
        if bad:
            issues.append(f"{len(bad)} moment timestamps out of range")
            redo.add("moments")
        if mo.get("count", 0) == 0:
            issues.append("0 moments (warn: keyframes rely on drift/gap only)")

    # keyframes: manifest vs disk, counts, decodable-size, sorted
    km = read_json(d / "keyframes.json")
    if not km or not km.get("keyframes"):
        issues.append("keyframes.json missing/empty")
        redo.add("keyframes")
    else:
        entries = km["keyframes"]
        stats["keyframes"] = len(entries)
        stats["by_source"] = km.get("by_source", {})
        if len(entries) < MIN_KEYFRAMES:
            issues.append(f"only {len(entries)} keyframes")
            redo.add("keyframes")
        disk = sorted((d / "keyframes").glob("*.jpg"))
        stats["jpg_on_disk"] = len(disk)
        if len(disk) != len(entries):
            issues.append(f"manifest {len(entries)} vs {len(disk)} jpgs on disk")
            redo.add("keyframes")
        missing = tiny = 0
        for e in entries:
            p = d / e["file"]
            if not p.exists():
                missing += 1
            elif p.stat().st_size < MIN_JPEG_BYTES:
                tiny += 1
        if missing:
            issues.append(f"{missing} keyframe files missing")
            redo.add("keyframes")
        if tiny:
            issues.append(f"{tiny} keyframe files suspiciously small")
            redo.add("keyframes")
        ts = [e["t"] for e in entries]
        if ts != sorted(ts):
            issues.append("keyframes not time-sorted")
            redo.add("keyframes")

    return {"id": job.video_id, "ok": not redo, "issues": issues,
            "redo": sorted(redo), "stats": stats}


def check_dataset(results: list[dict]) -> list[str]:
    """Cross-check index.json and dataset.jsonl against per-video artefacts."""
    problems = []
    index = read_json(OUT_ROOT / "index.json")
    if not index:
        return ["index.json missing"]
    idx_ids = {v["id"] for v in index["videos"]}
    all_ids = {r["id"] for r in results}
    if idx_ids != all_ids:
        problems.append(f"index ids != derived dirs (missing {all_ids - idx_ids})")

    ds = OUT_ROOT / "dataset.jsonl"
    if not ds.exists():
        return problems + ["dataset.jsonl missing"]
    rows = 0
    per_video = Counter()
    with open(ds, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"dataset.jsonl line {ln} invalid JSON")
                continue
            rows += 1
            per_video[row["video_id"]] += 1
            if not (OUT_ROOT / row["image"]).exists():
                problems.append(f"dataset row {ln}: image missing {row['image']}")
    # dataset row count per video should equal that video's keyframe count
    for r in results:
        kc = r["stats"].get("keyframes", 0)
        if kc and per_video.get(r["id"], 0) != kc:
            problems.append(f"{r['id']}: dataset rows {per_video.get(r['id'],0)} != keyframes {kc}")
    print(f"dataset.jsonl: {rows} rows across {len(per_video)} videos")
    return problems


def main() -> int:
    jobs = discover_jobs()
    results = [check_video(j) for j in jobs]

    print(f"\n=== QA over {len(results)} videos ===")
    redo_plan: dict[str, list[str]] = {}
    for r in results:
        mark = "ok " if r["ok"] else "FIX"
        s = r["stats"]
        summary = (f"seg={s.get('segments','?')} cov={s.get('coverage','?')} "
                   f"mom={s.get('moments','?')} kf={s.get('keyframes','?')}")
        print(f"[{mark}] {r['id']:52} {summary}")
        for issue in r["issues"]:
            print(f"        - {issue}")
        # only stages that are genuine redos (exclude pure warnings handled above)
        if r["redo"]:
            redo_plan[r["id"]] = r["redo"]

    print("\n=== dataset / manifest ===")
    ds_problems = check_dataset(results)
    for p in ds_problems:
        print(f"  ! {p}")

    report = {
        "videos": results,
        "redo": redo_plan,
        "dataset_problems": ds_problems,
        "clean": not redo_plan and not ds_problems,
    }
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "qa_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if redo_plan:
        print("\n=== REDO PLAN ===")
        for vid, stages in redo_plan.items():
            print(f"  {vid}: --force " + " --force ".join(stages))
        print("\nreport: .scratch/qa_report.json")
        return 1
    print("\nALL CLEAN. report: .scratch/qa_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
