#!/usr/bin/env python3
"""Resolve the OHLC-header join keys counted by `spec_coverage.py` to real bars.

`docs/notes/2026-07-27-spec-coverage-probe.md` §2 is explicit that its `DATED`
column counts **join keys, not resolved dates** -- one frame (`#0385`) had been
resolved end to end and the rest were unverified. This converts the key count
into a resolved count, and measures whether the join rule identifies a bar at
all. Read-only; counts, not verdicts.

THE JOIN RULE IS 3-OF-4, NOT 4-OF-4, and that is not a convenience. On the one
frame verified by hand the OCR read H, L and C to the tick and got the open
wrong by a single tick -- a printed-number misread of the kind
`docs/notes/2026-07-27-wpv-33-ocr-gate.md` §5 measures. A naive 4-tuple equality
returns zero matches and makes the whole route look impossible.

A 3-of-4 rule is weaker than a 4-of-4 rule, so it has to earn its keep: a rule
loose enough to match everything resolves nothing. `--audit` runs two controls
that try to break it, per ADR-0021:

  perturbed   every leg shifted by one tick. These quadruples are, by
              construction, on no chart. If they match at a rate near the real
              one, the rule is matching noise and the resolved count is worthless.
  2-of-4      the same join relaxed by one leg, to show what the ambiguity
              looks like just outside the rule we chose.

Prices are stored as integer ticks. NQ ticks are 0.25, verified here rather
than assumed: `ticks * 0.25` reproduces the §0 bar (2026-01-02 60m,
O 25385.25 H 25415.00 L 25379.25 C 25394.50) exactly.
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parents[2]
VISUAL = REPO / ".artifacts" / "research" / "visual"
BARS = REPO / ".artifacts" / "research" / "bars"

TICK = 0.25
TIMEFRAMES = ("1m", "5m", "15m", "60m", "D")
LEGS = ("O", "H", "L", "C")

NUM = r"([\d,]+(?:\.\d+)?)"
OHLC_RE = re.compile(rf"O\s?{NUM}\s+H\s?{NUM}\s+L\s?{NUM}\s+C\s?{NUM}", re.I)


def to_ticks(s: str) -> int | None:
    """A price that is not a whole number of ticks cannot be any bar's price --
    it is an OCR misread, and saying so is cheaper than a failed join."""
    v = float(s.replace(",", ""))
    q = v / TICK
    return round(q) if abs(q - round(q)) < 1e-6 else None


def frame_keys(videos: list[str] | None) -> list[dict]:
    """One entry per frame carrying a parseable OHLC header."""
    out = []
    for vid_dir in sorted(VISUAL.iterdir()):
        if not vid_dir.is_dir():
            continue
        if videos and not any(vid_dir.name.startswith(p) for p in videos):
            continue
        f = vid_dir / "visual_records.jsonl"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            m = OHLC_RE.search(rec.get("ocr_text", "") or "")
            if not m:
                continue
            ticks = [to_ticks(g) for g in m.groups()]
            out.append({
                "id": rec["id"],
                "video": rec["video"],
                "instrument": ((rec.get("chart") or {}).get("instrument") or "").strip(),
                "ticks": ticks,
                "off_tick": [LEGS[i] for i, t in enumerate(ticks) if t is None],
            })
    return out


def load_bars(tf: str) -> list[dict]:
    f = BARS / f"NQ_{tf}.jsonl"
    if not f.exists():
        return []
    bars = []
    with f.open() as fh:
        for line in fh:
            b = json.loads(line)
            bars.append({
                "t": b["trading_date"],
                "start_ns": b["start_ns"],
                "quality": b.get("quality"),
                "ohlc": (b["open_ticks"], b["high_ticks"], b["low_ticks"], b["close_ticks"]),
            })
    return bars


def build_index(bars: list[dict], k: int) -> dict[tuple, list[int]]:
    """(leg-positions, values) -> bar indices, for every k-subset of O/H/L/C."""
    idx: dict[tuple, list[int]] = defaultdict(list)
    combos = list(itertools.combinations(range(4), k))
    for i, b in enumerate(bars):
        for c in combos:
            idx[(c, *(b["ohlc"][j] for j in c))].append(i)
    return idx


def match(ticks: list[int | None], bars: list[dict], idx: dict[tuple, list[int]],
          k: int) -> tuple[set[int], set[tuple]]:
    """Bars agreeing with the frame on any k of the 4 legs, and which legs did."""
    hits: set[int] = set()
    which: set[tuple] = set()
    for c in itertools.combinations(range(4), k):
        if any(ticks[j] is None for j in c):
            continue
        key = (c, *(ticks[j] for j in c))
        for i in idx.get(key, ()):
            hits.add(i)
            which.add(c)
    return hits, which


def resolve(frames: list[dict], bars_by_tf: dict[str, list[dict]],
            idx_by_tf: dict[str, dict], k: int) -> dict:
    """Per distinct quadruple: does it land on exactly one bar, on several, or
    on none? Distinct, because a chart held on screen for 40 states repeats its
    header 40 times and counting those 40 times inflates everything."""
    distinct: dict[tuple, list[str]] = defaultdict(list)
    for fr in frames:
        distinct[tuple(fr["ticks"])].append(fr["id"])

    res = {"distinct": len(distinct), "frames": len(frames),
           "unique": 0, "ambiguous": 0, "none": 0,
           "by_tf": Counter(), "legs": Counter(), "ambig_sizes": [],
           "examples": [], "quality": Counter()}

    for quad, ids in sorted(distinct.items(), key=lambda kv: kv[1][0]):
        landed: list[tuple[str, int]] = []
        legs: set[tuple] = set()
        for tf in TIMEFRAMES:
            if tf not in idx_by_tf:
                continue
            hits, which = match(list(quad), bars_by_tf[tf], idx_by_tf[tf], k)
            legs |= which
            landed += [(tf, i) for i in hits]
        if not landed:
            res["none"] += 1
            continue
        if len(landed) == 1:
            res["unique"] += 1
            tf, i = landed[0]
            res["by_tf"][tf] += 1
            res["quality"][bars_by_tf[tf][i]["quality"]] += 1
            for c in legs:
                res["legs"]["".join(LEGS[j] for j in c)] += 1
            if len(res["examples"]) < 8:
                b = bars_by_tf[tf][i]
                res["examples"].append(
                    f"{ids[0]:58s} -> NQ_{tf} {b['t']} "
                    f"{'/'.join(str(v * TICK) for v in b['ohlc'])} [{b['quality']}]")
        else:
            res["ambiguous"] += 1
            res["ambig_sizes"].append(len(landed))
    return res


def report(label: str, r: dict) -> None:
    d = r["distinct"] or 1
    print(f"\n{label}")
    print(f"  distinct quadruples     {r['distinct']}  (from {r['frames']} frames)")
    print(f"  resolve to ONE bar      {r['unique']}  ({r['unique'] / d:.1%})")
    print(f"  match >1 bar            {r['ambiguous']}  ({r['ambiguous'] / d:.1%})"
          + (f"  median {sorted(r['ambig_sizes'])[len(r['ambig_sizes']) // 2]} bars"
             if r["ambig_sizes"] else ""))
    print(f"  match no bar            {r['none']}  ({r['none'] / d:.1%})")
    if r["by_tf"]:
        print("  uniquely matched on     "
              + ", ".join(f"{tf}={n}" for tf, n in r["by_tf"].most_common()))
    if r["quality"]:
        print("  matched bar quality     "
              + ", ".join(f"{q}={n}" for q, n in r["quality"].most_common()))
    if r["legs"]:
        print("  agreeing legs           "
              + ", ".join(f"{lg}={n}" for lg, n in r["legs"].most_common()))


def diagnose(frames: list[dict], bars_by_tf: dict[str, list[dict]],
             idx: dict[str, dict]) -> None:
    """Why did the rest not resolve? Two cheap causes can be ruled in or out
    from the data alone; anything left is NOT explained here, and this says so
    rather than guessing.

    Note what the price-envelope check does and does not establish. Our bars
    cover one window (Jan-Jun 2026). A quadruple whose prices sit inside that
    window's high-low envelope is **not thereby inside the window** -- NQ
    traded through 25,600 on many days, and an instructor charting a date we
    never built would look exactly like this. The envelope can only rule a
    quadruple OUT, never in."""
    distinct: dict[tuple, list[str]] = defaultdict(list)
    for fr in frames:
        distinct[tuple(fr["ticks"])].append(fr["id"])

    allticks = [v for b in bars_by_tf.get("1m", []) for v in b["ohlc"]]
    lo, hi = (min(allticks), max(allticks)) if allticks else (0, 0)
    # widest H-L each timeframe plausibly produces, as a p95
    p95 = {}
    for tf, bs in bars_by_tf.items():
        rs = sorted(b["ohlc"][1] - b["ohlc"][2] for b in bs)
        p95[tf] = rs[int(len(rs) * 0.95)] if rs else 0
    widest = max(p95.values()) if p95 else 0

    outside, too_wide, unexplained = [], [], []
    for quad, ids in distinct.items():
        if any(match(list(quad), bars_by_tf[tf], idx[tf], 3)[0] for tf in idx):
            continue
        if any(t is not None and not (lo <= t <= hi) for t in quad):
            outside.append(ids[0])
        elif (quad[1] - quad[2]) > widest:
            too_wide.append(ids[0])
        else:
            unexplained.append(ids[0])

    n = len(outside) + len(too_wide) + len(unexplained)
    print(f"\nWHY THE OTHER {n} DID NOT RESOLVE")
    print(f"  price outside our bars' envelope        {len(outside)}")
    print(f"  H-L wider than any timeframe we built   {len(too_wide)}  "
          f"(needs a weekly/monthly aggregation: {', '.join(i.split('#')[-1] for i in too_wide)})")
    print(f"  NOT EXPLAINED HERE                      {len(unexplained)}")
    print("    Leading candidates, neither tested: two or more legs misread by OCR "
          "\n    (§5 of the OCR-gate note measures single-leg misreads), and a chart "
          "\n    whose date falls outside the Jan-Jun 2026 window we built -- which "
          "\n    the envelope check cannot rule out. Do not report either as a cause.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", nargs="*", default=None,
                    help="video name PREFIXES to restrict to")
    ap.add_argument("--audit", action="store_true",
                    help="run the perturbed and 2-of-4 controls (ADR-0021)")
    args = ap.parse_args()

    frames = frame_keys(args.videos)
    if not frames:
        print("no frames with an OHLC header", file=sys.stderr)
        return 1

    non_nq = [f for f in frames if "nasdaq" not in f["instrument"].lower()]
    off = [f for f in frames if f["off_tick"]]
    print(f"{len(frames)} frames carry a parseable OHLC header")
    print(f"  not NQ (no bars to join to)   {len(non_nq)}")
    print(f"  >=1 leg not a whole tick      {len(off)}  "
          f"(legs: {Counter(lg for f in off for lg in f['off_tick']).most_common()})")

    bars_by_tf = {tf: b for tf in TIMEFRAMES if (b := load_bars(tf))}
    print("  bars loaded                   "
          + ", ".join(f"{tf}={len(b)}" for tf, b in bars_by_tf.items()))

    idx3 = {tf: build_index(b, 3) for tf, b in bars_by_tf.items()}
    r = resolve(frames, bars_by_tf, idx3, 3)
    report("3-OF-4 (the rule)", r)
    if r["examples"]:
        print("\n  resolved examples:")
        for e in r["examples"]:
            print(f"    {e}")

    idx4 = {tf: build_index(b, 4) for tf, b in bars_by_tf.items()}
    r4 = resolve(frames, bars_by_tf, idx4, 4)
    print(f"\n  of those, {r4['unique']} match on ALL FOUR legs; "
          f"{r['unique'] - r4['unique']} needed the 3-of-4 relaxation "
          f"(4-of-4 alone resolves {r4['unique']}).")

    diagnose(frames, bars_by_tf, idx3)

    if args.audit:
        print("\n" + "=" * 78)
        print("ADVERSARIAL CONTROLS -- a rule that matches everything resolves nothing")
        print("=" * 78)
        shifted = [dict(f, ticks=[None if t is None else t + 1 for t in f["ticks"]])
                   for f in frames]
        report("PERTURBED: every leg +1 tick. These quadruples are on no chart, so a "
               "\n           unique-match rate near the real one would mean the join is "
               "\n           matching noise.", resolve(shifted, bars_by_tf, idx3, 3))
        idx2 = {tf: build_index(b, 2) for tf, b in bars_by_tf.items()}
        report("2-OF-4: the same join relaxed by one leg.",
               resolve(frames, bars_by_tf, idx2, 2))

    print("\nCounts, not verdicts. A resolved quadruple is a FIXTURE CANDIDATE, not a "
          "\nfixture: under ADR-0004 the identification is VLM output, which is "
          "\nmodel-only evidence and cannot be the sole normative source. Decision 12's "
          "\nreview gate stands between this and any validated rule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
