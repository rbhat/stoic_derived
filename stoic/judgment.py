"""The human's decided predicates for terms the material leaves unquantified.

`stoic/sequence.py` is the machine and carries **no thresholds**: its `Judgment` dataclass
takes four predicates with no defaults, and L2 asks one only after every mechanical clause
already holds. This module is the one place a number for those terms is allowed to exist, and
every number here names the §11 decision that authorised it. Nothing here reads the material.

**Two of the four are filled here -- `D-29`.**

    is_meaningful_break   §2.1.1, §2.1.4  the Step 1 break and close beyond both 10/20 SMA
    is_meaningful_close   §2.3.4          the close that confirms Step 3

Both use one form: the close must sit beyond its reference by at least **10% of the parent bar's
high-low range**.

    excursion = |close - reference|          reference = the further MA (§2.1.1) or the
                                                         selected boundary (§2.3.4)
    confirmed = excursion >= 0.10 * (parent.high - parent.low)

**Two are deliberately NOT filled** -- `find_base` (§2.2.5, **D-3**) and `select_boundary`
(§2.2.6 to §2.2.9). They are routed to Phase 4's SLM. An unfilled predicate is the correct
state; a default here would pre-decide exactly what that phase exists to discover
(`claude_memories/audit-hard-rules-not-in-material.md`). `decided_judgment()` therefore
*requires* both as arguments and supplies neither.

**Why the parent bar and not the previous bar.** *Prev candle* is ambiguous in this repo in a
way §5.2.8a and **D-23** already settled: the reference is the **parent** -- the nearest
preceding non-inside bar -- because a run of inside bars otherwise collapses the yardstick
toward zero and makes the threshold trivially satisfiable. `IBD`
(`edu/123sequence/insidebar.png`) is the material's own picture of the same geometry: two
inside bars, and the breakout bar closing beyond a line drawn at the **parent's** extreme.
See `stoic/candles.py`.

**Two conventions fixed here, not in `docs/RULEBOOK.md`** (same disposition as `candles.py`'s
inside-bar tie-break):

1. **No parent bar (`parent_pos < 0`) means not confirmed.** At the head of a frame there is no
   yardstick, so the predicate cannot be evaluated; it returns `False` rather than passing. Same
   spirit as the SMA warm-up staying NaN in `stoic/indicators.py` -- never `min_periods=1`.
2. **A non-finite parent range means not confirmed.** A parent range of exactly zero is left
   to the literal arithmetic (threshold 0), which reduces the test to its mechanical
   precondition; it is not special-cased, because doing so would be a rule D-29 lacks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stoic.candles import candle_structure
from stoic.sequence import Boundary, Judgment
from stoic.structure import Direction

# The one number in this module. Human decision, 2026-08-09 -- docs/RULEBOOK.md §11, D-29.
# Not measured, not searched, and not read off the material: the census in
# docs/evidence/census_meaningful.md found no passage in the corpus that quantifies either term.
MEANINGFUL_FRACTION = 0.10

_PARENT_COL = "parent_pos"


def attach_parent_pos(bars: pd.DataFrame) -> pd.DataFrame:
    """Return `bars` carrying the `parent_pos` column these predicates need.

    Idempotent: a frame that already has the column is returned unchanged. Computing it is O(n)
    (`stoic.candles.candle_structure`), so attach it once per frame rather than per bar.
    """
    if _PARENT_COL in bars.columns:
        return bars
    return bars.join(candle_structure(bars)[[_PARENT_COL]])


def _require_parent_pos(bars: pd.DataFrame) -> None:
    if _PARENT_COL not in bars.columns:
        raise ValueError(
            f"bars is missing {_PARENT_COL!r} -- call stoic.judgment.attach_parent_pos(bars) first"
        )


def _clears(bars: pd.DataFrame, pos: int, excursion: float) -> bool:
    """Does `excursion` beyond the reference clear 10% of the parent bar's range? (D-29)"""
    _require_parent_pos(bars)
    parent = int(bars[_PARENT_COL].iat[pos])
    if parent < 0:
        return False  # no parent bar -> no yardstick -> not confirmed (convention 1)
    span = float(bars["high"].iat[parent]) - float(bars["low"].iat[parent])
    if not np.isfinite(span) or not np.isfinite(excursion):
        return False  # convention 2
    return bool(excursion >= MEANINGFUL_FRACTION * span)


def is_meaningful_break(bars: pd.DataFrame, pos: int, direction: Direction) -> bool:
    """§2.1.1 / §2.1.4 -- is this a *meaningful* break and close beyond both 10/20 SMA? (D-29)

    The reference is the **further** MA, because §2.1.1 requires the close to be beyond *both*:
    for a bullish break that is `max(sma_10, sma_20)`, for a bearish one `min(...)`. This
    mirrors how §5.4.7b already picks `min`/`max` for the same "beyond both" reason.

    `SequenceMachine` only calls this once the close is already beyond both MAs, so `excursion` is
    normally positive; it is computed signed anyway, so a caller that asks early gets `False` rather
    than an accidental pass.
    """
    close = float(bars["close"].iat[pos])
    sma10 = float(bars["sma_10"].iat[pos])
    sma20 = float(bars["sma_20"].iat[pos])

    if direction is Direction.BULLISH:
        excursion = close - max(sma10, sma20)
    else:
        excursion = min(sma10, sma20) - close

    return _clears(bars, pos, excursion)


def is_meaningful_close(
    bars: pd.DataFrame, pos: int, boundary: Boundary, direction: Direction
) -> bool:
    """§2.3.4 -- is this the *meaningful close* beyond the selected boundary? (D-29)

    The reference is the boundary's level **on this bar** (`level_at(pos)`), so a sloping boundary
    (§2.2.7) is handled without this function knowing its shape.
    """
    close = float(bars["close"].iat[pos])
    level = float(boundary.level_at(pos))

    excursion = close - level if direction is Direction.BULLISH else level - close

    return _clears(bars, pos, excursion)


def decided_judgment(
    find_base: object,
    select_boundary: object,
) -> Judgment:
    """A `Judgment` with the two decided predicates filled and the two open ones required.

    `find_base` and `select_boundary` have **no defaults on purpose** — they are Phase 4's, and
    supplying one here would be the failure `audit-hard-rules-not-in-material.md` names. Pass them
    explicitly, or do not build a `Judgment`.
    """
    return Judgment(
        is_meaningful_break=is_meaningful_break,
        find_base=find_base,  # type: ignore[arg-type]
        select_boundary=select_boundary,  # type: ignore[arg-type]
        is_meaningful_close=is_meaningful_close,
    )


__all__ = [
    "MEANINGFUL_FRACTION",
    "attach_parent_pos",
    "decided_judgment",
    "is_meaningful_break",
    "is_meaningful_close",
]
