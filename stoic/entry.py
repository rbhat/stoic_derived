"""L3 -- the PTB entry layer: the working stop order, the fill, the stop, break-even.

Source: `docs/RULEBOOK.md` §2.5 (continuation entries), §3.4-3.7 (the Step 3 High/Low, its
freeze at fill -- **D-16**, **D-21**), §5.2.1a/§5.2.3a/§5.2.8-§5.2.8a (where the pullback begins,
the order level -- **D-12**, the inside-bar exclusion -- **D-23**), §5.3.1-§5.3.10 (activation,
the re-anchor walk -- **D-17**, the gap fill -- **D-22**), §5.4.1/§5.4.4/§5.4.5/§5.4.7-§5.4.7c
(the stop -- **D-10**/**D-18**, break-even -- **D-25**, invalidation -- **D-24**), and the `docs/
PLAN.md` Phase 5 layer table's L3 row. Open row **O-15** (§12) governs why a `RESET` does not
cancel a working order; open row **O-10** (§5.4.6) is why there is no minimum-R gate here.

L3 **consumes** L1 (`stoic.structure.opens_pullback`, `stoic.candles.candle_structure`) and L2
(`stoic.sequence`'s `EventRecord`s and running Step 3 extreme). It derives neither. Explicitly
out of scope, per the Phase 5 layer table and the decisions named above: R (`|fill - PTB
extreme|`, L5's -- a fill is an execution fact, L3 reports it, it does not divide it), TP1/TP2,
the §5.4.7 invalidation *logic* (L3 only consumes the emitted events), position exit once
break-even has fired or the setup is invalidated, any minimum-R / "sufficient room" gate
(**O-10**), anticipatory entry (**D-11**), and which timeframe to run on (**D-7** -- the caller
passes the frame).

**No number, threshold or fraction lives here.** `stoic/judgment.py` is the only module allowed
to hold one (`docs/CONSTRAINTS.md`); this module needs none.

**Three conventions fixed here, not in `docs/RULEBOOK.md`** (same disposition as `candles.py`'s
inside-bar tie-break note and `judgment.py`'s two conventions):

1. **Strict inequality on the fill test.** An exact touch of the trigger does not fill -- the
   bullish test is `high > trigger`, not `high >= trigger` (bearish mirrors on `low < trigger`).
   §5.2.3 says "trades *above* it" and **D-12** fixes the level with no buffer, but neither pins
   strict-vs-inclusive; this module reads "above"/"below" literally.
2. **Simultaneous §5.4.7 conditions collapse to one cancellation.** The working order is
   singular, so if two or three of §5.4.7a-c fire on the same bar for the same direction, exactly
   one `ORDER_CANCELLED` is emitted and the order is cleared once -- not once per condition.
3. **`ORDER_CANCELLED` carries the cancelled order's own `anchor_pos`/`trigger`/`stop`.** A
   data-shape convenience for a caller inspecting the record, not a strategy rule.

Pure functions and one small stateful stepper (`EntryMachine`) over bars, mirroring
`stoic.sequence.SequenceMachine`: no disk I/O, no network, no clock reads, no model, no
randomness, no accumulation the caller cannot inspect via `EntryMachine.state`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import StrEnum

import pandas as pd

from stoic.candles import candle_structure
from stoic.sequence import Event, EventRecord, Judgment, SequenceMachine
from stoic.structure import Direction, opens_pullback

# ---------------------------------------------------------------------------
# Events and records
# ---------------------------------------------------------------------------


class EntryEvent(StrEnum):
    PTB_ANCHORED = "ptb_anchored"  # order placed or re-anchored (§5.2.3a, §5.3.5)
    ORDER_CANCELLED = "order_cancelled"  # §5.3.4a -- invalidated without an entry
    ENTRY_FILLED = "entry_filled"  # §5.3.2, §5.3.7
    STOP_TO_BREAK_EVEN = "stop_to_break_even"  # §5.4.5, D-25


@dataclass(frozen=True)
class EntryRecord:
    """One emitted event, with whichever payload fields apply to it. The rest stay `None`."""

    pos: int
    event: EntryEvent
    direction: Direction
    anchor_pos: int | None = None
    trigger: float | None = None
    stop: float | None = None
    fill: float | None = None
    step3_extreme: float | None = None  # frozen value, on ENTRY_FILLED


@dataclass(frozen=True)
class WorkingOrder:
    """The resting stop order, anchored to the current PTB candidate."""

    anchor_pos: int
    trigger: float  # PTB high (bullish) / low (bearish) -- D-12, no buffer
    stop: float  # the opposite extreme of the same PTB -- §5.4.1, D-10/D-18, no floor


@dataclass(frozen=True)
class OpenEntry:
    """A filled position L3 still tracks -- until its break-even fires or its setup ends."""

    fill_pos: int
    fill: float
    stop: float  # PTB extreme at fill; becomes `fill` at break-even
    step3_extreme: float | None  # frozen at fill (§3.5, D-16); None means no BE level


@dataclass(frozen=True)
class EntryState:
    """An `EntryMachine`'s current state, readable after every `step` call."""

    armed: bool = False  # §2.5 directional state open
    scan_from: int | None = None  # look for a pullback opening strictly after this bar
    order: WorkingOrder | None = None
    positions: tuple[OpenEntry, ...] = ()
    last_step3_extreme: float | None = None  # latch; see the module docstring's "frozen extreme"


