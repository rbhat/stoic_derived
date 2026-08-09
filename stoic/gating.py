"""L4 -- whether a candidate deserves risk. Only the two moving-average gates.

Source: `docs/RULEBOOK.md` §7 opens *"The sequence produces a signal. These decide whether it
deserves risk"* -- this module answers only that, and only for the 50 and 200 SMA gates.

**Gate 1 -- the 50 SMA direction gate** (§7.1.2, decision **D-19**). *"When the price is staying
above 50 you only want to take bullish setups; when the price is staying below 50 you want to look
for the bearish setups"* (`M1 @ 18:38`). **D-19** (§7.1.7) fixes the mechanics as a per-bar read
of the close against the 50 -- no bar count, no lookback, no tolerance band, and no chop detector
(§7.1.8 -- a resetting count *is* what chop looks like from outside, not a state this module
recognises).

**Gate 2 -- the 200 SMA rule** (§7.1.4). *"we're not trying to long against 200 sma, not on the
one minute chart ... do not long into the 200 sma"* (`SCALP @ 22:45`-`23:02`). §7.1.4 states the
bullish case only; the passage is silent on shorting into the 200 from below. The mirror is the
human's decision **D-31** (2026-08-09, `docs/RULEBOOK.md` §11): *"just like we look for longs
above 50/200sma, we look for shorts below it."* That is a recorded strategy decision, not a
reading of the material -- the same disposition `judgment.py` gives `MEANINGFUL_FRACTION`. So
this gate is now symmetric: a bullish candidate is blocked at or below the 200, a bearish one at
or above it. It remains **scoped to fast charts**: the passage licenses `50 -> 200` longs on a
higher timeframe and forbids them on the 1m/5m, so the caller must say which kind of chart it is
(`fast_chart`, no default). *"Longing into the 200"* mechanises as price sitting at or below it,
and its mirror as price sitting at or above it, since the 200 is the obstacle above for a long and
the floor below for a short.

A pure evaluator over bars -- the caller picks the bar position. This module does not know about
orders, fills, sequences or signals, and holds **no threshold, fraction or tuned number of any
kind**: `stoic/judgment.py` is the only module in this repo allowed to hold one, and this one needs
none.

**Explicitly out of scope** (each is a trap named so it is not rebuilt here):

- **No minimum-R gate** (§7.5.4, open row **O-10** -- record R, do not gate on it).
- **No trapped-side filter** (§7.3, status **J** -- `claude_memories/audit-hard-rules-not-in-
  material.md` forbids inventing an unquantified predicate).
- **No HTF-alignment gate** (§7.5.5, **D-27** -- HTF alignment raises the confluence score and
  never blocks; that scoring is L5's, not L4's).
- **No chop detector** (§7.1.8, **D-19** -- chop is what continuous reset-and-recount looks like
  from outside, not a state the engine recognises).
- **No no-edge-zone filter.** §7.4.3's PDH/PDL instance was deliberately not built -- open row
  **O-19**, opened 2026-08-09. `stoic/levels.py` is not imported and PDH/PDL/PDC are not
  referenced here.
- **No MA targeting** (§7.1.5/§7.1.6, **D-14** -- targeting is §6/L5's).

**Five conventions fixed here, not in `docs/RULEBOOK.md`** (same disposition as `candles.py`'s
inside-bar tie-break and `judgment.py`'s two conventions):

1. **A close exactly equal to the 50 blocks both directions.** It is neither "staying above" nor
   "staying below" -- the precedent is `judgment.py`'s own disposition: no yardstick to read a
   pass off means not confirmed, never a pass by default.
2. **A close exactly equal to the 200 blocks, in both directions, on a fast chart** -- being *at*
   the 200 is still longing (or shorting) into it. Hence `<=`/`>=`, not `<`/`>`.
3. **A non-finite (NaN) SMA blocks, in both directions.** During warm-up there is no 50 (or no
   200) to read the gate against, so a candidate cannot be shown to pass it and is blocked
   instead. Consequence, stated plainly: a frame needs 50 bars before any signal can pass gate 1,
   and 200 bars before any candidate can pass gate 2 on a fast chart. That is correct -- the
   alternative is emitting signals whose gates were never actually checked.
4. **`fast_chart` has no default.** §7.1.4 scopes the 200 rule to the 1m/5m and licenses the
   higher-timeframe case; the engine may not guess which chart it is reading.
5. **All reasons are collected, never short-circuited.** A blocked record names everything that
   blocked it, which is what Phase 6 divergence triage reads.

Pure functions over bars: no disk I/O, no network, no clock reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from stoic.structure import Direction


class GateReason(StrEnum):
    TREND_50 = "trend_50"  # §7.1.2, D-19
    INTO_200 = "into_200"  # §7.1.4, D-31


@dataclass(frozen=True)
class GateDecision:
    pos: int
    direction: Direction
    passed: bool  # == (blocked_by == ())
    blocked_by: tuple[GateReason, ...]


def _require_smas(bars: pd.DataFrame, *, fast_chart: bool) -> None:
    required = ["sma_50", *(["sma_200"] if fast_chart else [])]
    missing = [c for c in required if c not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing {missing} -- call stoic.indicators.add_smas(bars) first")


def _trend_50_blocks(bars: pd.DataFrame, pos: int, direction: Direction) -> bool:
    """Gate 1 (§7.1.2, D-19): close against the 50, read on this bar alone. NaN blocks (convention
    3); an exact tie blocks both directions (convention 1)."""
    close = float(bars["close"].iat[pos])
    sma_50 = float(bars["sma_50"].iat[pos])
    if not np.isfinite(close) or not np.isfinite(sma_50):
        return True
    if direction is Direction.BULLISH:
        return not (close > sma_50)
    return not (close < sma_50)


def _into_200_blocks(
    bars: pd.DataFrame, pos: int, direction: Direction, *, fast_chart: bool
) -> bool:
    """Gate 2 (§7.1.4, D-31): symmetric, fast-chart-only. Never blocks anything when `fast_chart`
    is False."""
    if not fast_chart:
        return False
    close = float(bars["close"].iat[pos])
    sma_200 = float(bars["sma_200"].iat[pos])
    if not np.isfinite(close) or not np.isfinite(sma_200):
        return True  # convention 3
    if direction is Direction.BULLISH:
        return close <= sma_200  # convention 2
    return close >= sma_200  # convention 2, mirrored (D-31)


def gate(bars: pd.DataFrame, pos: int, direction: Direction, *, fast_chart: bool) -> GateDecision:
    """Evaluate both gates for `direction` at bar `pos`. `blocked_by` never short-circuits
    (convention 5); order is `GateReason`'s declaration order."""
    _require_smas(bars, fast_chart=fast_chart)

    reasons: list[GateReason] = []
    if _trend_50_blocks(bars, pos, direction):
        reasons.append(GateReason.TREND_50)
    if _into_200_blocks(bars, pos, direction, fast_chart=fast_chart):
        reasons.append(GateReason.INTO_200)

    blocked_by = tuple(reasons)
    return GateDecision(pos, direction, passed=not blocked_by, blocked_by=blocked_by)


def gate_frame(bars: pd.DataFrame, direction: Direction, *, fast_chart: bool) -> pd.DataFrame:
    """`gate` applied to every bar in `bars`. Returns a frame indexed identically to `bars`, with
    `passed` (bool) and `blocked_by` (tuple of `GateReason`) columns. Agrees with `gate` bar-for-bar
    by construction -- it is the same per-bar evaluation, not a separate implementation."""
    _require_smas(bars, fast_chart=fast_chart)

    decisions = [gate(bars, pos, direction, fast_chart=fast_chart) for pos in range(len(bars))]
    return pd.DataFrame(
        {
            "passed": [d.passed for d in decisions],
            "blocked_by": [d.blocked_by for d in decisions],
        },
        index=bars.index,
    )


__all__ = [
    "GateDecision",
    "GateReason",
    "gate",
    "gate_frame",
]
