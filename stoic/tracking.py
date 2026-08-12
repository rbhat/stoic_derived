"""Phase 7 -- tracking: turns an emitted `SIGNAL` into a closed (or still-open) trade outcome.

Design: `docs/PHASE7.md`. Sections 1, 2, 3, 3a, 4 and 7 are this module's spec; the module
docstring restates none of them -- open the source. The question stays `CLAUDE.md`'s: does our
implementation generate the trades the method calls for. An outcome is not a verdict -- counts per
class, never expectancy, never direction (Phase 9's charter).

**This module is pure: no disk I/O, no network, no clock read, no model, no threshold.** It is
never imported by L0-L5 -- pinned by an import-direction test, mirroring `stoic/fidelity.py`'s.
`stoic/judgment.py` is the only module in the repo allowed a threshold, fraction or tuned number
(`docs/CONSTRAINTS.md`); this module holds none.

**Two replays feed it, and L3's is not one of them** (`docs/PHASE7.md` §7): `emissions` is
`stoic.emission.replay_signals`'s frame (one `SIGNAL` row per trade to track -- `SUPPRESSED` and
`BREAK_EVEN` rows are read by nothing here, see convention 5 below), `sequence_events` is
`stoic.sequence.replay`'s frame (read only for the three `Event.INVALIDATED_*` members, §5.4.7).
`bars` is the 5m frame both replays ran over; `minute_bars` is the matching 1m spine, or `None`.

**Levels are reached by trading through them, strict, never an exact touch** (§2, mirroring
`stoic/entry.py`'s §5.2.3 convention): long stop `low < stop`, long TP1 `high > tp1`; short
mirrors on `high > stop` / `low < tp1`. §5.4.7 stays close-based, because it is L2's already-decided
event, read here rather than re-evaluated.

**Conventions fixed here, not in `docs/PHASE7.md`** (the same disposition `candles.py`,
`judgment.py`, `entry.py`, `gating.py` and `emission.py` each took):

1. **`bars`' span is inferred once from its own index, never assumed to be 5m** -- `track_outcomes`
   accepts `SignalType.SWING` and `POSITION` too, which per `VISION.md`'s Timeframes section manage
   on 60m and Daily. It calls **`stoic.sessions.infer_bar_span`**, which is where this repo already
   owned the question: `label_sessions` had inferred a span inline since Phase 0, and a second copy
   here would have been the third implementation (`stoic/bars.py` holds a `BAR_SPAN` table too).
   `docs/CONSTRAINTS.md`: *a layer that has to invent a predicate is usually reaching past a layer
   that already owns it.* The statistic is the **mode** of consecutive diffs, never a median -- a
   median averages the two middle diffs on an even count, so a 3-bar frame straddling the
   17:00-18:00 ET CME maintenance break reported 35m where the true span is 5m. It raises for fewer
   than two rows rather than falling back to a constant: a one-bar frame has no gap to measure, and
   a default that only ever fires in a fixture is a number pretending to be a measurement. Inferred
   once per `track_outcomes_records` call and threaded through, never recomputed per bar.
2. **`exit_ts` is the finest timestamp actually used to resolve the exit.** A bar resolved without
   drilling into `minute_bars` reports its own 1m-unresolved 5m timestamp; a bar resolved *by*
   drilling reports the specific 1m bar's timestamp that decided it -- the entire point of drilling
   is to read the real order, and throwing that resolution away at the return would make the drill
   pointless. `exit_pos` always indexes `bars` (the 5m frame), never a 1m position, regardless of
   which timestamp accompanies it.
3. **`TrackFlag.RESOLVED_ON_1M` marks only the bar that actually terminates the trade.** A drill on
   an earlier bar that finds nothing (the "dip to the stop before the trigger triggers" case, §3
   window 2) leaves no trace on the eventual outcome -- the trade did not close there, so nothing
   about that bar belongs on the row that describes where it did.
4. **The flatten `exit_ts` is always the flatten cutoff instant** (`stoic.sessions.flatten_cutoff_
   utc`), whether its price came from the 1m bar ending at the cutoff or the 5m fallback (§4) -- the
   instant itself is exact and does not depend on which frame supplied the price. On a session that
   ended before the cutoff ever arrived (convention 8), `exit_ts` is that session's own last bar's
   end instead, since the formulaic cutoff instant never actually occurred that day.
5. **`EmissionEvent.BREAK_EVEN` rows are never read.** §2 explains why a *full* exit at TP1's price
   is always what closes a trade that would otherwise have moved to break-even: TP1 is L3's frozen
   `step3_extreme` and D-25 fires break-even against that identical extreme with an identical strict
   trade-through test, so the bar that would trip break-even is always the bar that reaches TP1
   first. Since the two conditions are geometrically the same test against the same number, this
   module's own TP1 check already subsumes every case a `BREAK_EVEN` row could describe, and reading
   those rows would add nothing `SIGNAL` rows don't already carry. There is deliberately no
   `Outcome` member for it -- an enum value with no producer is a pin by *absence*, not by
   *observation*, and the first build shipped exactly that: a test asserting the member's count was
   zero, which held whatever the code did. The tripwire now lives in
   `tests/test_forward_test.py::test_tp1_and_the_break_even_trigger_are_the_same_frozen_number`,
   which drives the real engine over a fixture that trades through its own frozen Step 3 extreme
   and asserts L3's break-even level, L3's `ENTRY_FILLED` extreme and L5's `tp1` are one number.
   That can fail, and the day it does the removed class has to come back (O-7).
6. **`bars_held = exit_pos - fill_pos`** -- zero on the fill bar itself (a trade that fills and
   closes on the same bar, §3a).
7. **The fill-bar window and the flatten window are composed on every bar, not only when a 5m
   level was hit.** The trade's live span on the fill bar starts at the 1m trigger cross (or
   `bar_start` on a gap fill, where the trade is already live at the open); on the flatten bar it
   ends at the cutoff instead of `bar_end`. When the fill bar *is* the flatten bar and that span is
   empty or inverted -- the trigger crosses at or after the cutoff -- the order was never takeable,
   checked before any level test runs so a trade cannot be booked with an exit priced before its
   entry existed. `Outcome.NOT_TAKEN` records this: no exit fields, no P&L, ever.
8. **A holiday early close still flattens, at that session's own last bar.** `VISION.md` makes the
   flatten unconditional, but a session that closes early (2026-07-03, CME 13:00 ET) has no bar
   containing the formulaic 16:58 ET cutoff at all. When a session's cutoff bar is missing *and* a
   later session exists in the same frame -- so the gap is a real early close, not simply where the
   frame's data ends -- that session's last bar in `bars` is used as its flatten bar instead,
   flagged `TrackFlag.FLATTEN_SESSION_END`, priced directly off that bar's own close (no 1m lookup:
   there is no cutoff instant inside the frame for a 1m bar to end at). A frame's own trailing
   session, with no later session to confirm the gap is real rather than incomplete data, is left
   alone -- it may still resolve to `Outcome.OPEN`.
9. **An unresolvable level order on the flatten bar still resolves to `Outcome.FLATTEN`.** The
   trade's fate at the cutoff is certain -- it is flat, at a known price -- even when the 1m spine
   cannot say whether the stop or TP1 would have come first inside the bar. Discarding that
   certainty for `Outcome.AMBIGUOUS` would throw away a fact the bar itself does not leave in doubt.
   `TrackFlag.FLATTEN_LEVEL_ORDER_UNRESOLVED` records that the order was unresolved; `AMBIGUOUS`
   stays the answer everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from stoic.emission import EmissionEvent, SignalType
from stoic.sequence import Event
from stoic.sessions import flatten_cutoff_utc, infer_bar_span, session_date
from stoic.structure import Direction

_INVALIDATIONS: frozenset[Event] = frozenset(
    {
        Event.INVALIDATED_OPPOSITE_STEP_3,
        Event.INVALIDATED_MA_CLOSE,
        Event.INVALIDATED_BOUNDARY_CLOSE,
    }
)


class Outcome(StrEnum):
    STOP = "stop"
    TP1 = "tp1"
    INVALIDATED = "invalidated"
    FLATTEN = "flatten"
    NOT_TAKEN = "not_taken"
    AMBIGUOUS = "ambiguous"
    OPEN = "open"


class TrackFlag(StrEnum):
    GAP_BEYOND_TP1 = "gap_beyond_tp1"
    RESOLVED_ON_1M = "resolved_on_1m"
    UNRESOLVED_NO_1M = "unresolved_no_1m"
    UNRESOLVED_1M_AMBIGUOUS = "unresolved_1m_ambiguous"
    FLATTEN_5M_FALLBACK = "flatten_5m_fallback"
    FLATTEN_SESSION_END = "flatten_session_end"
    FLATTEN_LEVEL_ORDER_UNRESOLVED = "flatten_level_order_unresolved"
    FILLED_AFTER_CUTOFF = "filled_after_cutoff"


@dataclass(frozen=True)
class TradeOutcome:
    """One `SIGNAL`'s life from fill to close (or still-open). `flags` is always a tuple, `()`
    when none apply -- never `None`, so a caller can always iterate it."""

    signal_id: str
    direction: Direction
    fill_pos: int
    fill_ts: pd.Timestamp
    fill: float
    stop: float
    tp1: float | None
    r: float
    outcome: Outcome
    exit_pos: int | None
    exit_ts: pd.Timestamp | None
    exit_price: float | None
    bars_held: int | None
    r_realized: float | None
    flags: tuple[TrackFlag, ...]


# ---------------------------------------------------------------------------
# The flatten bar, per session (§4)
# ---------------------------------------------------------------------------


def _flatten_bar_cutoffs(
    bars: pd.DataFrame, type_: SignalType, bar_span: pd.Timedelta
) -> tuple[dict[int, pd.Timestamp], frozenset[int]]:
    """Position -> flatten cutoff instant, for every session's flatten bar in `bars`, plus the
    positions that are a session-end fallback rather than a real cutoff-containing bar (A3, §1
    convention 8): a holiday early close (2026-07-03, CME closed 13:00 ET) leaves no bar
    containing the formulaic 16:58 ET cutoff for that session's date at all -- silently producing
    no flatten there would let a trade ride into the next session, contradicting `VISION.md`'s
    unconditional flatten. When a session's cutoff bar is missing, that session's own **last** bar
    in `bars` becomes its flatten bar instead, keyed to its own end instant -- but only when a
    *later* session also appears in `bars`, which is what tells a real gap (more data exists past
    it) apart from the frame simply ending mid-session (no more data exists, so nothing here can
    say whether the cutoff would have been reached). The frame's own trailing session is therefore
    never given this fallback.

    `SignalType.POSITION` never flattens (§2). Finds the bar **containing** the cutoff via
    `index.searchsorted`, never `stoic.sessions.label_sessions`' `past_flatten` -- `past_flatten`
    is 0 for every 5m bar by construction (the cutoff sits inside a 2-minute window no 5m bar can
    start in), which is the trap `docs/STATE.md` names.
    """
    if type_ is SignalType.POSITION or len(bars) == 0:
        return {}, frozenset()
    sd = session_date(bars.index)
    dates = sorted(set(sd))
    cutoffs: dict[int, pd.Timestamp] = {}
    covered: set = set()
    for date, cutoff in zip(dates, flatten_cutoff_utc(dates), strict=True):
        pos = int(bars.index.searchsorted(cutoff, side="right")) - 1
        if 0 <= pos < len(bars) and bars.index[pos] <= cutoff < bars.index[pos] + bar_span:
            cutoffs[pos] = cutoff
            covered.add(date)

    session_end: set[int] = set()
    last_date = dates[-1] if dates else None
    for date in dates:
        if date in covered or date == last_date:
            continue
        session_positions = sd.index[sd == date]
        if len(session_positions) == 0:
            continue
        last_pos = bars.index.get_loc(session_positions[-1])
        cutoffs[last_pos] = bars.index[last_pos] + bar_span
        session_end.add(last_pos)
    return cutoffs, frozenset(session_end)


def _flatten_exit(
    bars: pd.DataFrame,
    minute_bars: pd.DataFrame | None,
    pos: int,
    cutoff: pd.Timestamp,
    *,
    is_session_end: bool,
) -> tuple[float, tuple[TrackFlag, ...]]:
    """The flatten exit price (§4, A2, A3): the 1m bar **ending** at the cutoff (index
    `cutoff - 1min`, the price at exactly the cutoff instant), or the containing 5m bar's close,
    flagged, when that 1m bar is missing. The bar *starting* at the cutoff is never read -- its
    close is struck a minute late, past the cutoff §3 already treats as the end of the live span.
    On a session-end fallback (`is_session_end`, §1 convention 8) `cutoff` is that session's own
    last bar's end rather than a formulaic instant nothing in the frame reaches -- priced directly
    off that bar's own close, flagged `FLATTEN_SESSION_END`, with no 1m lookup at all.
    """
    if is_session_end:
        return float(bars["close"].iat[pos]), (TrackFlag.FLATTEN_SESSION_END,)
    prior_minute_start = cutoff - pd.Timedelta(minutes=1)
    if minute_bars is not None and prior_minute_start in minute_bars.index:
        return float(minute_bars.loc[prior_minute_start, "close"]), ()
    return float(bars["close"].iat[pos]), (TrackFlag.FLATTEN_5M_FALLBACK,)


# ---------------------------------------------------------------------------
# §5.4.7 invalidation lookup (L2's event, read here, never re-evaluated)
# ---------------------------------------------------------------------------


def _invalidation_positions(
    sequence_events: pd.DataFrame, direction: Direction
) -> frozenset[int]:
    """Every position at which L2 emitted any of §5.4.7a-c for `direction`.

    Enum-normalised on both sides (`Direction(...)`, `Event(...)`) rather than `.astype(str)`
    against a retyped literal -- `docs/CONSTRAINTS.md`'s named defect class: real enum values are
    lowercase and a hand-retyped uppercase literal matches nothing on real data while a fixture
    using the same wrong casing keeps passing.
    """
    if sequence_events.empty:
        return frozenset()
    dirs = sequence_events["direction"].map(Direction)
    evs = sequence_events["event"].map(Event)
    mask = (dirs == direction) & evs.isin(_INVALIDATIONS)
    return frozenset(int(p) for p in sequence_events.loc[mask, "pos"])


# ---------------------------------------------------------------------------
# The intrabar rule -- one function, three spans (§3)
# ---------------------------------------------------------------------------


def _bar_hits(
    bar_high: float, bar_low: float, stop: float, tp1: float | None, *, bullish: bool
) -> tuple[bool, bool]:
    """Strict trade-through test against the 5m bar's own range (§2). `tp1=None` never hits."""
    stop_hit = (bar_low < stop) if bullish else (bar_high > stop)
    tp1_hit = tp1 is not None and ((bar_high > tp1) if bullish else (bar_low < tp1))
    return stop_hit, tp1_hit