_INVALIDATIONS = (
    Event.INVALIDATED_OPPOSITE_STEP_3,
    Event.INVALIDATED_MA_CLOSE,
    Event.INVALIDATED_BOUNDARY_CLOSE,
)


def _ptb_extremes(bars: pd.DataFrame, pos: int, direction: Direction) -> tuple[float, float]:
    """(trigger, stop) for the PTB candidate at `pos` -- §5.2.3a / §5.4.1: entry sits at one of
    the PTB's own extremes, the stop at the opposite one. No buffer (D-12), no floor (D-18).
    """
    high = float(bars["high"].iat[pos])
    low = float(bars["low"].iat[pos])
    if direction == Direction.BULLISH:
        return high, low
    return low, high


# ---------------------------------------------------------------------------
# The single-direction state machine
# ---------------------------------------------------------------------------


class EntryMachine:
    """One direction's PTB walk: the working order, its fill, and break-even tracking.

    `state` is read-only from outside; `step` is the only way to advance it. Two `EntryMachine`s
    (one per `Direction`) are driven independently -- `replay_entries` wires the pair against the
    matching pair of `SequenceMachine`s, same pattern as `stoic.sequence`.
    """

    def __init__(self, direction: Direction) -> None:
        self.direction = direction
        self._state = EntryState()

    @property
    def state(self) -> EntryState:
        return self._state

    def step(
        self,
        bars: pd.DataFrame,
        pos: int,
        *,
        events: list[EventRecord],
        step3_extreme: float | None,
        structure: pd.DataFrame | None = None,
    ) -> list[EntryRecord]:
        """Advance this direction's state by exactly one bar.

        `events` -- this bar's L2 `EventRecord`s for this direction; rows for the other direction
        are ignored defensively (the caller is expected to have already filtered). `step3_extreme`
        -- L2's running Step 3 High/Low **as of before this bar was stepped** (the pre-bar value);
        may be `None`. `structure` -- a precomputed `candle_structure(bars)`; computed here
        (O(n)) if omitted, same disposition as `stoic.structure.opens_pullback`.

        **The order below is the design, not an implementation accident:**

        1. Latch the extreme -- so both the fill (2) and any later bar that latches nothing new
           can read a frozen number that already reflects this bar's L2 pass.
        2. Fill check, *before* L2 events are processed -- a fill is **intrabar**, while every
           §5.4.7 invalidation condition is **close-based** (the engine note under §5.4.7: "All
           three are close-based"). So on a bar that both fills and would invalidate, the fill
           happened first, in wall-clock terms, and must be recorded that way.
        3. Break-even, evaluated on every still-open position -- **including one that just filled
           this bar.** For a long, the trigger (a PTB high inside the pullback) sits below the
           Step 3 High, so a bar whose high reaches the Step 3 High necessarily traded through the
           trigger first: the intrabar order is determined by geometry, not assumed. The one
           exception is a gap fill *above* the frozen extreme, where the position opens already
           beyond its break-even level -- correctly firing break-even on the same bar.
        4. L2 events -- invalidation, (re)arming, reset.
        5. Anchor / re-anchor, at bar close. A bar that reaches this step without having filled
           has, by construction, not traded beyond the working order's trigger -- so it is still a
           bar of the continuing pullback. No separate "is the pullback still going" predicate is
           needed, and §5.3.3c forbids inventing one.
        """
        if structure is None:
            structure = candle_structure(bars)
        own_events = [e for e in events if e.direction == self.direction]

        bullish = self.direction == Direction.BULLISH
        open_ = float(bars["open"].iat[pos])
        high = float(bars["high"].iat[pos])
        low = float(bars["low"].iat[pos])

        state = self._state
        records: list[EntryRecord] = []

        # --- 1. Latch the extreme (the module docstring's "frozen extreme") ---
        latched = step3_extreme if step3_extreme is not None else state.last_step3_extreme
        for e in own_events:
            if e.event == Event.RESET and e.step3_extreme is not None:
                latched = e.step3_extreme
        state = replace(state, last_step3_extreme=latched)

        # --- 2. Fill check, before L2 events (fill is intrabar; §5.4.7 is close-based) ---
        if state.order is not None:
            order = state.order
            fill: float | None = None
            if bullish:
                if open_ > order.trigger:  # gap first -- never better than the trigger (§5.3.7)
                    fill = open_
                elif high > order.trigger:  # strict: an exact touch does not fill
                    fill = order.trigger
            else:
                if open_ < order.trigger:
                    fill = open_
                elif low < order.trigger:
                    fill = order.trigger

            if fill is not None:
                records.append(
                    EntryRecord(
                        pos,
                        EntryEvent.ENTRY_FILLED,
                        self.direction,
                        anchor_pos=order.anchor_pos,
                        trigger=order.trigger,
                        stop=order.stop,
                        fill=fill,
                        step3_extreme=state.last_step3_extreme,
                    )
                )
                new_position = OpenEntry(
                    fill_pos=pos,
                    fill=fill,
                    stop=order.stop,
                    step3_extreme=state.last_step3_extreme,
                )
                state = replace(
                    state,
                    order=None,
                    positions=(*state.positions, new_position),
                    scan_from=pos,  # the next pullback may only open strictly after this bar
                )

        # --- 3. Break-even (§5.4.5, D-25) -- evaluated on every open position, fill bar included
        remaining: list[OpenEntry] = []
        for entry in state.positions:
            extreme = entry.step3_extreme
            beyond = extreme is not None and (high > extreme if bullish else low < extreme)
            if beyond:
                records.append(
                    EntryRecord(
                        pos,
                        EntryEvent.STOP_TO_BREAK_EVEN,
                        self.direction,
                        fill=entry.fill,
                        stop=entry.fill,
                        step3_extreme=entry.step3_extreme,
                    )
                )
                # the position's one job is done -- §5.4.5 is the only stop move there is (§6.5b)
            else:
                remaining.append(entry)
        state = replace(state, positions=tuple(remaining))

        # --- 4. Process L2 events ---
        # a-c. Any of §5.4.7a-c: cancel a working order (if one exists), drop all positions,
        # disarm. Multiple conditions firing on the same bar still cancel exactly once (D-24,
        # D-17; module docstring convention 2).
        if any(e.event in _INVALIDATIONS for e in own_events):
            if state.order is not None:
                records.append(
                    EntryRecord(
                        pos,
                        EntryEvent.ORDER_CANCELLED,
                        self.direction,
                        anchor_pos=state.order.anchor_pos,
                        trigger=state.order.trigger,
                        stop=state.order.stop,
                    )
                )
            state = replace(state, order=None, positions=(), armed=False)

        # STEP_3_CONFIRMED: arm; only move scan_from if no walk is currently in progress -- an
        # active walk is not disturbed (§5.3.4a lists exactly two ways it ends).
        if any(e.event == Event.STEP_3_CONFIRMED for e in own_events):
            new_scan_from = pos if state.order is None else state.scan_from
            state = replace(state, armed=True, scan_from=new_scan_from)

        # RESET (§2.4.3, D-15): disarm -- no *new* pullback may be scanned. A reset does NOT
        # cancel a working order (O-15; §5.3.4a: "no third outcome and no timeout" -- only a fill
        # or §5.4.7a-c ends the walk).
        if any(e.event == Event.RESET for e in own_events):
            state = replace(state, armed=False)

        # --- 5. Anchor / re-anchor, at bar close ---
        if state.order is None:
            if (
                state.armed
                and state.scan_from is not None
                and pos > state.scan_from
                and opens_pullback(bars, pos, self.direction, structure)
            ):
                trigger, stop = _ptb_extremes(bars, pos, self.direction)
                state = replace(state, order=WorkingOrder(pos, trigger, stop))
                records.append(
                    EntryRecord(
                        pos,
                        EntryEvent.PTB_ANCHORED,
                        self.direction,
                        anchor_pos=pos,
                        trigger=trigger,
                        stop=stop,
                    )
                )
        else:
            # This bar did not fill (a fill would have cleared state.order in step 2).
            if bool(structure["is_inside"].iat[pos]):
                pass  # §5.3.5a: skip -- the order stays at the current anchor, not cancelled
            else:
                trigger, stop = _ptb_extremes(bars, pos, self.direction)
                state = replace(state, order=WorkingOrder(pos, trigger, stop))
                records.append(
                    EntryRecord(
                        pos,
                        EntryEvent.PTB_ANCHORED,
                        self.direction,
                        anchor_pos=pos,
                        trigger=trigger,
                        stop=stop,
                    )
                )

        self._state = state
        return records


