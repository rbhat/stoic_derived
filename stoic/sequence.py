"""The Step 1 -> Step 2 -> Step 3 state machine (L2), and the events it emits.

Source: `docs/RULEBOOK.md` §2 in full, §3 (Step 3 High/Low), §5.4.7 (invalidation),
§6.3a-c (the Step 2 swing / fib anchor), and decisions **D-1, D-15, D-16, D-19, D-20, D-21, D-24**
in §11. Open row **O-15** (§12) records the reset/invalidation asymmetry this module implements
as written, without reconciling it.

**Four terms are unquantified in the material and stay that way: Step 1's "meaningful" break/close
(§2.1.1 P, §2.1.4 J), an "obvious" base (§2.2.5 J), boundary selection (§2.2.6-§2.2.9 J), and
Confirmed Step 3's "meaningful close" (§2.3.4 P).** They enter this module as the four fields of
`Judgment` -- injected predicates with **no defaults**, not even "reasonable" ones. This module
enforces every mechanical clause itself (the close-beyond-both-MAs test, the trade-through test,
the close-beyond-boundary test, the reset test, the invalidation tests) and asks a predicate only
about the unquantified adjective, only once its mechanical precondition already holds.

**§2.2.8's no-hindsight constraint is structural, not a convention.** `find_base` is handed a
frame truncated at the bar being evaluated (`bars.iloc[: pos + 1]`); `select_boundary` is handed a
frame truncated at the base's own last bar (`bars.iloc[: base.end + 1]`) -- "boundary selection
must be a function of bars up to and including the last base bar," per the §2.2.8 engine note, not
of whatever bar the machine happens to be evaluating. Neither predicate can physically see a bar
that has not happened yet. The same `bars.iloc[: pos + 1]` truncation is applied to
`is_meaningful_break` and `is_meaningful_close`, on the general no-lookahead principle this whole
codebase holds to, even though the rulebook's own hindsight language (§2.2.8) names only the
base/boundary pair.

**Two lifetimes, not one.** `Stage` is the count's own progress (§2.1-§2.4): it opens at Step 1
and is wiped by the §2.4.3/D-15 reset, including the directional state §2.5/D-21 licenses for
continuation entries -- that state ends at the same reset (§2.5.8). The **invalidatable
sequence** (§5.4.7, D-24) is a different, longer-lived object: it opens at `STEP_3_CONFIRMED`,
records the boundary already selected under §2.2.8, and *survives* the reset and every later Step
1/base/break of the count -- because §6.5 holds the *position* "until the complete opposite one
two three pattern confirms," which can be many bars after the count has already reset and started
over. It closes at the first of §5.4.7a-c to fire; a later `STEP_3_CONFIRMED` in the same
direction replaces it. Gating invalidation on `Stage` -- as an earlier version of this module did
-- conflates the two lifetimes and makes §5.4.7a's "opposite Step 3, possibly many bars away"
unreachable, since the two directions' Step 1 and reset predicates are character-identical.

Both directions are tracked as two independent `SequenceMachine`s over the same bars. The only
cross-link between them is §5.4.7a: a confirmed opposite Step 3 invalidates an open invalidatable
sequence on the other side. `replay` wires this symmetrically and per bar: both machines' counts
run first, from pre-bar state, then both machines' invalidations run against those results -- see
`replay`'s docstring.

Pure functions and one small stateful stepper (`SequenceMachine`) over bars: no disk I/O, no
network, no clock reads, no accumulation the caller cannot inspect via `SequenceMachine.state`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

import numpy as np
import pandas as pd

from stoic.structure import Direction

# ---------------------------------------------------------------------------
# Injected-judgment protocol (§1 of the build spec)
# ---------------------------------------------------------------------------


class Boundary(Protocol):
    """A Step 2/3 boundary, evaluated per bar (§2.2.7: not necessarily horizontal)."""

    def level_at(self, pos: int) -> float: ...


@dataclass(frozen=True)
class HorizontalBoundary:
    """The one concrete `Boundary` this module ships: a flat price level.

    A sloped boundary (§2.2.7's up-sloping bullish line) is the injected selector's business, not
    this module's -- `select_boundary` may return any object satisfying `Boundary`.
    """

    price: float

    def level_at(self, pos: int) -> float:
        return self.price


@dataclass(frozen=True)
class BaseSpan:
    """Positional span of a completed Step 2 base, inclusive of both ends."""

    start: int
    end: int


@dataclass(frozen=True)
class Judgment:
    """The four terms `docs/RULEBOOK.md` leaves to the human. No defaults, by design.

    `is_meaningful_break` and `find_base` are asked only once their mechanical precondition
    already holds (§2.1: close beyond both MAs). `select_boundary` returning `None` means §2.2.9's
    "two boundaries look equally valid" -- wait, not error; this module re-asks on the next bar.
    `is_meaningful_close` is asked only once the mechanical precondition already holds (§2.3.4/7:
    close beyond the boundary).
    """

    is_meaningful_break: Callable[[pd.DataFrame, int, Direction], bool]
    find_base: Callable[[pd.DataFrame, int, Direction], BaseSpan | None]
    select_boundary: Callable[[pd.DataFrame, BaseSpan, Direction], Boundary | None]
    is_meaningful_close: Callable[[pd.DataFrame, int, Boundary, Direction], bool]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class Event(StrEnum):
    STEP_1 = "step_1"  # Sec2.1: meaningful break and close beyond both 10/20
    BASE_SELECTED = "base_selected"  # Sec2.2: base found AND boundary selected
    STEP_3_BREAK = "step_3_break"  # Sec2.3.1: trades through the boundary, direction of Step 1
    STEP_3_CONFIRMED = "step_3_confirmed"  # Sec2.3.4: meaningful close beyond it
    RESET = "reset"  # Sec2.4.3 / D-15
    INVALIDATED_OPPOSITE_STEP_3 = "invalidated_opposite_step_3"  # Sec5.4.7a
    INVALIDATED_MA_CLOSE = "invalidated_ma_close"  # Sec5.4.7b
    INVALIDATED_BOUNDARY_CLOSE = "invalidated_boundary_close"  # Sec5.4.7c


@dataclass(frozen=True)
class EventRecord:
    """One emitted event, with whichever payload fields apply to it. The rest stay `None`."""

    pos: int
    event: Event
    direction: Direction
    boundary_level: float | None = None
    base_start: int | None = None
    base_end: int | None = None
    step2_swing_pos: int | None = None
    step2_swing_price: float | None = None
    step3_extreme: float | None = None


# ---------------------------------------------------------------------------
# The single-direction state machine
# ---------------------------------------------------------------------------


class Stage(StrEnum):
    """Internal progress of one direction's count. Not an `Event` -- `SequenceState.stage` is
    what `SequenceMachine.state` exposes between events, for L3 to read while driving `step`.

    `Stage` is wiped by the §2.4.3/D-15 reset. It does **not** gate §5.4.7 invalidation -- see
    `InvalidatableSequence`, which has the longer lifetime §6.5 describes.
    """

    WAITING_STEP1 = "waiting_step1"
    AFTER_STEP1 = "after_step1"
    BASE_SELECTED = "base_selected"
    STEP3_BROKEN = "step3_broken"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class InvalidatableSequence:
    """The §5.4.7/D-24 invalidatable sequence -- opens at `STEP_3_CONFIRMED`, survives the
    §2.4.3 reset and everything the count does afterward, and closes at the first of §5.4.7a-c to
    fire. A longer-lived object than `Stage`; see the module docstring's "two lifetimes" note.

    `boundary` is the boundary already selected under §2.2.8 at the confirming bar -- "no new
    selection happens here" (§5.4.7c). `opened_pos` is the bar `STEP_3_CONFIRMED` fired on, kept
    only so a later replacement (a second `STEP_3_CONFIRMED` in the same direction) is visibly a
    new object, not a mutation of the old one.
    """

    boundary: Boundary
    opened_pos: int


@dataclass(frozen=True)
class SequenceState:
    """A `SequenceMachine`'s current state, readable after every `step` call.

    `step3_extreme` is the running Step 3 High (bullish) / Low (bearish) (§3.4, D-16): it starts
    at the Confirmed Step 3 bar's own high/low and keeps advancing while `stage == CONFIRMED`,
    across continuation entries (§3.7, D-21) -- it is never frozen here. It is scoped to `Stage`,
    same as the directional state of §2.5/D-21 it belongs to.

    `invalidatable` is scoped to §5.4.7/D-24 instead (see `InvalidatableSequence`) and outlives a
    `Stage` reset -- callers must not assume it is `None` just because `stage == WAITING_STEP1`.
    """

    stage: Stage = Stage.WAITING_STEP1
    step1_pos: int | None = None
    base: BaseSpan | None = None
    boundary: Boundary | None = None
    step2_swing_pos: int | None = None
    step2_swing_price: float | None = None
    confirmed_pos: int | None = None
    step3_extreme: float | None = None
    invalidatable: InvalidatableSequence | None = None


def _require_smas(bars: pd.DataFrame) -> None:
    missing = [c for c in ("sma_10", "sma_20") if c not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing {missing} -- call stoic.indicators.add_smas(bars) first")


class SequenceMachine:
    """One direction's Step 1 -> Step 2 -> Step 3 count, and its post-confirmation invalidations.

    Two phases, called separately so `replay` can interleave them symmetrically across both
    directions (F1's fix for the cross-link asymmetry):

    - `step_count` advances the §2.1-§2.4 count by one bar: reset, Step 1, Step 2, Step 3 break,
      Step 3 confirm. A `STEP_3_CONFIRMED` here (re-)opens `state.invalidatable`.
    - `step_invalidations` evaluates §5.4.7a-c against `state.invalidatable`, independent of
      `Stage`, and closes it on the first of the three to fire.

    `step` chains the two for a single direction driven standalone (by L3, or by a test that does
    not need the cross-link). `opposite_confirmed_this_bar` is edge-triggered: whether the *other*
    direction's machine emitted `STEP_3_CONFIRMED` on this exact bar, not whether it is currently
    in a confirmed `Stage` -- `replay` computes this from its own pass over both machines' counts.
    """

    def __init__(self, direction: Direction, judgment: Judgment) -> None:
        self.direction = direction
        self.judgment = judgment
        self._state = SequenceState()

    @property
    def state(self) -> SequenceState:
        return self._state

    def step_count(self, bars: pd.DataFrame, pos: int) -> list[EventRecord]:
        """Advance the §2.1-§2.4 count by exactly one bar. Does not evaluate §5.4.7 -- see
        `step_invalidations`.
        """
        _require_smas(bars)
        events: list[EventRecord] = []
        stage = self._state.stage
        bullish = self.direction == Direction.BULLISH

        close = float(bars["close"].iat[pos])
        high = float(bars["high"].iat[pos])
        low = float(bars["low"].iat[pos])
        sma10 = float(bars["sma_10"].iat[pos])
        sma20 = float(bars["sma_20"].iat[pos])
        view = bars.iloc[: pos + 1]

        # --- Reset (§2.4.3, D-15): bare close beyond both MAs against direction. Evaluated
        # before the running extreme advances (F8) so a RESET row carries the pre-bar extreme,
        # not this bar's own high/low. `invalidatable` survives the reset (F1) -- Stage's
        # lifetime (§2.5.8/D-21) is shorter than the invalidatable sequence's (§6.5).
        if stage != Stage.WAITING_STEP1:
            reset_fires = (
                (close < sma10 and close < sma20)
                if bullish
                else (close > sma10 and close > sma20)
            )
            if reset_fires:
                final_extreme = self._state.step3_extreme if stage == Stage.CONFIRMED else None
                events.append(
                    EventRecord(pos, Event.RESET, self.direction, step3_extreme=final_extreme)
                )
                self._state = SequenceState(invalidatable=self._state.invalidatable)
                return events

        # --- Step 3 High/Low running extreme (§3.4, D-16, D-21): advances while the directional
        # state (Stage.CONFIRMED) is open. Scoped to Stage -- §3.7's "one series per state" is
        # the §2.5 directional state, which the reset above already ends.
        if stage == Stage.CONFIRMED:
            extreme = self._state.step3_extreme
            assert extreme is not None
            new_extreme = max(extreme, high) if bullish else min(extreme, low)
            self._state = replace(self._state, step3_extreme=new_extreme)

        # --- Step 1 (§2.1) ---
        if stage == Stage.WAITING_STEP1:
            broke = (
                (close > sma10 and close > sma20) if bullish else (close < sma10 and close < sma20)
            )
            if broke and self.judgment.is_meaningful_break(view, pos, self.direction):
                events.append(EventRecord(pos, Event.STEP_1, self.direction))
                self._state = replace(self._state, stage=Stage.AFTER_STEP1, step1_pos=pos)

        # --- Step 2: base + boundary (§2.2) ---
        # D-34 makes the base a *state*, not a one-time selection: it is re-asked on every bar for
        # as long as it has never been broken, and the span it returns always ends at `pos - 1`.
        # So the boundary is re-read from bars strictly earlier than the one whose break is tested
        # below, which is what makes §2.2.8 literal rather than conventional -- F5 keeps enforcing
        # it. Once the stage is STEP3_BROKEN the line is "pre-selected" (§2.3.1) and freezes: F6's
        # re-break of a still-pending base must re-break the *same* line, or a failed break under
        # §2.3.7 would silently move the line it failed against.
        elif stage in (Stage.AFTER_STEP1, Stage.BASE_SELECTED):
            step1_pos = self._state.step1_pos
            assert step1_pos is not None
            base = self.judgment.find_base(view, step1_pos, self.direction)
            if base is None:
                boundary = None
            else:
                # F4: find_base must return a span inside [step1_pos, pos] -- a base that starts
                # before Step 1 or ends after the bar being evaluated is lookahead, not a base.
                if not (step1_pos <= base.start <= base.end <= pos):
                    raise ValueError(
                        f"find_base returned an invalid span for direction={self.direction}: "
                        f"step1_pos={step1_pos}, base=({base.start}, {base.end}), pos={pos} -- "
                        "must satisfy step1_pos <= base.start <= base.end <= pos"
                    )
                # F2: select_boundary sees bars up to and including the base's last bar (the
                # §2.2.8 engine note), which can be earlier than `pos` when the base is
                # recognised late -- not the fuller `view` truncated at `pos`.
                boundary = self.judgment.select_boundary(
                    bars.iloc[: base.end + 1], base, self.direction
                )
            if base is not None and boundary is not None:
                # Step 2 swing window is [step1_pos, base.end], inclusive of the Step 1 bar
                # (D-20/§6.3b); sliced from `view`, not `bars` (F4), and safe because the
                # span validation above already guarantees base.end <= pos. It widens with the
                # base under D-34, so the swing is re-read rather than kept from first selection.
                if bullish:
                    window = view["low"].iloc[step1_pos : base.end + 1].to_numpy()
                    offset = int(np.argmin(window))
                else:
                    window = view["high"].iloc[step1_pos : base.end + 1].to_numpy()
                    offset = int(np.argmax(window))
                swing_pos = step1_pos + offset
                swing_price = float(window[offset])

                # BASE_SELECTED is emitted once, on entry to the stage -- D-34. While the base
                # extends, the span and the line update silently: re-emitting per bar would make
                # the stream mostly noise, and STEP_3_BREAK already carries the level actually
                # broken. A base cancelled and later re-formed does emit again, because that is a
                # genuinely new selection rather than the same one growing.
                if stage == Stage.AFTER_STEP1:
                    events.append(
                        EventRecord(
                            pos,
                            Event.BASE_SELECTED,
                            self.direction,
                            boundary_level=boundary.level_at(pos),
                            base_start=base.start,
                            base_end=base.end,
                            step2_swing_pos=swing_pos,
                            step2_swing_price=swing_price,
                        )
                    )
                self._state = replace(
                    self._state,
                    stage=Stage.BASE_SELECTED,
                    base=base,
                    boundary=boundary,
                    step2_swing_pos=swing_pos,
                    step2_swing_price=swing_price,
                )
                stage = Stage.BASE_SELECTED
            elif stage == Stage.BASE_SELECTED:
                # The leg resumed (D-34), or no line could be drawn from the span (§2.2.9). The
                # base is cancelled, not frozen -- it never confirmed a Step 3, so nothing is
                # emitted, and the count waits at AFTER_STEP1 for the next one to form.
                self._state = replace(
                    self._state,
                    stage=Stage.AFTER_STEP1,
                    base=None,
                    boundary=None,
                    step2_swing_pos=None,
                    step2_swing_price=None,
                )
                stage = Stage.AFTER_STEP1

        # --- Step 3 break (§2.3.1, §2.3.2, F5, F6) ---
        if stage in (Stage.BASE_SELECTED, Stage.STEP3_BROKEN):
            base = self._state.base
            boundary = self._state.boundary
            assert base is not None and boundary is not None
            # F5: the boundary must be markable BEFORE the break (§2.2.5). Under D-34 the default
            # find_base already guarantees `base.end == pos - 1`, so §2.2.8 is enforced there and
            # this guard is vacuously true on every evaluation. It stays because an *injected*
            # predicate (D-34 names three rejected constructions, and O-18 needs a fourth) may
            # return a span ending at `pos`, and such a span must not be breakable on its own bar.
            if base.end < pos:
                level = boundary.level_at(pos)
                broke = high > level if bullish else low < level
                if broke:
                    # F6: every trade-through of a still-pending base is a fresh entry
                    # opportunity (§2.3.3), not just the first one.
                    #
                    # The span and the Step 2 swing are carried here, not just on BASE_SELECTED:
                    # under D-34 that event fires once, on the first bar a base exists, while the
                    # span keeps growing behind it. Without these fields the only recorded value
                    # of D-20's fib anchor would be the first-bar one, which the state that
                    # actually drove the break can contradict.
                    events.append(
                        EventRecord(
                            pos,
                            Event.STEP_3_BREAK,
                            self.direction,
                            boundary_level=level,
                            base_start=base.start,
                            base_end=base.end,
                            step2_swing_pos=self._state.step2_swing_pos,
                            step2_swing_price=self._state.step2_swing_price,
                        )
                    )
                    if stage == Stage.BASE_SELECTED:
                        self._state = replace(self._state, stage=Stage.STEP3_BROKEN)
                    stage = Stage.STEP3_BROKEN

        # --- Confirmed Step 3 (§2.3.4, §2.3.7) ---
        if stage == Stage.STEP3_BROKEN:
            boundary = self._state.boundary
            assert boundary is not None
            level = boundary.level_at(pos)
            beyond = close > level if bullish else close < level
            if beyond and self.judgment.is_meaningful_close(view, pos, boundary, self.direction):
                extreme = high if bullish else low
                events.append(
                    EventRecord(
                        pos,
                        Event.STEP_3_CONFIRMED,
                        self.direction,
                        boundary_level=level,
                        step3_extreme=extreme,
                    )
                )
                # F1: (re-)open the invalidatable sequence with the boundary already selected
                # under §2.2.8 -- no new selection happens here. It outlives Stage from here on:
                # only step_invalidations (§5.4.7a-c) closes it.
                self._state = replace(
                    self._state,
                    stage=Stage.CONFIRMED,
                    confirmed_pos=pos,
                    step3_extreme=extreme,
                    invalidatable=InvalidatableSequence(boundary=boundary, opened_pos=pos),
                )

        return events

    def step_invalidations(
        self,
        bars: pd.DataFrame,
        pos: int,
        *,
        opposite_confirmed_this_bar: bool = False,
    ) -> list[EventRecord]:
        """Evaluate §5.4.7a-c against the open invalidatable sequence, if any (F1).

        Independent of `Stage`: fires for any direction with an open `state.invalidatable`,
        regardless of that direction's current `Stage`. Closes the sequence on the first of a/b/c
        to fire this call -- which is also what removes the duplicate-emission defect a condition
        holding for several consecutive bars used to produce; no separate latch needed.
        """
        inv = self._state.invalidatable
        if inv is None:
            return []

        bullish = self.direction == Direction.BULLISH
        close = float(bars["close"].iat[pos])
        high = float(bars["high"].iat[pos])
        low = float(bars["low"].iat[pos])
        sma10 = float(bars["sma_10"].iat[pos])
        sma20 = float(bars["sma_20"].iat[pos])

        events: list[EventRecord] = []

        # a -- the confirmed opposite Step 3 (§5.4.7a). Edge-triggered: fires on the bar the
        # opposite machine emits STEP_3_CONFIRMED, not on every bar it remains confirmed.
        if opposite_confirmed_this_bar:
            events.append(EventRecord(pos, Event.INVALIDATED_OPPOSITE_STEP_3, self.direction))

        # b -- a strong close beyond the 10/20 against the direction (§5.4.7b, D-24: >= 10% of
        # the candle's own high-low range).
        rng = high - low
        if bullish:
            ma_floor = min(sma10, sma20)
            if close < ma_floor and (ma_floor - close) >= 0.10 * rng:
                events.append(EventRecord(pos, Event.INVALIDATED_MA_CLOSE, self.direction))
        else:
            ma_ceiling = max(sma10, sma20)
            if close > ma_ceiling and (close - ma_ceiling) >= 0.10 * rng:
                events.append(EventRecord(pos, Event.INVALIDATED_MA_CLOSE, self.direction))

        # c -- a close beyond the Step 2 boundary against the direction (§5.4.7c). Close-only: a
        # trade-through alone does not invalidate. Tested against `inv.boundary` -- the boundary
        # recorded when this invalidatable sequence opened -- not `self._state.boundary`, which a
        # reset can already have wiped (F1).
        level = inv.boundary.level_at(pos)
        boundary_close_invalid = close < level if bullish else close > level
        if boundary_close_invalid:
            events.append(
                EventRecord(
                    pos, Event.INVALIDATED_BOUNDARY_CLOSE, self.direction, boundary_level=level
                )
            )

        if events:
            self._state = replace(self._state, invalidatable=None)

        return events

    def step(
        self,
        bars: pd.DataFrame,
        pos: int,
        *,
        opposite_confirmed_this_bar: bool = False,
    ) -> list[EventRecord]:
        """`step_count` then `step_invalidations`, for a single direction driven standalone.

        `replay` does not call this -- it calls the two phases directly across both directions,
        so `opposite_confirmed_this_bar` can be computed from this bar's count results (F1).
        """
        events = self.step_count(bars, pos)
        events += self.step_invalidations(
            bars, pos, opposite_confirmed_this_bar=opposite_confirmed_this_bar
        )
        return events


# ---------------------------------------------------------------------------
# The replay entry point
# ---------------------------------------------------------------------------

_PAYLOAD_COLUMNS = (
    "pos",
    "ts",
    "event",
    "direction",
    "boundary_level",
    "base_start",
    "base_end",
    "step2_swing_pos",
    "step2_swing_price",
    "step3_extreme",
)


def replay(bars: pd.DataFrame, judgment: Judgment) -> pd.DataFrame:
    """Run both directions' `SequenceMachine`s over `bars`, one row per emitted event.

    `bars` must already carry `sma_10` and `sma_20` (`stoic.indicators.add_smas`) -- this module
    never computes them (the caller chooses the timeframe, D-7).

    **Two passes per bar (F1).** Pass 1 runs both machines' `step_count` from pre-bar state and
    records whether each emitted `STEP_3_CONFIRMED` on this bar. Pass 2 runs both machines'
    `step_invalidations`, each fed the *other* direction's pass-1 flag. Neither pass has one
    machine reading the other's state, so the order the two machines are stepped in cannot change
    the output -- unlike a single-pass version, where one direction would see the other's
    pre-bar state and the other would see its just-updated state.
    """
    _require_smas(bars)

    bullish = SequenceMachine(Direction.BULLISH, judgment)
    bearish = SequenceMachine(Direction.BEARISH, judgment)

    records: list[EventRecord] = []
    for pos in range(len(bars)):
        bull_count_events = bullish.step_count(bars, pos)
        bear_count_events = bearish.step_count(bars, pos)
        records.extend(bull_count_events)
        records.extend(bear_count_events)

        bull_confirmed_this_bar = any(
            e.event == Event.STEP_3_CONFIRMED for e in bull_count_events
        )
        bear_confirmed_this_bar = any(
            e.event == Event.STEP_3_CONFIRMED for e in bear_count_events
        )

        records.extend(
            bullish.step_invalidations(
                bars, pos, opposite_confirmed_this_bar=bear_confirmed_this_bar
            )
        )
        records.extend(
            bearish.step_invalidations(
                bars, pos, opposite_confirmed_this_bar=bull_confirmed_this_bar
            )
        )

    data: dict[str, list] = {c: [] for c in _PAYLOAD_COLUMNS}
    for r in records:
        data["pos"].append(r.pos)
        data["ts"].append(bars.index[r.pos])
        data["event"].append(r.event)
        data["direction"].append(r.direction)
        data["boundary_level"].append(r.boundary_level)
        data["base_start"].append(r.base_start)
        data["base_end"].append(r.base_end)
        data["step2_swing_pos"].append(r.step2_swing_pos)
        data["step2_swing_price"].append(r.step2_swing_price)
        data["step3_extreme"].append(r.step3_extreme)

    # F8: base_start/base_end/step2_swing_pos are positional indices, not floats -- nullable
    # Int64, not the float64 an all-`None`/mixed column silently becomes. Same schema whether
    # `records` is empty or not, so an empty replay is not distinguishable by dtype alone.
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=bars.index.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "boundary_level": pd.Series(data["boundary_level"], dtype="float64"),
            "base_start": pd.Series(data["base_start"], dtype="Int64"),
            "base_end": pd.Series(data["base_end"], dtype="Int64"),
            "step2_swing_pos": pd.Series(data["step2_swing_pos"], dtype="Int64"),
            "step2_swing_price": pd.Series(data["step2_swing_price"], dtype="float64"),
            "step3_extreme": pd.Series(data["step3_extreme"], dtype="float64"),
        }
    )


__all__ = [
    "BaseSpan",
    "Boundary",
    "Event",
    "EventRecord",
    "HorizontalBoundary",
    "InvalidatableSequence",
    "Judgment",
    "SequenceMachine",
    "SequenceState",
    "Stage",
    "replay",
]