def _find_trigger_cross(
    minute_bars: pd.DataFrame | None,
    bar_start: pd.Timestamp,
    bar_end: pd.Timestamp,
    trigger: float,
    *,
    bullish: bool,
) -> pd.Timestamp | None:
    """The first 1m bar inside `[bar_start, bar_end)` trading through `trigger` -- the same
    gap-or-touch test `stoic/entry.py` uses for the fill (§5.3.7), at 1m resolution. `None` if
    `minute_bars` is absent or has no bars in the span (§3's "missing" case).
    """
    if minute_bars is None:
        return None
    window = minute_bars.loc[(minute_bars.index >= bar_start) & (minute_bars.index < bar_end)]
    if window.empty:
        return None
    for ts, row in window.iterrows():
        o, h, low = float(row["open"]), float(row["high"]), float(row["low"])
        if bullish:
            if o > trigger or h > trigger:
                return ts
        else:
            if o < trigger or low < trigger:
                return ts
    return None


def _drill(
    minute_bars: pd.DataFrame | None,
    span_start: pd.Timestamp,
    span_end: pd.Timestamp,
    stop: float,
    tp1: float | None,
    *,
    bullish: bool,
) -> tuple[str, pd.Timestamp | None, float | None, TrackFlag | None]:
    """Reads the real order of stop/TP1 inside `[span_start, span_end)` via `minute_bars`.

    Returns `(kind, ts, price, flag)` where `kind` is one of `"stop"`, `"tp1"`, `"none"` (neither
    reached in the span) or `"ambiguous"` (missing 1m coverage, or one 1m bar spans both levels --
    §3: never guessed). `ts`/`price`/`flag` are populated only for the kind they describe.
    """
    if minute_bars is None:
        return "ambiguous", None, None, TrackFlag.UNRESOLVED_NO_1M
    window = minute_bars.loc[(minute_bars.index >= span_start) & (minute_bars.index < span_end)]
    if window.empty:
        return "ambiguous", None, None, TrackFlag.UNRESOLVED_NO_1M
    for ts, row in window.iterrows():
        high, low = float(row["high"]), float(row["low"])
        stop_hit, tp1_hit = _bar_hits(high, low, stop, tp1, bullish=bullish)
        if stop_hit and tp1_hit:
            return "ambiguous", None, None, TrackFlag.UNRESOLVED_1M_AMBIGUOUS
        if stop_hit:
            return "stop", ts, stop, None
        if tp1_hit:
            return "tp1", ts, tp1, None
    return "none", None, None, None


