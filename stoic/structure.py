"""The expansion leg after Confirmed Step 3, and where the pullback that follows it begins.

Source: `docs/RULEBOOK.md` §5.2.1a and decision **D-28**; the engine notes under §5.3.3a.

**The rule:** the expansion leg after Confirmed Step 3 runs for as long as price keeps making new
extremes in the sequence direction, and during it there is no pullback and no PTB. The pullback
begins at the **first completed candle whose extremes both move against the direction** — bullish:
a **lower high *and* a lower low**; bearish: a **higher low *and* a higher high** — measured
against the **parent bar** (§5.2.8a), not the bar immediately to the left. Comparisons are
**strict**: "lower" means lower, not "not higher".

**D-28's discrimination.** The material operationalises *"the first candle that goes the other
way"* three ways: (a) breaches the previous extreme, (b) fails to extend, (c) both. D-28 takes
**(c)** — the reading a passage states outright in two clauses (`TPA @ 00:23:50`) — not (a) or (b)
alone. The three readings differ exactly on inside and outside bars: an inside bar has a lower
high but not a lower low (reading (b) alone would wrongly open here); an outside bar breaches the
previous low but still makes a new high (reading (a) alone would wrongly open here). Under (c),
**neither an inside bar nor an outside bar opens a pullback** — both properties fall out of the
rule and both are asserted by tests, not merely commented.

**No body test.** §5.3.3c forbids reintroducing `close < open` or a lower-high-only test as a
per-candidate filter, and D-28 has none either. Nothing in this module looks at `open` or `close`.

`leg_phases` owns only **where the pullback begins**. Where it *ends* is not L1's: the working
order walks candle by candle until it fills or is invalidated (§5.3.4a), which is L2/L3's job —
that boundary is not modelled here.

Pure functions over bars: no disk I/O, no network, no clock reads.
"""

from __future__ import annotations

from enum import StrEnum

import pandas as pd

from stoic.candles import candle_structure


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class Phase(StrEnum):
    EXPANSION = "expansion"
    PULLBACK = "pullback"


def opens_pullback(
    bars: pd.DataFrame,
    pos: int,
    direction: Direction,
    structure: pd.DataFrame | None = None,
) -> bool:
    """True if bar `pos` is the first completed candle whose extremes both move against
    `direction`, measured against its **parent bar** (§5.2.8a) rather than bar `pos - 1`.

    `False` if `pos` has no parent bar (the first bar in `bars`, per `candle_structure`).
    Pass a precomputed `structure` (from `stoic.candles.candle_structure`) to avoid recomputing it
    on every call when scanning many positions.

    Raises `ValueError` if `pos` is out of bounds (`0 <= pos < len(bars)`), rather than silently
    wrapping (a negative `pos`) or raising `IndexError` (an out-of-range positive `pos`).
    """
    if not (0 <= pos < len(bars)):
        raise ValueError(f"pos {pos} out of bounds for bars of length {len(bars)}")

    if structure is None:
        structure = candle_structure(bars)

    parent = int(structure["parent_pos"].iat[pos])
    if parent < 0:
        return False

    high = bars["high"]
    low = bars["low"]
    bar_high, bar_low = float(high.iat[pos]), float(low.iat[pos])
    parent_high, parent_low = float(high.iat[parent]), float(low.iat[parent])

    if direction == Direction.BULLISH:
        return bool(bar_high < parent_high and bar_low < parent_low)
    if direction == Direction.BEARISH:
        return bool(bar_low > parent_low and bar_high > parent_high)
    raise ValueError(f"unknown direction {direction!r}")


def find_pullback_start(
    bars: pd.DataFrame,
    direction: Direction,
    *,
    start: int,
    end: int | None = None,
) -> int | None:
    """Positional index of the first bar that opens a pullback, or `None` if the leg never does.

    Scans `start + 1 .. end - 1` — `start` itself is excluded, since it is the Confirmed Step 3
    bar supplied by L2 and the pullback follows the leg it opens. `end` defaults to `len(bars)`
    and is clamped to it if given larger.
    """
    end = len(bars) if end is None else min(end, len(bars))

    structure = candle_structure(bars)
    for i in range(start + 1, end):
        if opens_pullback(bars, i, direction, structure=structure):
            return i
    return None


def leg_phases(bars: pd.DataFrame, direction: Direction, *, start: int) -> pd.Series:
    """`Phase` per bar over `bars.index[start:]`: `EXPANSION` up to the pullback bar,
    `PULLBACK` from it on. All `EXPANSION` if the leg never pulls back.

    This locates only where the pullback **begins**. Where it ends is L2/L3's (§5.3.4a, the PTB
    walk) and is not modelled here.
    """
    pullback_start = find_pullback_start(bars, direction, start=start)
    index = bars.index[start:]
    if pullback_start is None:
        phases = [Phase.EXPANSION] * len(index)
    else:
        phases = [
            Phase.PULLBACK if start + offset >= pullback_start else Phase.EXPANSION
            for offset in range(len(index))
        ]
    return pd.Series(phases, index=index, name="phase")


__all__ = [
    "Direction",
    "Phase",
    "find_pullback_start",
    "leg_phases",
    "opens_pullback",
]
