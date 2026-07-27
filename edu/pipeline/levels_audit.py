#!/usr/bin/env python3
"""WP-V §3.3 — the levels half of the audit gate. Deterministic, no model.

The §3.3 gate as written checks OCR accuracy and says nothing about
`chart.drawn_levels`, which is the field with the known weakness: the VLM reads
a level's price off the pixels, and on a line with no printed number it
estimates against the axis instead. Measured on the first completed video, that
estimate lands within 1 tick of a real daily OHLC 68.4 % of the time for levels
carrying a method term, and 5.7 % of the time for everything else -- the latter
being chance, because most of that bucket is not a level at all ("M" and "Y" are
chart furniture; "Swing Failure Pattern SFP" is a concept misfiled here).

So the field is two populations and the label separates them. This module
reports that split, and two other things, as counts -- never a pass/fail
(ADR-0021, and §3.3 is "counts, not verdicts").

Three checks, in order of how much they can be relied on:

1. SELF-CONSISTENCY (primary; needs no market data).
   Two adjacent states of the same chart must give the same value for the same
   label -- a level does not move in one second of video. Disagreement is proof
   of estimation that needs no ground truth to establish, which is the point:
   the corpus spans AUD/USD, GBP/JPY, gold, RTY and BTC, and we have daily bars
   for NQ alone. A check that only works on NQ cannot be the one the gate leans
   on.

2. LABEL TAXONOMY (primary; needs no market data).
   Every distinct label, bucketed into method terms and everything else, with
   the unmatched ones listed in full. The bucket list is deliberately dumb and
   printed rather than tuned: an unfamiliar label must show up for a human to
   look at, not get silently classified. Terms come from the education
   (ADR-0004), not from whatever maximises the match rate.

3. BARS CROSSCHECK (secondary; NQ only, and reported as such).
   Distance from each proposed level to the nearest daily OHLC, as a
   distribution rather than a match/no-match flag -- because the interesting
   finding is that the misses are near misses. For method-term labels 95.9 % sit
   within 40 ticks and none is beyond 200, so what fails them is the exactness
   of the criterion, not a misreading. A bare match rate hides that completely.

Usage:
    .venv/bin/python edu/pipeline/levels_audit.py            # all videos
    .venv/bin/python edu/pipeline/levels_audit.py --video cs_vol1_...
    .venv/bin/python edu/pipeline/levels_audit.py --json out.json

Read-only. Safe to run while the extraction is live; it reports on whatever is
on disk at the moment it reads.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_extract import (
    BARS_DIR,
    TICK_SIZE,
    VISUAL_HOME,
    _normalize_instrument,
    read_jsonl,
    write_atomic,
)

# Terms the education uses for a level. From the material (ADR-0004): previous
# day / week / month high, low and close, the Friday and Monday references the
# HTF protocol is built on, and the highest/lowest close of the month that the
# case studies turn on. Matching is substring-insensitive and deliberately
# loose -- the point is to separate "this names a level the method knows" from
# "this is a stray glyph", not to grade spelling.
# PMHC / PMLC are in because the material draws them by those initials -- the
# Gold frames label the same line "Previous Month Highest Close" in full
# elsewhere, so they are the education's own abbreviation, not a guess. Nothing
# is added here to lift a match rate (ADR-0004); an abbreviation earns its place
# by appearing spelled out somewhere in the corpus.
METHOD_TERM_RE = re.compile(
    r"previous|prior|friday|monday|thursday|wednesday|tuesday"
    r"|close|high|low|open"
    r"|^pd[hlco]$|^pw[hlco]$|^pm[hlco]$|^pm[hl]c$|^[hl]com$|^bw[hl]$",
    re.IGNORECASE,
)

# Distance buckets for check 3, in ticks. 1 is the crosscheck's own match
# threshold; the rest exist to show the shape of the misses.
TICK_BUCKETS = (1, 2, 4, 10, 40, 200, 1000)


def classify_label(label: str) -> str:
    label = (label or "").strip()
    if not label:
        return "unlabelled"
    return "method_term" if METHOD_TERM_RE.search(label) else "other"


def parse_price(raw: str) -> float | None:
    try:
        return float(str(raw).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------- check 1: consistency

# Deltas are reported in basis points of price, never in ticks: this check has
# to work on AUD/USD and GBP/JPY as much as on NQ, and a tick means a different
# thing on each. 1 bp of 25,000 is 2.5 points; 1 bp of 0.71 is 0.00007.
BPS_BUCKETS = (1, 5, 20, 100, 500)


def _labels_once(chart: dict) -> dict[str, float]:
    """label -> price, for labels appearing exactly once with a parseable price.

    A label repeated within one frame cannot be paired up unambiguously, so it
    is left out rather than guessed at.
    """
    seen: dict[str, list[float | None]] = defaultdict(list)
    for lvl in chart.get("drawn_levels") or []:
        label = (lvl.get("label") or "").strip()
        if label:
            seen[label].append(parse_price(lvl.get("value")))
    return {k: v[0] for k, v in seen.items() if len(v) == 1 and v[0] is not None}


def _bps(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return abs(a - b) / scale * 10_000 if scale else 0.0


def check_collapse(records: list[dict]) -> dict:
    """Distinct levels on ONE frame reporting the same price.

    The sharpest bars-free signal there is, because it needs no second frame
    and no market data -- it is simply impossible. A previous day's high and
    that same day's low cannot be one number, and neither can sit exactly on
    the Friday close as well. When the model cannot resolve the axis it collapses
    the whole group onto a single reading, and this catches that outright.

    Only method-term labels are paired, because "M" and "Y" are furniture and
    two pieces of furniture sharing a value means nothing.
    """
    frames = 0
    collapsed = []
    for r in records:
        if r.get("status") != "ok":
            continue
        levels = _labels_once(r.get("chart") or {})
        levels = {k: v for k, v in levels.items() if classify_label(k) == "method_term"}
        if len(levels) < 2:
            continue
        frames += 1
        groups: dict[float, list[str]] = defaultdict(list)
        for label, price in levels.items():
            groups[price].append(label)
        shared = {p: ls for p, ls in groups.items() if len(ls) > 1}
        if shared:
            collapsed.append({
                "video": r["video"], "state_id": r["state_id"],
                "hms": r.get("hms_start"),
                "collapsed_onto": {str(p): sorted(ls) for p, ls in shared.items()},
            })
    return {
        "frames_with_2plus_method_levels": frames,
        "frames_with_collapse": len(collapsed),
        "collapse_rate": round(len(collapsed) / frames, 4) if frames else None,
        "examples": collapsed[:20],
    }


def check_self_consistency(records: list[dict]) -> dict:
    """Adjacent states of one chart must agree on a label's value.

    The obvious version of this check is wrong, and the first run of it said
    23.2 % disagreement on evidence that proved nothing: in a video teaching
    PDH/PDL/PDC the instructor steps the chart forward day by day, so
    "Previous Day High" genuinely changes between two adjacent states. The
    examples were 300+ point jumps with every label moving together -- a chart
    advance, not a misread.

    The discriminator is whether the labels move *together*. Advancing the chart
    moves all of them; the model misjudging one line moves that one and leaves
    its neighbours alone. So pairs are classified:

      all_changed   every shared label moved -- the chart advanced. Excluded:
                    it is not evidence either way.
      none_changed  nothing moved. The healthy case.
      mixed         some moved, some did not. The chart cannot have advanced,
                    so the movers are the model changing its mind about a line
                    that did not move. THIS is the measurement.

    Deltas from mixed pairs are reported as a distribution in basis points, so
    a 2 bp wobble and a 300 bp jump are never averaged into one number.
    """
    by_state = {r["state_id"]: r for r in records if r.get("status") == "ok"}
    pair_classes: Counter[str] = Counter()
    labels_compared = 0
    disagreements: list[dict] = []

    for sid in sorted(by_state):
        a, b = by_state.get(sid), by_state.get(sid + 1)
        if a is None or b is None:
            continue
        ca, cb = a.get("chart") or {}, b.get("chart") or {}
        if not ca or not cb:
            continue
        if _normalize_instrument(ca.get("instrument", "")) != _normalize_instrument(
            cb.get("instrument", "")
        ):
            continue
        if (ca.get("timeframe") or "") != (cb.get("timeframe") or ""):
            continue

        la, lb = _labels_once(ca), _labels_once(cb)
        shared = sorted(set(la) & set(lb))
        if len(shared) < 2:
            # With one shared label there is no way to tell an advance from a
            # misread, so the pair carries no information for this check.
            pair_classes["too_few_shared_labels"] += 1
            continue

        moved = [label for label in shared if la[label] != lb[label]]
        if not moved:
            pair_classes["none_changed"] += 1
            continue
        if len(moved) == len(shared):
            pair_classes["all_changed_chart_advanced"] += 1
            continue

        pair_classes["mixed"] += 1
        labels_compared += len(shared)
        for label in moved:
            disagreements.append({
                "video": a["video"], "state_ids": [sid, sid + 1],
                "hms": a.get("hms_start"), "label": label,
                "values": [la[label], lb[label]],
                "bps": round(_bps(la[label], lb[label]), 2),
                "held_still": [x for x in shared if x not in moved],
            })

    hist, prev = {}, 0
    ds = sorted(d["bps"] for d in disagreements)
    for lim in BPS_BUCKETS:
        n = sum(1 for x in ds if x <= lim)
        hist[f"<={lim}bp"] = n - prev
        prev = n
    hist[f">{BPS_BUCKETS[-1]}bp"] = len(ds) - prev

    return {
        "pair_classes": dict(pair_classes),
        "labels_compared_in_mixed_pairs": labels_compared,
        "disagreements": len(disagreements),
        "disagreement_rate_in_mixed_pairs": round(len(disagreements) / labels_compared, 4)
        if labels_compared else None,
        "median_bps": round(ds[len(ds) // 2], 2) if ds else None,
        "bps_histogram": hist,
        "examples": disagreements[:20],
    }


# --------------------------------------------------------------- check 2: labels

def check_label_taxonomy(records: list[dict]) -> dict:
    counts: Counter[str] = Counter()
    labels_by_class: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        if r.get("status") != "ok":
            continue
        for lvl in (r.get("chart") or {}).get("drawn_levels") or []:
            label = (lvl.get("label") or "").strip()
            cls = classify_label(label)
            counts[cls] += 1
            labels_by_class[cls][label or "(empty)"] += 1
    total = sum(counts.values())
    return {
        "total_levels": total,
        "by_class": dict(counts),
        "share_method_term": round(counts["method_term"] / total, 4) if total else None,
        # Listed in full, not summarised: an unfamiliar label is the thing a
        # human needs to see, and it is exactly what a summary would hide.
        "other_labels": labels_by_class["other"].most_common(),
        "method_term_labels": labels_by_class["method_term"].most_common(25),
    }


# ----------------------------------------------------------- check 3: bars (NQ)

def _bar_prices(symbol: str) -> list[float] | None:
    path = BARS_DIR / f"{symbol}_D.jsonl"
    if not path.exists():
        return None
    vals = {
        row[f"{f}_ticks"] * TICK_SIZE
        for row in read_jsonl(path)
        for f in ("open", "high", "low", "close")
    }
    return sorted(vals) or None


def _nearest_ticks(vals: list[float], price: float) -> float:
    i = bisect.bisect_left(vals, price)
    best = None
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(vals):
            d = abs(vals[j] - price)
            if best is None or d < best:
                best = d
    return best / TICK_SIZE


def check_bars_distance(records: list[dict]) -> dict:
    """Distance to the nearest daily OHLC, per label class, as a distribution.

    Secondary by design. We hold daily bars for NQ only, so this is silent on
    most of the corpus and must never be what the gate turns on -- see check 1.
    """
    cache: dict[str, list[float] | None] = {}
    dists: dict[str, list[float]] = defaultdict(list)
    covered: Counter[str] = Counter()

    for r in records:
        if r.get("status") != "ok":
            continue
        chart = r.get("chart") or {}
        symbol = _normalize_instrument(chart.get("instrument", ""))
        if symbol not in cache:
            cache[symbol] = _bar_prices(symbol)
        vals = cache[symbol]
        for lvl in chart.get("drawn_levels") or []:
            price = parse_price(lvl.get("value"))
            if price is None:
                covered["unparseable"] += 1
                continue
            if vals is None:
                covered[f"no_bars:{symbol}"] += 1
                continue
            covered[f"bars:{symbol}"] += 1
            dists[classify_label(lvl.get("label"))].append(_nearest_ticks(vals, price))

    out: dict[str, object] = {"level_coverage": dict(covered)}
    for cls, ds in sorted(dists.items()):
        ds.sort()
        cum, prev, hist = {}, 0, {}
        for lim in TICK_BUCKETS:
            n = sum(1 for x in ds if x <= lim)
            hist[f"<={lim}"] = n - prev
            cum[f"<={lim}"] = n
            prev = n
        hist[f">{TICK_BUCKETS[-1]}"] = len(ds) - prev
        out[cls] = {
            "n": len(ds),
            "median_ticks": round(ds[len(ds) // 2], 2) if ds else None,
            "within_1_tick_rate": round(cum["<=1"] / len(ds), 4) if ds else None,
            "histogram_ticks": hist,
            "cumulative_ticks": cum,
        }
    return out


# ---------------------------------------------------------------------- reporting

def render(report: dict) -> str:
    lines: list[str] = []
    z = report["collapse"]
    lines.append("0. COLLAPSE — distinct levels on one frame sharing a price (impossible)")
    lines.append(f"   frames with 2+ method-term levels : {z['frames_with_2plus_method_levels']}")
    rate = z["collapse_rate"]
    lines.append(
        f"   frames showing a collapse         : {z['frames_with_collapse']}"
        + (f"  ({rate:.1%})" if rate is not None else "")
    )
    for e in z["examples"][:4]:
        for price, labels in e["collapsed_onto"].items():
            lines.append(f"     #{e['state_id']} {price} <- {', '.join(labels)}")

    a = report["self_consistency"]
    lines.append("")
    lines.append("1. SELF-CONSISTENCY — adjacent states of one chart, no market data needed")
    for k, n in sorted(a["pair_classes"].items()):
        lines.append(f"     {k:28s} {n}")
    rate = a["disagreement_rate_in_mixed_pairs"]
    lines.append(
        f"   labels that moved while a neighbour held still: {a['disagreements']}"
        + (f" of {a['labels_compared_in_mixed_pairs']} ({rate:.1%})" if rate is not None else "")
    )
    if a["median_bps"] is not None:
        lines.append(f"   median disagreement: {a['median_bps']} bp   {a['bps_histogram']}")
    for d in a["examples"][:5]:
        lines.append(
            f"     e.g. #{d['state_ids'][0]}->{d['state_ids'][1]} {d['label']!r}: "
            f"{d['values'][0]} -> {d['values'][1]} ({d['bps']}bp), "
            f"held still: {d['held_still']}"
        )

    b = report["label_taxonomy"]
    lines.append("")
    lines.append("2. LABEL TAXONOMY")
    lines.append(f"   total levels            : {b['total_levels']}")
    for cls, n in sorted(b["by_class"].items()):
        share = n / b["total_levels"] if b["total_levels"] else 0
        lines.append(f"     {cls:14s} {n:6d}  ({share:5.1%})")
    if b["other_labels"]:
        lines.append("   labels not matching a method term (all of them):")
        for label, n in b["other_labels"][:30]:
            lines.append(f"     {n:5d}  {label!r}")

    c = report["bars_distance"]
    lines.append("")
    lines.append("3. BARS CROSSCHECK — NQ only; silent on the rest of the corpus")
    lines.append(f"   coverage: {c['level_coverage']}")
    for cls in ("method_term", "other", "unlabelled"):
        d = c.get(cls)
        if not d:
            continue
        lines.append(
            f"   {cls}: n={d['n']}, median {d['median_ticks']} ticks, "
            f"within 1 tick {d['within_1_tick_rate']:.1%}"
        )
        lines.append(f"     cumulative: {d['cumulative_ticks']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", action="append", help="limit to these videos")
    ap.add_argument("--json", type=Path, help="also write the full report here")
    args = ap.parse_args()

    paths = sorted(VISUAL_HOME.glob("*/visual_records.jsonl"))
    if args.video:
        wanted = set(args.video)
        paths = [p for p in paths if p.parent.name in wanted]
    if not paths:
        print(f"no visual_records.jsonl under {VISUAL_HOME}", file=sys.stderr)
        return 1

    records: list[dict] = []
    per_video: dict[str, list[dict]] = {}
    for p in paths:
        recs = read_jsonl(p)
        per_video[p.parent.name] = recs
        records.extend(recs)

    report = {
        "videos": {k: len(v) for k, v in per_video.items()},
        "records": len(records),
        "collapse": check_collapse(records),
        # Consistency is per video: state_ids only mean "adjacent" within one.
        "self_consistency": _merge_consistency(
            [check_self_consistency(v) for v in per_video.values()]
        ),
        "label_taxonomy": check_label_taxonomy(records),
        "bars_distance": check_bars_distance(records),
    }

    print(f"levels audit — {len(records)} records across {len(per_video)} video(s)")
    print()
    print(render(report))
    if args.json:
        write_atomic(args.json, json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    return 0


def _merge_consistency(parts: list[dict]) -> dict:
    labels = sum(p["labels_compared_in_mixed_pairs"] for p in parts)
    dis = sum(p["disagreements"] for p in parts)
    pair_classes: Counter[str] = Counter()
    hist: Counter[str] = Counter()
    examples: list[dict] = []
    all_bps: list[float] = []
    for p in parts:
        pair_classes.update(p["pair_classes"])
        hist.update(p["bps_histogram"])
        examples.extend(p["examples"])
        all_bps.extend(d["bps"] for d in p["examples"])
    all_bps.sort()
    return {
        "pair_classes": dict(pair_classes),
        "labels_compared_in_mixed_pairs": labels,
        "disagreements": dis,
        "disagreement_rate_in_mixed_pairs": round(dis / labels, 4) if labels else None,
        "median_bps": round(all_bps[len(all_bps) // 2], 2) if all_bps else None,
        "bps_histogram": dict(hist),
        "examples": examples[:20],
    }


if __name__ == "__main__":
    raise SystemExit(main())