# ---------------------------------------------------------------------------
# One trade
# ---------------------------------------------------------------------------


def _track_signal(
    bars: pd.DataFrame,
    minute_bars: pd.DataFrame | None,
    row: pd.Series,
    *,
    flatten_cutoffs: dict[int, pd.Timestamp],
    session_end_positions: frozenset[int],
    invalidation_positions: frozenset[int],
    bar_span: pd.Timedelta,
) -> TradeOutcome:
    direction = Direction(row["direction"])
    bullish = direction is Direction.BULLISH
    fill_pos = int(row["fill_pos"])
    fill = float(row["fill"])
    stop = float(row["stop"])
    trigger = float(row["trigger"])
    tp1 = None if pd.isna(row["tp1"]) else float(row["tp1"])
    r = float(row["r"])
    signal_id = str(row["signal_id"])
    fill_ts = bars.index[fill_pos]

    base = {
        "signal_id": signal_id,
        "direction": direction,
        "fill_pos": fill_pos,
        "fill_ts": fill_ts,
        "fill": fill,
        "stop": stop,
        "tp1": tp1,
        "r": r,
    }

    def realized(exit_price: float) -> float:
        return (exit_price - fill) / r if bullish else (fill - exit_price) / r

    def terminal(
        outcome: Outcome,
        pos: int,
        ts: pd.Timestamp,
        price: float,
        flags: tuple[TrackFlag, ...] = (),
    ) -> TradeOutcome:
        return TradeOutcome(
            **base,
            outcome=outcome,
            exit_pos=pos,
            exit_ts=ts,
            exit_price=price,
            bars_held=pos - fill_pos,
            r_realized=realized(price),
            flags=flags,
        )

    def ambiguous(flag: TrackFlag) -> TradeOutcome:
        return TradeOutcome(
            **base,
            outcome=Outcome.AMBIGUOUS,
            exit_pos=None,
            exit_ts=None,
            exit_price=None,
            bars_held=None,
            r_realized=None,
            flags=(flag,),
        )

    def not_taken() -> TradeOutcome:
        return TradeOutcome(
            **base,
            outcome=Outcome.NOT_TAKEN,
            exit_pos=None,
            exit_ts=None,
            exit_price=None,
            bars_held=None,
            r_realized=None,
            flags=(TrackFlag.FILLED_AFTER_CUTOFF,),
        )

    for pos in range(fill_pos, len(bars)):
        is_fill_bar = pos == fill_pos
        cutoff = flatten_cutoffs.get(pos)
        is_flatten_bar = cutoff is not None
        bar_start = bars.index[pos]
        bar_end = bar_start + bar_span
        bar_open = float(bars["open"].iat[pos])
        bar_high = float(bars["high"].iat[pos])
        bar_low = float(bars["low"].iat[pos])
        bar_close = float(bars["close"].iat[pos])

        # The live span on this bar (§1 convention 7, A1): starts at the 1m trigger cross on the
        # fill bar (`bar_start` itself on a gap fill, already live at the open), `bar_start` on
        # every later bar; ends at the flatten cutoff on the flatten bar, `bar_end` otherwise.
        # Composed on *every* bar, not only when a 5m level was hit -- checked before any outcome
        # is chosen, below.
        gap_fill = False
        if is_fill_bar:
            gap_fill = (bar_open > trigger) if bullish else (bar_open < trigger)
            span_start = bar_start if gap_fill else _find_trigger_cross(
                minute_bars, bar_start, bar_end, trigger, bullish=bullish
            )
        else:
            span_start = bar_start
        span_end = cutoff if is_flatten_bar else bar_end

        # The trade was never takeable: on the fill bar, which is also the flatten bar, the
        # trigger cross is at or after the cutoff -- the live span is empty or inverted. Checked
        # first, before the gap-beyond-TP1 read and before any level test, so nothing downstream
        # can book an exit priced before the entry existed.
        if is_fill_bar and is_flatten_bar and span_start is not None and span_start >= span_end:
            return not_taken()

        # §3a step 1 -- the fill bar only: a gap already beyond TP1 exits at the fill.
        if is_fill_bar and tp1 is not None:
            gapped = (fill > tp1) if bullish else (fill < tp1)
            if gapped:
                return terminal(
                    Outcome.TP1, fill_pos, fill_ts, fill, (TrackFlag.GAP_BEYOND_TP1,)
                )

        # §3a step 2 -- stop or TP1, per §3's windows.
        stop_hit_5m, tp1_hit_5m = _bar_hits(bar_high, bar_low, stop, tp1, bullish=bullish)
        if stop_hit_5m or tp1_hit_5m:
            two_level = stop_hit_5m and tp1_hit_5m
            needs_drill = two_level or (is_fill_bar and not gap_fill) or is_flatten_bar

            if not needs_drill:
                if stop_hit_5m:
                    return terminal(Outcome.STOP, pos, bar_start, stop)
                assert tp1 is not None  # tp1_hit_5m (the only other way in) requires it
                return terminal(Outcome.TP1, pos, bar_start, tp1)

            if is_fill_bar and not gap_fill and span_start is None:
                return ambiguous(TrackFlag.UNRESOLVED_NO_1M)

            kind, ts, price, flag = _drill(
                minute_bars, span_start, span_end, stop, tp1, bullish=bullish
            )
            if kind == "ambiguous":
                assert flag is not None
                if is_flatten_bar:
                    # A1's second face, and A4: the level order is unresolvable, but the trade's
                    # fate at the cutoff is not -- it is flat, at a known price. Never discard
                    # that certainty for AMBIGUOUS.
                    is_session_end = pos in session_end_positions
                    price, exit_flags = _flatten_exit(
                        bars, minute_bars, pos, cutoff, is_session_end=is_session_end
                    )
                    return terminal(
                        Outcome.FLATTEN, pos, cutoff, price,
                        (TrackFlag.FLATTEN_LEVEL_ORDER_UNRESOLVED, *exit_flags),
                    )
                return ambiguous(flag)
            if kind == "stop":
                assert ts is not None and price is not None
                return terminal(Outcome.STOP, pos, ts, price, (TrackFlag.RESOLVED_ON_1M,))
            if kind == "tp1":
                assert ts is not None and price is not None
                return terminal(Outcome.TP1, pos, ts, price, (TrackFlag.RESOLVED_ON_1M,))
            # kind == "none": nothing reached inside the live span -- fall through.

        # §3a step 4 -- the flatten bar, and only against §5.4.7 does the order invert.
        if is_flatten_bar:
            assert cutoff is not None
            is_session_end = pos in session_end_positions
            price, flags = _flatten_exit(
                bars, minute_bars, pos, cutoff, is_session_end=is_session_end
            )
            return terminal(Outcome.FLATTEN, pos, cutoff, price, flags)

        # §3a step 3 -- §5.4.7a-c, close-based, L2's event.
        if pos in invalidation_positions:
            return terminal(Outcome.INVALIDATED, pos, bar_start, bar_close)

        # Still open -- advance to the next bar.

    return TradeOutcome(
        **base,
        outcome=Outcome.OPEN,
        exit_pos=None,
        exit_ts=None,
        exit_price=None,
        bars_held=None,
        r_realized=None,
        flags=(),
    )


