"""Inside bars and the parent bar they are measured against.

Source: `docs/RULEBOOK.md` §5.2.8, §5.2.8a, decision **D-23**, `IBD`
(`edu/123sequence/insidebar.png`).

**The rule:** *inside* is measured against the **parent bar** — the nearest preceding bar that is
not itself an inside bar — **not** the bar immediately to the left. `IBD` labels exactly one Parent
Bar, draws its reference lines from that bar's high and low, and points a run of **two** Inside Bars
at it. A run of inside bars all point at the same parent; the parent does not advance through the
run. For a non-inside bar, `parent_pos` is the nearest preceding non-inside bar — the reference bar
D-28 requires.

**Implementation convention, not in the material.** A bar whose high equals the parent's high *and*
whose low equals the parent's low is treated as **inside** (`<=` / `>=`, not strict `<` / `>`). The
material never addresses the exact-equality case; if it ever matters, this is a decision that needs
revisiting, not a rule to add to `docs/RULEBOOK.md`.

Pure functions over bars: no disk I/O, no network, no clock reads.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def candle_structure(bars: pd.DataFrame) -> pd.DataFrame:
    """Inside-bar flags and parent-bar positions for every row of `bars`.

    Returns a frame on `bars.index` with columns:
      is_inside : bool — True if this bar's high/low fall within [parent low, parent high].
      parent_pos: int64 — positional index of the parent bar, -1 where there is none (the first
                  bar, which has no reference).

    Single forward pass, O(n). See the module docstring for the parent-bar rule and the
    exact-equality convention.
    """
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    n = len(bars)

    is_inside = np.zeros(n, dtype=bool)
    parent_pos = np.full(n, -1, dtype="int64")

    parent = -1
    for i in range(n):
        if parent == -1:
            is_inside[i] = False
            parent_pos[i] = -1
            parent = i
        elif high[i] <= high[parent] and low[i] >= low[parent]:
            is_inside[i] = True
            parent_pos[i] = parent
        else:
            is_inside[i] = False
            parent_pos[i] = parent
            parent = i

    return pd.DataFrame({"is_inside": is_inside, "parent_pos": parent_pos}, index=bars.index)


def inside_flags(bars: pd.DataFrame) -> pd.Series:
    """The `is_inside` column of `candle_structure(bars)`."""
    return candle_structure(bars)["is_inside"]


def parent_positions(bars: pd.DataFrame) -> pd.Series:
    """The `parent_pos` column of `candle_structure(bars)`."""
    return candle_structure(bars)["parent_pos"]


__all__ = [
    "candle_structure",
    "inside_flags",
    "parent_positions",
]
