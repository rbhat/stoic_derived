#!/usr/bin/env python3
"""WP-V §3.3 audit gate -- the ground-truth OCR half.

Read-only and deterministic. Safe to run while the §3.2 extraction is live: it
opens `visual_records.jsonl` for reading only and never touches stage state.

Three subcommands, matching the three items of the gate in
`docs/notes/2026-07-26-slm-retrain-plan.md` §3:

  sample   item 1 -- draw N frames stratified by `frame_class` and emit a
                     worksheet pairing each record's `ocr_text` with its JPEG,
                     so a human (or the session agent) can read the two side by
                     side. Snapshotted to disk, because the corpus is still
                     growing underneath us and a sample that changes between
                     runs is not a sample.
  slides   item 2 -- pull the four known slides by (video, state_id) and emit
                     their stored `ocr_text` for diffing against hand-typed
                     ground truth.
  counts   item 3 -- frames by class, OCR-confidence distribution, unreadable
                     rate, cap/strip rates. Counts, not verdicts.
  score            -- fold a filled-in verdicts file back into counts.

What this deliberately does NOT do: anything with `chart.drawn_levels`. That
field is advisory by decision and is not trained on, and two checks against it
have already been built and retired -- see `claude_memories/wpv-32-extraction-run.md`,
"STOP AUDITING drawn_levels". The gate is about `ocr_text` against the pixels.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parents[2]
VISUAL = REPO / ".artifacts" / "research" / "visual"
GATE_DIR = VISUAL / "ocr_gate"

# Item 2's four known slides. The plan names them by timestamp; these are the
# state_ids those timestamps resolve to, verified by `--locate` before use.
KNOWN_SLIDES_SPEC = [
    ("concept_simple_stoic_setups_sss", 35 * 60 + 5, 37 * 60, "SSS 00:35:05-00:37:00"),
    ("concept_htf_stoic_trader_protocol", None, None, "HTF template slides"),
]

# Every graded frame gets exactly one of these. `exact` and `minor` are both
# "the transcription is usable"; the split exists so the report can say how
# much of the corpus is byte-clean rather than merely faithful.
VERDICTS = ("exact", "minor", "omission", "error", "hallucination")


def load_records(videos: list[str] | None = None) -> list[dict]:
    """Every `ok` record on disk, in a stable order. Errors are excluded --
    they carry no `ocr_text` to grade."""
    out: list[dict] = []
    for vid_dir in sorted(VISUAL.iterdir()):
        if not vid_dir.is_dir():
            continue
        if videos and vid_dir.name not in videos:
            continue
        f = vid_dir / "visual_records.jsonl"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") == "ok":
                out.append(rec)
    out.sort(key=lambda r: (r["video"], r["state_id"]))
    return out


def allocate(class_sizes: dict[str, int], n: int, floor: int) -> dict[str, int]:
    """Split n across classes: a floor per class first, then largest-remainder
    proportional on what is left. Deterministic, ties broken by class name."""
    classes = sorted(class_sizes)
    alloc = {c: min(floor, class_sizes[c]) for c in classes}
    remaining = n - sum(alloc.values())
    if remaining <= 0:
        return alloc
    headroom = {c: class_sizes[c] - alloc[c] for c in classes}
    pool = sum(headroom.values())
    if pool == 0:
        return alloc
    exact = {c: remaining * headroom[c] / pool for c in classes}
    for c in classes:
        alloc[c] += int(exact[c])
    short = n - sum(alloc.values())
    order = sorted(classes, key=lambda c: (-(exact[c] - int(exact[c])), c))
    i = 0
    while short > 0 and any(alloc[c] < class_sizes[c] for c in classes):
        c = order[i % len(order)]
        if alloc[c] < class_sizes[c]:
            alloc[c] += 1
            short -= 1
        i += 1
    return alloc


def stride_pick(items: list[dict], k: int) -> list[dict]:
    """Systematic sample: k items spread evenly across a list already sorted by
    (video, state_id). Deterministic with no seed, and it spreads the draw
    across videos and across each video's timeline -- which a seeded RNG does
    not guarantee on a corpus this lopsided (one video holds half the frames)."""
    if k >= len(items):
        return list(items)
    if k <= 0:
        return []
    return [items[round(i * (len(items) - 1) / max(k - 1, 1))] for i in range(k)]


def worksheet_row(rec: dict) -> dict:
    """One frame's worth of what a grader needs, and nothing that would bias
    the reading -- `summary` and `concepts` are the model's interpretation and
    are deliberately withheld from the worksheet."""
    vid_dir = VISUAL / rec["video"]
    return {
        "id": rec["id"],
        "video": rec["video"],
        "state_id": rec["state_id"],
        "hms": rec.get("rep_hms") or rec.get("hms_start"),
        "jpeg": str((vid_dir / rec["source_frame"]).relative_to(REPO)),
        "frame_class": rec["frame_class"],
        "ocr_confidence": rec["ocr_confidence"],
        "unreadable_lines": rec.get("unreadable_lines", 0),
        "ocr_line_count": rec.get("ocr_line_count", 0),
        "ocr_text_capped": bool(rec.get("ocr_text_capped")),
        "axis_lines_stripped": rec.get("axis_lines_stripped", 0),
        "prompt_sha": rec.get("prompt_sha"),
        "ocr_text": rec.get("ocr_text", ""),
    }


def cmd_sample(args: argparse.Namespace) -> int:
    out_path = GATE_DIR / args.out
    if out_path.exists() and not args.force:
        print(f"{out_path.relative_to(REPO)} already exists -- reusing the snapshot.")
        print("Pass --force to redraw (this invalidates any grading done against it).")
        return 0

    recs = load_records()
    if not recs:
        print("no records on disk yet", file=sys.stderr)
        return 1

    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_class[r["frame_class"]].append(r)
    sizes = {c: len(v) for c, v in by_class.items()}
    alloc = allocate(sizes, args.n, args.floor)

    rows: list[dict] = []
    for cls in sorted(alloc):
        rows.extend(worksheet_row(r) for r in stride_pick(by_class[cls], alloc[cls]))

    GATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": "wpv-3.3-ocr-groundtruth",
        "drawn_from_records": len(recs),
        "videos_covered": sorted({r["video"] for r in recs}),
        "class_sizes": sizes,
        "allocation": alloc,
        "method": "per-class floor then largest-remainder proportional; "
                  "systematic stride within each class over (video, state_id)",
        "prompt_shas": sorted({r.get("prompt_sha") for r in recs if r.get("prompt_sha")}),
        "frames": rows,
    }
    out_path.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {out_path.relative_to(REPO)}: {len(rows)} frames "
          f"from {len(recs)} records across {len(payload['videos_covered'])} videos")
    for cls in sorted(alloc):
        print(f"  {cls:16s} {alloc[cls]:3d} of {sizes[cls]:5d}")
    return 0


def cmd_slides(args: argparse.Namespace) -> int:
    """Item 2. Locate slide-class frames in a window and dump their stored
    `ocr_text` for a hand-typed diff."""
    recs = [r for r in load_records([args.video]) if r["frame_class"] == "slide"]
    lo, hi = args.start, args.end
    hits = [r for r in recs if lo <= r["t_start"] <= hi]
    print(f"{args.video}: {len(hits)} slide frames in "
          f"{lo // 60:02d}:{lo % 60:02d}-{hi // 60:02d}:{hi % 60:02d} "
          f"(of {len(recs)} slide frames extracted)")
    for r in hits:
        print(f"\n{'=' * 78}\n{r['id']}  {r.get('rep_hms')}  "
              f"conf={r['ocr_confidence']}  lines={r.get('ocr_line_count')}")
        print(f"jpeg: {(VISUAL / r['video'] / r['source_frame']).relative_to(REPO)}")
        print("-" * 78)
        print(r.get("ocr_text", ""))
    return 0


def cmd_counts(args: argparse.Namespace) -> int:
    """Item 3. Counts, not verdicts."""
    recs = load_records()
    by_class = Counter(r["frame_class"] for r in recs)
    by_conf = Counter(r["ocr_confidence"] for r in recs)
    conf_by_class: dict[str, Counter] = defaultdict(Counter)
    for r in recs:
        conf_by_class[r["frame_class"]][r["ocr_confidence"]] += 1
    unread = sum(r.get("unreadable_lines", 0) for r in recs)
    lines = sum(r.get("ocr_line_count", 0) for r in recs)
    capped = sum(1 for r in recs if r.get("ocr_text_capped"))
    stripped = sum(1 for r in recs if r.get("axis_lines_stripped"))
    empty = sum(1 for r in recs if not r.get("ocr_text", "").strip())

    print(f"records (ok)            {len(recs)}")
    print(f"prompt_sha              {sorted({r.get('prompt_sha') for r in recs})}")
    print(f"videos                  {len(sorted({r['video'] for r in recs}))}")
    print(f"ocr lines               {lines}")
    print(f"unreadable lines        {unread}  rate {unread / lines if lines else 0:.4f}")
    print(f"empty ocr_text          {empty}  ({empty / len(recs):.1%})")
    print(f"ocr_text_capped         {capped}  ({capped / len(recs):.1%})")
    print(f"axis_lines_stripped     {stripped}  ({stripped / len(recs):.1%})")
    print("\nframe_class x ocr_confidence")
    confs = ["high", "partial", "unreadable"]
    print(f"  {'class':16s} {'n':>6s} " + " ".join(f"{c:>11s}" for c in confs))
    for cls, n in by_class.most_common():
        cells = " ".join(f"{conf_by_class[cls][c]:>11d}" for c in confs)
        print(f"  {cls:16s} {n:>6d} {cells}")
    print(f"  {'ALL':16s} {len(recs):>6d} " + " ".join(f"{by_conf[c]:>11d}" for c in confs))
    return 0


def cmd_slidevar(args: argparse.Namespace) -> int:
    """Slide-text stability. A rendered slide's printed text cannot change
    between frames -- the instructor can draw over it, but he cannot retype it.
    So for frames sharing a title line, any variation in `ocr_text` is model
    error, with no ground-truth ambiguity to argue about.

    This is NOT the retired drawn_levels self-consistency check. That one
    compared hand-drawn levels on a live TradingView chart, where the frames
    genuinely differ because the instructor is editing them. Here the pixels
    under comparison are a static render."""
    recs = [r for r in load_records()
            if r["frame_class"] in ("slide", "chart_annotated", "mixed")]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        lines = [ln for ln in r.get("ocr_text", "").splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0].strip()
        # Only titles that look like a template slide heading, and only groups
        # big enough for "some frames have it, some do not" to mean anything.
        if title.isupper() or title.istitle():
            groups[title].append(r)

    unstable = []
    for title, rs in sorted(groups.items()):
        if len(rs) < args.min_group:
            continue
        linesets = [{ln.strip() for ln in r["ocr_text"].splitlines() if ln.strip()}
                    for r in rs]
        universe = set().union(*linesets)
        core = set.intersection(*linesets)
        varying = universe - core
        if varying:
            unstable.append((title, len(rs), sorted(varying), core))

    print(f"slide-title groups with >={args.min_group} frames: "
          f"{sum(1 for _, rs in groups.items() if len(rs) >= args.min_group)}")
    print(f"groups whose printed text is NOT identical across frames: {len(unstable)}\n")
    for title, n, varying, core in unstable:
        print(f"{title!r}  n={n} frames, {len(core)} stable lines, "
              f"{len(varying)} varying")
        for v in varying[:args.show]:
            present = sum(1 for r in groups[title]
                          if v in {ln.strip() for ln in r["ocr_text"].splitlines()})
            print(f"    {present:3d}/{n}  {v[:88]!r}")
        if len(varying) > args.show:
            print(f"    ... {len(varying) - args.show} more")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    """Fold graded verdicts back into counts. No thresholds, no pass/fail."""
    graded = json.loads((GATE_DIR / args.verdicts).read_text())
    sample = json.loads((GATE_DIR / args.sample).read_text())
    by_id = {f["id"]: f for f in sample["frames"]}

    rows = graded["frames"]
    missing = [i for i in by_id if i not in {r["id"] for r in rows}]
    if missing:
        print(f"UNGRADED: {len(missing)} frames -- {missing[:5]}")

    verdicts = Counter(r["verdict"] for r in rows)
    by_class: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_class[by_id[r["id"]]["frame_class"]][r["verdict"]] += 1
    cls_agree = sum(1 for r in rows if r.get("frame_class_agree"))
    conf_agree = sum(1 for r in rows if r.get("ocr_confidence_agree"))
    tot_content = sum(r.get("content_lines_on_screen", 0) for r in rows)
    tot_wrong = sum(r.get("wrong_lines", 0) for r in rows)
    tot_missing = sum(r.get("missing_lines", 0) for r in rows)
    tot_added = sum(r.get("added_lines", 0) for r in rows)
    tot_furn = sum(r.get("furniture_lines", 0) for r in rows)

    print(f"graded frames           {len(rows)}")
    for v in VERDICTS:
        print(f"  {v:16s} {verdicts[v]:3d}  ({verdicts[v] / len(rows):.1%})")
    print(f"\nframe_class agrees      {cls_agree}/{len(rows)}")
    print(f"ocr_confidence agrees   {conf_agree}/{len(rows)}")
    def pct(x: int) -> str:
        return f"{x / tot_content:.2%}" if tot_content else "n/a"

    print(f"\ncontent lines on screen {tot_content}")
    print(f"  wrong                 {tot_wrong}  ({pct(tot_wrong)})")
    print(f"  missing               {tot_missing}  ({pct(tot_missing)})")
    print(f"  added (not on screen) {tot_added}  ({pct(tot_added)})")
    print(f"axis furniture emitted  {tot_furn} lines (RULE 1 violations that "
          f"survived _strip_axis_ladders)")
    print("\nverdict x frame_class")
    for cls in sorted(by_class):
        cells = " ".join(f"{v}={by_class[cls][v]}" for v in VERDICTS if by_class[cls][v])
        print(f"  {cls:16s} n={sum(by_class[cls].values()):<3d} {cells}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sample", help="item 1: draw the stratified worksheet")
    p.add_argument("-n", type=int, default=30)
    p.add_argument("--floor", type=int, default=3, help="minimum frames per class present")
    p.add_argument("--out", default="sample_30.json")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("slides", help="item 2: dump stored ocr_text for known slides")
    p.add_argument("--video", required=True)
    p.add_argument("--start", type=int, default=0, help="seconds")
    p.add_argument("--end", type=int, default=10 ** 6, help="seconds")
    p.set_defaults(func=cmd_slides)

    p = sub.add_parser("counts", help="item 3: corpus counts")
    p.set_defaults(func=cmd_counts)

    p = sub.add_parser("slidevar", help="slide text that varies between frames of one slide")
    p.add_argument("--min-group", type=int, default=3)
    p.add_argument("--show", type=int, default=8)
    p.set_defaults(func=cmd_slidevar)

    p = sub.add_parser("score", help="fold graded verdicts into counts")
    p.add_argument("--sample", default="sample_30.json")
    p.add_argument("--verdicts", default="verdicts_30.json")
    p.set_defaults(func=cmd_score)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