# ---------------------------------------------------------------------------
# The replay entry point
# ---------------------------------------------------------------------------

_COLUMNS = (
    "signal_id", "direction", "fill_pos", "fill_ts", "fill", "stop", "tp1", "r",
    "outcome", "exit_pos", "exit_ts", "exit_price", "bars_held", "r_realized", "flags",
)


def track_outcomes_records(
    bars: pd.DataFrame,
    *,
    emissions: pd.DataFrame,
    sequence_events: pd.DataFrame,
    minute_bars: pd.DataFrame | None,
    type_: SignalType,
) -> list[TradeOutcome]:
    """One `TradeOutcome` per emitted `SIGNAL` row in `emissions`, in emission order.

    `bars` must be the same 5m frame `stoic.sequence.replay` and `stoic.emission.replay_signals`
    ran over. `minute_bars` is the matching 1m spine (`None` if unavailable at all -- every drill
    then reports `TrackFlag.UNRESOLVED_NO_1M`, never an invented order).
    """
    bar_span = infer_bar_span(bars.index)
    flatten_cutoffs, session_end_positions = _flatten_bar_cutoffs(bars, type_, bar_span)
    inval_by_direction = {
        direction: _invalidation_positions(sequence_events, direction)
        for direction in (Direction.BULLISH, Direction.BEARISH)
    }

    is_signal = emissions["event"].map(EmissionEvent) == EmissionEvent.SIGNAL
    records: list[TradeOutcome] = []
    for _, row in emissions.loc[is_signal].iterrows():
        direction = Direction(row["direction"])
        records.append(
            _track_signal(
                bars,
                minute_bars,
                row,
                flatten_cutoffs=flatten_cutoffs,
                session_end_positions=session_end_positions,
                invalidation_positions=inval_by_direction[direction],
                bar_span=bar_span,
            )
        )
    return records


