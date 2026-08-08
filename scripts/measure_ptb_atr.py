"""Measure the distribution of PTB range / ATR, for the human to set `k` in RULEBOOK D-18 / O-5.

This is a **distribution report, not a search**. It prints counts and percentiles. It never scores a
threshold against P&L, and it never names a best value — `CLAUDE.md` forbids that.

What is measured, and why it is a proxy
---------------------------------------
R for a PTB entry is `|entry - PTB extreme|` = the PTB bar's own high-low range (entry sits at one
extreme, the stop at the other — RULEBOOK 5.2.3a + 5.4.1). So the quantity the ATR floor compares
against is **bar range / ATR** for the bars that turn out to be PTBs.

There is no labelled PTB set yet (that is Phase 3), so this measures three nested populations that
bracket it:

  ALL     every RTH 5m bar — the widest population, no structure assumed.
  BODY    correction bars under the *body* reading of O-13 (long context: close < open).
  EXTREME correction bars under the *lower-high* reading of O-13 (long context: high < prev high).

BODY and EXTREME are both restricted to a trending context (close and the 10/20 SMA stacked in the
trade direction, price the correct side of the 50) and both exclude inside bars, which the material
excludes explicitly (`PTBV @ 01:33:01`). Reporting the two O-13 readings side by side also shows how
much that still-open row moves the population `k` would be set against.

Usage:  .venv/bin/python scripts/measure_ptb_atr.py
Writes: .artifacts/ptb_atr_distribution.md
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# `stoic` lives at the repo root, one level up from scripts/ — same reason as
# scripts/check_bar_spine.py: running this file directly puts only scripts/ on sys.path, and
# [tool.uv] package = false means there is no installed package to fall back on.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stoic.bars import REPO_ROOT, label_sessions, load_bars

OUT = REPO_ROOT / ".artifacts" / "ptb_atr_distribution.md"

SYMBOLS = ("NQ", "ES")
ATR_LENGTHS = (14, 20)
# Reported so the human can read counts off a fixed ladder. Not candidates being scored.
LADDER = (0.25, 0.40, 0.50, 0.60, 0.75, 1.00, 1.25)
PCTS = (5, 10, 25, 50, 75, 90, 95)

# ~645 min of NQ+ES 1m bars missing; see claude_memories/historical-bars-2025-11-28-outage.md
EXCLUDED_SESSIONS = frozenset({date(2025, 11, 28)})


def wilder_atr(bars: pd.DataFrame, n: int) -> pd.Series:
    """Wilder's ATR(n): RMA of true range. Index-aligned to `bars`."""
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rth_5m(symbol: str) -> pd.DataFrame:
    bars = load_bars(symbol, "5m")
    labels = label_sessions(bars.index, bar_span=pd.Timedelta("5min"))
    bars = bars.assign(session_date=labels["session_date"], rth=labels["rth"])
    keep = bars["rth"] & ~bars["session_date"].isin(EXCLUDED_SESSIONS)
    return bars.loc[keep]


def populations(bars: pd.DataFrame) -> dict[str, pd.Series]:
    """Boolean masks over `bars`, one per population described in the module docstring."""
    sma10 = bars["close"].rolling(10).mean()
    sma20 = bars["close"].rolling(20).mean()
    sma50 = bars["close"].rolling(50).mean()
    prev_high, prev_low = bars["high"].shift(1), bars["low"].shift(1)

    inside = (bars["high"] <= prev_high) & (bars["low"] >= prev_low)
    up_ctx = (bars["close"] > sma10) & (sma10 > sma20) & (bars["close"] > sma50)
    down_ctx = (bars["close"] < sma10) & (sma10 < sma20) & (bars["close"] < sma50)

    body = (up_ctx & (bars["close"] < bars["open"])) | (down_ctx & (bars["close"] > bars["open"]))
    extreme = (up_ctx & (bars["high"] < prev_high)) | (down_ctx & (bars["low"] > prev_low))

    return {
        "ALL": pd.Series(True, index=bars.index),
        "BODY": body & ~inside,
        "EXTREME": extreme & ~inside,
    }


def o13_disagreement(bars: pd.DataFrame) -> list[str]:
    """How often the two readings of O-13 pick different bars. Counts only — O-13 is the human's."""
    masks = populations(bars)
    body, extreme = masks["BODY"], masks["EXTREME"]
    candidate = body | extreme
    both = int((body & extreme).sum())
    only_body = int((body & ~extreme).sum())
    only_extreme = int((extreme & ~body).sum())
    n = int(candidate.sum())
    apart = only_body + only_extreme
    rows = [
        ("both readings call it a correction bar", both),
        ("BODY only — closes down, prints a *higher* high", only_body),
        ("EXTREME only — lower high, closes *up*", only_extreme),
        ("**they disagree**", apart),
    ]
    return [
        "**O-13 — how far apart the two readings are** (trending context, inside bars already out)",
        "",
        f"| of {n:,} candidate bars | bars | share |",
        "|---|---|---|",
        *(f"| {label} | {count:,} | {count / n:.1%} |" for label, count in rows),
        "",
    ]


def report_block(name: str, ratio: pd.Series, total: int) -> list[str]:
    ratio = ratio.dropna()
    n = len(ratio)
    if n == 0:
        return [f"**{name}** — no bars", ""]
    pct = np.percentile(ratio, PCTS)
    lines = [
        f"**{name}** — n = {n:,} ({n / total:.1%} of all RTH 5m bars)",
        "",
        "| pct | " + " | ".join(f"p{p}" for p in PCTS) + " |",
        "|---|" + "---|" * len(PCTS),
        "| range/ATR | " + " | ".join(f"{v:.2f}" for v in pct) + " |",
        "",
        "| range/ATR < | " + " | ".join(f"{k:.2f}" for k in LADDER) + " |",
        "|---|" + "---|" * len(LADDER),
        "| bars | " + " | ".join(f"{int((ratio < k).sum()):,}" for k in LADDER) + " |",
        "| share | " + " | ".join(f"{(ratio < k).mean():.1%}" for k in LADDER) + " |",
        "",
    ]
    return lines


def main() -> int:
    out: list[str] = [
        "# PTB range / ATR — distribution",
        "",
        "Generated by `scripts/measure_ptb_atr.py`. **Counts, not a verdict.** No threshold here",
        "has been scored against performance; `CLAUDE.md` forbids searching for a best cell. The",
        "human sets `k` in RULEBOOK 5.4.4 (§12 row O-5) by reading these counts.",
        "",
        "R for a PTB entry is the PTB bar's own high-low range (5.2.3a + 5.4.1), so `range / ATR`",
        "is exactly the quantity 5.4.4 compares. PTBs are not labelled yet (Phase 3), so three",
        "nested populations bracket them — see the script docstring. `BODY` and `EXTREME` are the",
        "two readings of the still-open O-13, shown side by side.",
        "",
        "Each symbol also gets an **O-13 disagreement** table: how often the two readings pick",
        "different bars. That one is not about `k` — it sizes the open row itself.",
        "",
    ]

    for symbol in SYMBOLS:
        bars = rth_5m(symbol)
        total = len(bars)
        span = f"{bars.index[0].date()} → {bars.index[-1].date()}"
        out += [f"## {symbol} 5m, RTH — {total:,} bars, {span}", ""]
        masks = populations(bars)
        out += o13_disagreement(bars)
        for n_atr in ATR_LENGTHS:
            atr = wilder_atr(bars, n_atr)
            rng = bars["high"] - bars["low"]
            out += [f"### ATR({n_atr})", ""]
            for name, mask in masks.items():
                out += report_block(name, (rng / atr)[mask], total)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
