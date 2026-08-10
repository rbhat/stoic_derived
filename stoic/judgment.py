"""The human's decided predicates for terms the material leaves unquantified.

`stoic/sequence.py` is the machine and carries **no thresholds**: its `Judgment` dataclass
takes four predicates with no defaults, and L2 asks one only after every mechanical clause
already holds. This module is the one place a number for those terms is allowed to exist, and
every number here names the §11 decision that authorised it. Nothing here reads the material.

**All four are filled here -- `D-29`, `D-30` and `D-34`.**

    is_meaningful_break        §2.1.1, §2.1.4  the Step 1 break and close beyond both MAs
    is_meaningful_close        §2.3.4          the close that confirms Step 3
    find_base                  §2.2.5a         the obvious base (D-34)
    select_boundary_from_base  §2.2.6          the line the base determines (D-30)

The two **D-29** predicates share one form: the close must sit beyond its reference by at least
**10% of the parent bar's high-low range**.

    excursion = |close - reference|          reference = the further MA (§2.1.1) or the
                                                         selected boundary (§2.3.4)
    confirmed = excursion >= 0.10 * (parent.high - parent.low)

**`find_base` carries no number at all, and that is D-34's point.** The base is the *residual*
state -- unless price is trending or breaking out, it is basing -- so there is nothing to
calibrate. `MEANINGFUL_FRACTION` remains the only constant in this module, and therefore in the
engine. D-34 dropped **D-3**'s three clauses rather than leaving them unimplemented: compression
because a base's ranges can be about the same, MA proximity and *breakouts inside* because
**D-15**'s reset already ends the count on a close back through both MAs.

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
from stoic.structure import Direction, opens_pullback

# The one number in this module. Human decision, 2026-08-09 -- docs/RULEBOOK.md §11, D-29.
# Not measured, not searched, and not read off the material: the census in
# docs/evidence/census_meaningful.md found no passage in the corpus that quantifies either term.
MEANINGFUL_FRACTION = 0.10

# The base's floor, in **non-inside** candles. Human decision, 2026-08-09 -- docs/RULEBOOK.md §11,
# D-34: "min is 2 bars". Not tuned and not measured: 2 is the fewest candles that can carry a
# range at all, which is why §2.2.5a is P rather than J. Inside candles do not count toward it --
# §5.3.5a / D-23's precedent, and the reason a run of them cannot become a base on its own.
MIN_BASE_CANDLES = 2

_PARENT_COL = "parent_pos"
_INSIDE_COL = "is_inside"
_STRUCTURE_COLS = (_INSIDE_COL, _PARENT_COL)


def attach_parent_pos(bars: pd.DataFrame) -> pd.DataFrame:
    """Return `bars` carrying the `is_inside` / `parent_pos` columns these predicates need.

    Idempotent: a frame that already has both columns is returned unchanged. Computing them is
    O(n) (`stoic.candles.candle_structure`), so attach them once per frame rather than per bar --
    `find_base` is asked on every bar of a growing view, so recomputing inside it would make L2
    quadratic in the length of the frame.

    Both columns are **prefix-stable**: `candle_structure` is a single forward pass, so a value at
    position `i` is the same whether it was computed on the whole frame or on any prefix ending at
    or after `i`. That is what makes attaching once and slicing later correct.
    """
    if all(col in bars.columns for col in _STRUCTURE_COLS):
        return bars
    present = [col for col in _STRUCTURE_COLS if col in bars.columns]
    return bars.drop(columns=present).join(candle_structure(bars)[list(_STRUCTURE_COLS)])


def _require_parent_pos(bars: pd.DataFrame) -> None:
    missing = [col for col in _STRUCTURE_COLS if col not in bars.columns]
    if missing:
        raise ValueError(
            f"bars is missing {missing!r} -- call stoic.judgment.attach_parent_pos(bars) first"
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


def _extension(bars: pd.DataFrame, pos: int, structure: pd.DataFrame) -> int:
    """+1 if both of bar `pos`'s extremes sit above its parent's, -1 if both below, else 0.

    **This is `stoic.structure.opens_pullback` read without a direction**, not a second copy of
    its comparison: *both extremes against a bullish sequence* is the same test as *both extremes
    down*, and the bearish call is the same test upward. Delegating keeps **D-28**'s two-clause
    rule single-sourced, which is what makes the sweep case fall out here rather than being
    re-derived (`docs/CONSTRAINTS.md` -- a layer that reimplements a predicate is reaching past
    the layer that owns it).

    0 means an outside bar or a tie on either extreme. Neither extends, so under **D-34** both are
    basing -- which is exactly the sweep-and-reverse the human's rule keeps inside the base.

    `structure` is built once per `find_base` call and threaded through: `opens_pullback` reads
    only `parent_pos` from it, and rebuilding the frame per call cost more than every other part
    of this predicate put together.
    """
    if opens_pullback(bars, pos, Direction.BULLISH, structure=structure):
        return -1  # lower high and lower low
    if opens_pullback(bars, pos, Direction.BEARISH, structure=structure):
        return 1  # higher high and higher low
    return 0


def _continues_trend(bars: pd.DataFrame, pos: int, structure: pd.DataFrame) -> bool:
    """Is bar `pos` the second of two consecutive non-inside candles extending the same way? (D-34)

    Read backwards through `parent_pos`, which for a non-inside bar *is* the previous non-inside
    bar -- so this is O(1) and needs no scan. A bar with no parent cannot be classified and is
    **not** a continuation: **D-34** makes basing the residual, so an unclassifiable bar is basing
    (convention 3). A bar whose *parent* has no parent needs no separate guard -- `_extension`
    already returns 0 there, and 0 never matches.
    """
    parent = int(bars[_PARENT_COL].iat[pos])
    if parent < 0:
        return False

    here = _extension(bars, pos, structure)
    return here != 0 and here == _extension(bars, parent, structure)


def find_base(bars: pd.DataFrame, step1_pos: int, direction: Direction) -> BaseSpan | None:
    """§2.2.5a -- the *obvious base*, as the trailing run of candles that are not trending. (D-34)

    The base is the **residual state**: unless price is trending or breaking out, it is basing.
    *Trending* is two consecutive **non-inside** candles extending the same way against the parent
    bar (§5.2.8a); everything else is a basing candle. So a **sweep that reverses** -- an outside
    bar -- stays inside the base, which is the human's rule and the reason a containment reading
    was rejected (see **D-34**). **Inside candles are skipped, never treated as a pause in the
    trend**, so a run of them mid-leg cannot open a base; that is §5.3.5a's precedent.

    `bars` is the view truncated at the bar being evaluated, so the span returned always ends at
    `len(bars) - 2` -- **the candle before the one being tested**. That is what makes §2.2.8
    literal rather than conventional: the boundary `select_boundary` draws from this span cannot
    have seen the bar whose break it is about to be tested against. `stoic.sequence` re-asks on
    every bar while the base is unbroken, so the span grows by one candle at a time.

    Returns `None` when the run holds fewer than `MIN_BASE_CANDLES` **non-inside** candles. The
    floor counting non-inside candles is what stops a run of inside candles from becoming a base
    on its own: they are contained by a parent that is itself part of the trend, so reading them
    as a base would make every inside-candle pause mid-leg into a Step 2 -- exactly the *"there
    could be inside bars and then it continues"* case. `None` also covers *the leg resumed*, which
    cancels the base rather than freezing it.

    **`direction` is deliberately unused**, and that is not an oversight. Under **D-34** a trend in
    *either* direction stops the basing -- a continued expansion after Step 1 and the return leg
    that follows it are both trending -- so the classification is symmetric. The parameter stays
    because `Judgment.find_base`'s protocol carries it and a future §2.2.7-style override may need
    it.

    **Two conventions fixed here** rather than in `docs/RULEBOOK.md`, in the same disposition as
    this module's other two:

    3. **An unclassifiable candle is basing.** With no parent bar there is no yardstick, and
       **D-34** makes basing the residual state, so the permissive branch is the correct one here.
       Note this is the opposite disposition to conventions 1 and 2 above, which return `False` for
       want of a yardstick -- there the residual is *not confirmed*, here it is *basing*. Both
       follow the rule they implement rather than a house style.
    4. **The Step 1 candle is never part of the base.** §2.2 puts the return, and so the base,
       *after* Step 1, so the span starts at `step1_pos + 1` at the earliest. Without this the
       Step 1 candle's close could set the boundary under **D-30**, which would require Step 3 to
       clear Step 1's own close.
    """
    _require_parent_pos(bars)

    base_end = len(bars) - 2  # the candle before the one being tested
    earliest = step1_pos + 1  # convention 4
    if base_end < earliest:
        return None

    inside = bars[_INSIDE_COL]
    structure = bars[[_PARENT_COL]]
    start = earliest
    for pos in range(base_end, earliest - 1, -1):
        if bool(inside.iat[pos]):
            continue  # inside candles are skipped, not classified
        if _continues_trend(bars, pos, structure):
            start = pos + 1  # the base begins after the last trending candle
            break

    if start > base_end:
        return None
    if int((~inside.iloc[start : base_end + 1]).sum()) < MIN_BASE_CANDLES:
        return None
    return BaseSpan(start, base_end)


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
    find_base: object = find_base,
    select_boundary: object = select_boundary_from_base,
) -> Judgment:
    """A `Judgment` with all four predicates filled by recorded §11 decisions.

    Every default here is a decision, not a convenience: **D-29** for the two *meaningful* tests,
    **D-34** for `find_base`, **D-30** for `select_boundary`. Both arguments stay overridable --
    `select_boundary` so §2.2.7's sloping case can be supplied (**O-18**), `find_base` so a rival
    construction can be replayed against this one without editing the engine.

    **This signature used to require `find_base` and deliberately supply no default**, because the
    *obvious base* was the last unquantified term. **D-34** closed it on 2026-08-09; the argument
    is now defaulted rather than removed so that the alternative readings D-34 names as rejected
    stay cheap to test.
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
    "find_base",
    "is_meaningful_break",
    "is_meaningful_close",
    "select_boundary_from_base",
]