def _to_frame(records: list[TradeOutcome], bars: pd.DataFrame) -> pd.DataFrame:
    data: dict[str, list] = {c: [getattr(r, c) for r in records] for c in _COLUMNS}
    # Same schema whether `records` is empty or not (replay_signals' F8 discipline): positional
    # indices are nullable Int64, prices float64, ts columns bars.index.dtype, enums/tuples object.
    return pd.DataFrame(
        {
            "signal_id": pd.Series(data["signal_id"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "fill_pos": pd.Series(data["fill_pos"], dtype="Int64"),
            "fill_ts": pd.Series(data["fill_ts"], dtype=bars.index.dtype),
            "fill": pd.Series(data["fill"], dtype="float64"),
            "stop": pd.Series(data["stop"], dtype="float64"),
            "tp1": pd.Series(data["tp1"], dtype="float64"),
            "r": pd.Series(data["r"], dtype="float64"),
            "outcome": pd.Series(data["outcome"], dtype="object"),
            "exit_pos": pd.Series(data["exit_pos"], dtype="Int64"),
            "exit_ts": pd.Series(data["exit_ts"], dtype=bars.index.dtype),
            "exit_price": pd.Series(data["exit_price"], dtype="float64"),
            "bars_held": pd.Series(data["bars_held"], dtype="Int64"),
            "r_realized": pd.Series(data["r_realized"], dtype="float64"),
            "flags": pd.Series(data["flags"], dtype="object"),
        }
    )


def track_outcomes(
    bars: pd.DataFrame,
    *,
    emissions: pd.DataFrame,
    sequence_events: pd.DataFrame,
    minute_bars: pd.DataFrame | None,
    type_: SignalType,
) -> pd.DataFrame:
    """`track_outcomes_records`, flattened to one row per `SIGNAL`, columns in `TradeOutcome`
    field order. See that function's docstring for the frame requirements."""
    records = track_outcomes_records(
        bars,
        emissions=emissions,
        sequence_events=sequence_events,
        minute_bars=minute_bars,
        type_=type_,
    )
    return _to_frame(records, bars)


__all__ = [
    "Outcome",
    "TrackFlag",
    "TradeOutcome",
    "track_outcomes",
    "track_outcomes_records",
]