# ---------------------------------------------------------------------------
# The shared per-bar wiring -- consumed by both replay entry points below and by
# `stoic.emission.replay_signals`, so there is exactly one implementation of the bar loop.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BarStep:
    """One bar's L2 events and L3 records, per direction. `*_sequence_events` is each direction's
    `step_count` events plus that same call's `step_invalidations` events, in that order -- the
    same list `EntryMachine.step` is fed as `events` below."""

    pos: int
    bull_entry_records: list[EntryRecord]
    bear_entry_records: list[EntryRecord]
    bull_sequence_events: list[EventRecord]
    bear_sequence_events: list[EventRecord]


def iter_replay_steps(bars: pd.DataFrame, judgment: Judgment) -> Iterator[BarStep]:
    """Run both directions' `SequenceMachine`s and `EntryMachine`s over `bars`, one `BarStep` per
    bar. This is the two-pass-per-bar structure `stoic.sequence.replay` uses, reused rather than
    reimplemented: per bar, capture each `SequenceMachine`'s pre-bar `step3_extreme`, run both
    `step_count`s, then both `step_invalidations` with the cross-linked confirmation flags exactly
    as `sequence.replay` does, then step each `EntryMachine` with that direction's events for the
    bar and its pre-bar extreme. `candle_structure(bars)` is computed once and passed to every call.

    `replay_entries` below flattens this into L3's own `EntryRecord` rows; `stoic.emission.
    replay_signals` consumes the same iterator to drive `SignalEmitter`s. Neither reimplements the
    loop.

    **This cannot run end to end today.** `find_base` is undecided (§2.2.5, D-3), so
    `stoic.judgment.decided_judgment()` requires it as an argument with no default. That is the
    correct state, not a gap this function needs to fill.
    """
    structure = candle_structure(bars)

    seq_bull = SequenceMachine(Direction.BULLISH, judgment)
    seq_bear = SequenceMachine(Direction.BEARISH, judgment)
    entry_bull = EntryMachine(Direction.BULLISH)
    entry_bear = EntryMachine(Direction.BEARISH)

    for pos in range(len(bars)):
        pre_bull_extreme = seq_bull.state.step3_extreme
        pre_bear_extreme = seq_bear.state.step3_extreme

        bull_count_events = seq_bull.step_count(bars, pos)
        bear_count_events = seq_bear.step_count(bars, pos)

        bull_confirmed_this_bar = any(
            e.event == Event.STEP_3_CONFIRMED for e in bull_count_events
        )
        bear_confirmed_this_bar = any(
            e.event == Event.STEP_3_CONFIRMED for e in bear_count_events
        )

        bull_inval_events = seq_bull.step_invalidations(
            bars, pos, opposite_confirmed_this_bar=bear_confirmed_this_bar
        )
        bear_inval_events = seq_bear.step_invalidations(
            bars, pos, opposite_confirmed_this_bar=bull_confirmed_this_bar
        )

        bull_sequence_events = bull_count_events + bull_inval_events
        bear_sequence_events = bear_count_events + bear_inval_events

        bull_entry_records = entry_bull.step(
            bars,
            pos,
            events=bull_sequence_events,
            step3_extreme=pre_bull_extreme,
            structure=structure,
        )
        bear_entry_records = entry_bear.step(
            bars,
            pos,
            events=bear_sequence_events,
            step3_extreme=pre_bear_extreme,
            structure=structure,
        )

        yield BarStep(
            pos=pos,
            bull_entry_records=bull_entry_records,
            bear_entry_records=bear_entry_records,
            bull_sequence_events=bull_sequence_events,
            bear_sequence_events=bear_sequence_events,
        )


