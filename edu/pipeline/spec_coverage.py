#!/usr/bin/env python3
"""Does the extracted material contain what the rulebook's open decisions need?

Read-only, deterministic, safe against the live extraction. Counts only --
it reports candidate evidence, never an answer, and never a verdict.

The question is NOT "does the education state the parameter". It almost
certainly does not. The question is the backward chain:

    Python rulebook (deterministic parameters)
        ^ derived from
    SLM answers ("what is a break and retest?")
        ^ learned from
    training data -- does it mention the concept, WITH worked examples?

So the unit that matters is not a definition, it is a **dated worked example**:
a chart frame where the instructor has labelled the concept, on a named
instrument, on a identifiable date. That is measurable against our own bars --
the same move as the Stage B levels decision (do not OCR the price, compute it
from bars). A concept with 40 dated examples is recoverable even if no number
is ever spoken. A concept with 0 is not, and needs a human decision under
ADR-0004.

Four evidence classes are counted separately because they are worth different
amounts:

  printed_slide   the concept named on a slide          -- a definition
  printed_chart   the concept labelled on a price chart -- a worked example
  dated_chart     ...and the frame names an instrument and a date
                  -- a FIXTURE CANDIDATE, the only class Python can measure
  narrated        the instructor says it out loud       -- context, weakest
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIS = os.path.join(REPO, ".artifacts", "research", "visual")

# Concepts grouped under the rulebook decision they would serve. Aliases are
# matched case-insensitively on word-ish boundaries; short ones like "b&r" and
# "sfp" are matched strictly to avoid swallowing substrings.
CONCEPTS: dict[str, tuple[str, list[str]]] = {
    "break_and_retest": ("3. break-and-retest-parameters", [
        "break & retest", "break and retest", "b&r", "b & r", "break/retest",
        "retest", "break then retest"]),
    "swing_failure": ("4. sfp-parameters", [
        "swing failure", "sfp", "false break", "sweep", "swept", "liquidity grab"]),
    "chop_zone": ("5. chop-zone-parameters", [
        "chop zone", "chop", "tangle", "compression"]),
    "consolidation_range": ("5. chop-zone-parameters", [
        "consolidation", "range", "inside day", "sideways", "box"]),
    "swing_pivot": ("2. pivot-detection", [
        "swing high", "swing low", "pivot", "higher high", "higher low",
        "lower high", "lower low", "peak formation"]),
    "golden_zone_fib": ("8. fib-anchors-and-target-order", [
        "golden", "0.618", "61.8", "0.65", "0.705", "0.79", "fib", "fibonacci",
        "retracement", "50%", "1.618", "2.618", "4.236", "measured move"]),
    "trapped_side": ("6. trapped-side-inference", [
        "trapped", "who is trapped", "trap", "stop run", "forced exit",
        "exit simultaneously"]),
    "sbs_entry_model": ("7. sbs-pivots-and-origin / 9. entry-model-selection", [
        "sbs", "entry model", "limit order", "entry execution", "market order"]),
    "risk_management": ("10. risk-and-management", [
        "stop loss", "risk", "r multiple", "1-2%", "take profit", "target",
        "hold till close", "quick trade", "break even", "trail"]),
    "session_calendar": ("1. session-calendar", [
        "asia", "london", "new york", "9:30", "session", "rth", "cash open",
        "opening range"]),
    "confluence": ("11. confluence-score", [
        "confluence", "confirmation", "a+ setup", "checklist", "grade",
        "high probability"]),
}

# "NQ Mar 12th, 2026" / "CL Jan 27th, 2026" / "Gold February-March 2026" /
# "AUD/USD March, 2026" -- the instructor's own frame titles.
MONTH = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
         r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
DATE_RE = re.compile(rf"\b({MONTH})\b[^\n]{{0,18}}\b(19|20)\d{{2}}\b", re.I)
DATE_NUM_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")

# The second, better route to a date. A TradingView single-chart header prints
# "O25,385.00 H25,415.00 L25,379.25 C25,394.50" -- an exact OHLC quadruple that
# joins deterministically back to a bar in our own data, and therefore to a
# date, without reading the (stripped) time axis at all. Dual-panel frames do
# not print OHLC but do carry a dated title, so the two routes are
# complementary rather than redundant.
OHLC_RE = re.compile(
    r"O\s?[\d,]+\.?\d*\s+H\s?[\d,]+\.?\d*\s+L\s?[\d,]+\.?\d*\s+C\s?[\d,]+\.?\d*", re.I)


def alias_pattern(alias: str) -> re.Pattern:
    """Word-boundary match, but tolerant of the punctuation in 'b&r' / '0.618'."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", re.I)


PATTERNS = {name: [(a, alias_pattern(a)) for a in aliases]
            for name, (_, aliases) in CONCEPTS.items()}


