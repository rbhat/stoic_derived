"""The human's decided predicates for terms the material leaves unquantified.

`stoic/sequence.py` is the machine and carries **no thresholds**: its `Judgment` dataclass
takes four predicates with no defaults, and L2 asks one only after every mechanical clause
already holds. This module is the one place a number for those terms is allowed to exist, and
every number here names the §11 decision that authorised it. Nothing here reads the material.

**Three of the four are filled here -- `D-29` and `D-30`.**

    is_meaningful_break        §2.1.1, §2.1.4  the Step 1 break and close beyond both MAs
    is_meaningful_close        §2.3.4          the close that confirms Step 3
    select_boundary_from_base  §2.2.6          the line the base determines (D-30)

The two **D-29** predicates share one form: the close must sit beyond its reference by at least
**10% of the parent bar's high-low range**.

    excursion = |close - reference|          reference = the further MA (§2.1.1) or the
                                                         selected boundary (§2.3.4)
    confirmed = excursion >= 0.10 * (parent.high - parent.low)

**One is deliberately NOT filled** -- `find_base`, the *obvious base* of §2.2.5 / **D-3**.
It is the last unquantified term in the engine. An unfilled predicate is the correct state; a
default would pre-decide exactly what Phase 4 exists to discover
(`claude_memories/audit-hard-rules-not-in-material.md`), so `decided_judgment()` *requires* it.

**One is filled only in part.** `select_boundary` gets **D-30**'s base-derived default, but
§2.2.7's **sloping** boundary is retained and is *not* implemented -- see
`select_boundary_from_base`. Deciding when a base edge is a trend line is still **J**.

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
from stoic.sequence import BaseSpan, Boundary, HorizontalBoundary, Judgment
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


def select_boundary_from_base(
    bars: pd.DataFrame, base: BaseSpan, direction: Direction
) -> Boundary | None:
    """§2.2.6 -- the boundary the base determines: its **close** extreme, Step 1 side. (D-30)

    Choosing the base determines the line. §2.3.1 fixes which side -- Step 3 breaks in the direction
    of Step 1 -- so the side is forced, not chosen: the highest close of the base for a bullish
    sequence, the lowest for a bearish one.

    **Closes, not wicks**, per **D-30**. The precedent is §7.3 / **D-8**, where `HCOM`/`LCOM`
    are the highest and lowest daily *close*, *"not the highest wick"*. §2.1.2's wick rule is
    about what counts as a *break*, not about where a level is drawn, so it does not bear here.

    Returns `None` when the span yields no usable level, which §2.2.9 already defines as *wait* --
    never an invented fallback.

    **This is the default, not the whole of §2.2.6.** §2.2.7 is retained: `PC` draws the bullish
    boundary as an up-sloping line and `SCALP @ 00:05:57` narrates a sloping one live, so a **sloped
    boundary remains permitted where the base edge is a trend line**. That override is still **J**
    and is deliberately **not implemented here** -- deciding *when* an edge is a trend line is
    exactly the predicate `audit-hard-rules-not-in-material.md` forbids inventing. Inject a
    different selector to supply one; `Boundary` is a Protocol and `level_at(pos)` already carries
    any shape.
    """
    if base.end < base.start:
        return None
    closes = bars["close"].iloc[base.start : base.end + 1]
    level = float(closes.max()) if direction is Direction.BULLISH else float(closes.min())
    if not np.isfinite(level):
        return None
    return HorizontalBoundary(level)


def decided_judgment(
    find_base: object,
    select_boundary: object = select_boundary_from_base,
) -> Judgment:
    """A `Judgment` with the decided predicates filled and the open one required.

    `find_base` has **no default on purpose** -- an *obvious base* (§2.2.5, **D-3**) is the one term
    still unquantified, and supplying a default would be the failure
    `audit-hard-rules-not-in-material.md` names. Pass it explicitly, or do not build a `Judgment`.

    `select_boundary` **does** default, to `select_boundary_from_base` -- not because a default is
    safe in general, but because **D-30** decided it. Override it to supply §2.2.7's sloping case.
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
    "select_boundary_from_base",
]