# ---------------------------------------------------------------------------
# The replay entry point
# ---------------------------------------------------------------------------

_PAYLOAD_COLUMNS = ("pos", "ts", "event", "direction", "anchor_pos", "trigger", "stop", "fill",
                    "step3_extreme")


def replay_entries(bars: pd.DataFrame, judgment: Judgment) -> pd.DataFrame:
    """Run both directions' `SequenceMachine`s and `EntryMachine`s over `bars`, one row per
    emitted `EntryRecord`.

    Thin flattening layer over `iter_replay_steps` -- see that function's docstring for the
    per-bar wiring. Does **not** return L2's `EventRecord`s -- a caller that wants both calls
    `sequence.replay` too.
    """
    records: list[EntryRecord] = []
    for step in iter_replay_steps(bars, judgment):
        records.extend(step.bull_entry_records)
        records.extend(step.bear_entry_records)

    data: dict[str, list] = {c: [] for c in _PAYLOAD_COLUMNS}
    for r in records:
        data["pos"].append(r.pos)
        data["ts"].append(bars.index[r.pos])
        data["event"].append(r.event)
        data["direction"].append(r.direction)
        data["anchor_pos"].append(r.anchor_pos)
        data["trigger"].append(r.trigger)
        data["stop"].append(r.stop)
        data["fill"].append(r.fill)
        data["step3_extreme"].append(r.step3_extreme)

    # Same schema whether `records` is empty or not (sequence.replay's F8 discipline): positional
    # indices are nullable Int64, not the float64 an all-None/mixed column silently becomes.
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=bars.index.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "anchor_pos": pd.Series(data["anchor_pos"], dtype="Int64"),
            "trigger": pd.Series(data["trigger"], dtype="float64"),
            "stop": pd.Series(data["stop"], dtype="float64"),
            "fill": pd.Series(data["fill"], dtype="float64"),
            "step3_extreme": pd.Series(data["step3_extreme"], dtype="float64"),
        }
    )


__all__ = [
    "BarStep",
    "EntryEvent",
    "EntryMachine",
    "EntryRecord",
    "EntryState",
    "OpenEntry",
    "WorkingOrder",
    "iter_replay_steps",
    "replay_entries",
]