def load(videos: list[str] | None) -> list[dict]:
    out = []
    for f in sorted(glob.glob(f"{VIS}/*/visual_records.jsonl")):
        v = os.path.basename(os.path.dirname(f))
        if videos and not any(v.startswith(p) for p in videos):
            continue
        with open(f) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("status") == "ok":
                    out.append(r)
    return out


def printed_text(r: dict) -> str:
    """Everything the model read or described FROM THE SCREEN. Excludes
    narration, which is a separate and weaker evidence class."""
    parts = [r.get("ocr_text", ""), " ".join(r.get("concepts") or [])]
    ch = r.get("chart") or {}
    parts += [lv.get("label", "") for lv in (ch.get("drawn_levels") or [])]
    parts += list(ch.get("annotations") or [])
    parts.append(r.get("summary", ""))
    return "\n".join(p for p in parts if p)


def has_printed_date(r: dict) -> bool:
    t = r.get("ocr_text", "")
    return bool(DATE_RE.search(t) or DATE_NUM_RE.search(t))


def has_ohlc(r: dict) -> bool:
    return bool(OHLC_RE.search(r.get("ocr_text", "")))


def has_date(r: dict) -> bool:
    """Datable by either route. Neither is a date we have resolved -- both are
    keys that a deterministic join can resolve later. Counting them is not
    claiming the join has been done."""
    return has_printed_date(r) or has_ohlc(r)


def has_instrument(r: dict) -> bool:
    ch = r.get("chart") or {}
    return bool((ch.get("instrument") or "").strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", nargs="*", default=None,
                    help="video name prefixes to restrict to")
    ap.add_argument("--examples", type=int, default=3,
                    help="fixture-candidate ids to print per concept")
    args = ap.parse_args()

    recs = load(args.videos)
    if not recs:
        print("no records", file=sys.stderr)
        return 1

    is_chart = {"chart", "chart_annotated", "mixed"}
    tally: dict[str, Counter] = defaultdict(Counter)
    distinct: dict[str, set] = defaultdict(set)
    hits: dict[str, list[str]] = defaultdict(list)
    alias_use: dict[str, Counter] = defaultdict(Counter)

    for r in recs:
        screen = printed_text(r)
        narr = r.get("narration_window") or ""
        chart_frame = r["frame_class"] in is_chart
        dated = chart_frame and has_date(r) and has_instrument(r)
        for name, pats in PATTERNS.items():
            on_screen = [a for a, p in pats if p.search(screen)]
            in_narr = any(p.search(narr) for _, p in pats)
            if on_screen:
                for a in on_screen:
                    alias_use[name][a] += 1
                tally[name]["printed_chart" if chart_frame else "printed_slide"] += 1
                if chart_frame:
                    distinct[name].add((r["video"], r.get("ocr_text", "")))
                if dated:
                    tally[name]["dated_chart"] += 1
                    if has_ohlc(r):
                        tally[name]["via_ohlc"] += 1
                    else:
                        tally[name]["via_title"] += 1
                    if len(hits[name]) < args.examples:
                        hits[name].append(r["id"])
            if in_narr:
                tally[name]["narrated"] += 1

    n_chart = sum(1 for r in recs if r["frame_class"] in is_chart)
    n_dated = sum(1 for r in recs if r["frame_class"] in is_chart
                  and has_date(r) and has_instrument(r))
    print(f"{len(recs)} records | {len({r['video'] for r in recs})} videos | "
          f"{n_chart} chart frames | {n_dated} dated+instrumented chart frames\n")

    hdr = (f"{'concept':22s} {'slide':>6s} {'chart':>6s} {'uniq':>5s} {'DATED':>6s} "
           f"{'ohlc':>5s} {'title':>5s} {'narr':>6s}   serves")
    print(hdr)
    print("-" * len(hdr))
    for name, (decision, _) in CONCEPTS.items():
        t = tally[name]
        print(f"{name:22s} {t['printed_slide']:>6d} {t['printed_chart']:>6d} "
              f"{len(distinct[name]):>5d} {t['dated_chart']:>6d} {t['via_ohlc']:>5d} "
              f"{t['via_title']:>5d} {t['narrated']:>6d}   {decision}")
    print("\n  uniq = distinct (video, ocr_text) among the chart frames -- frame counts are"
          "\n  inflated by repetition, one slide held on screen for 74 states counts 74 times.")

    print("\nfixture candidates (dated + instrumented chart frames carrying the concept):")
    for name in CONCEPTS:
        if hits[name]:
            print(f"  {name:22s} {', '.join(hits[name])}")
        else:
            print(f"  {name:22s} -- NONE")

    print("\ntop matching aliases (what actually fired, so a count can be audited):")
    for name in CONCEPTS:
        top = ", ".join(f"{a}={n}" for a, n in alias_use[name].most_common(5))
        print(f"  {name:22s} {top or '--'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
