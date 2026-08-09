"""L5 -- emission: turns an L3 fill into a `SignalRecord`, or a suppressed candidate.

Source: `docs/RULEBOOK.md` §3 (Step 3 High/Low, frozen at fill -- D-16), §5.3.7-§5.3.10 (fill
price, R from the fill not the trigger -- D-22), §5.4.1-§5.4.7 (stop, R, break-even -- D-18,
D-25 -- all built in L3, consumed here), §6.1/§6.2 (TP1/TP2 -- D-6), §7.1.1/§7.1.3 (the 50/200
*read*, kept distinct from L4's §7.1.2 *gate*), §7.5.5 (HTF alignment -- D-27), §9 (Type ->
setup timeframe / fast_chart -- D-7's 2026-08-08 amendment), and decisions **D-13, D-16, D-18,
D-19, D-20, D-21, D-22, D-24, D-25, D-26, D-27, D-31, D-32, D-33** in §11. `VISION.md` -- "What a
signal actually is" -- is the schema this fills in. **D-32 and D-33 were added to §11 on
2026-08-09 and are the two rows this module exists to implement**; everything else here is
already-settled rulebook, consumed rather than re-derived.

**No lookahead (D-32).** Every read this module makes -- the L4 gate call and both §7.1.1
confluence conditions -- happens at `anchor_pos` (`EntryRecord.anchor_pos` on `ENTRY_FILLED`),
the bar whose close placed or last re-anchored the working order (D-17), never at the fill bar.
D-32's own reasoning: D-19 makes the 50/200 gate a **close** read, while a stop-market fill is
**intrabar** (§5.3.7), so gating on the fill bar's own close would decide risk from a number that
does not exist yet when the order fills. One consequence recorded so it is not mistaken for a bug
later: on a **fast chart**, a passing gate already implies the anchor's close is beyond *both* the
50 and 200 in the trade direction, so `DIR_50`/`DIR_200` are constant-true on every emitted
Scalp/Day signal and the score varies only with the HTF input; the three vary independently only
on **slow charts** (Swing, Position), where gate 2 never fires (D-31).

**No threshold, fraction or tuned number lives here.** `stoic/judgment.py` is the only module in
the repo allowed to hold one (`docs/CONSTRAINTS.md`); this module needs none -- R is a
subtraction, the score is a count (D-33), and `ConfluenceScore.of` is `len(Confluence)`, a
structural count, not a tuned number.

**What this module deliberately does NOT (re-)implement** -- each a trap named so it is not
rebuilt:

- **No minimum-R / "sufficient room" gate** (§5.4.6, O-10, `m` unset). R is recorded, never
  gated on.
- **No anticipatory entry** (§5.5, D-11).
- **No trapped-side, break & retest, SFP or SBS** (§7.3, §8 -- all J, none built anywhere).
- **No no-edge-zone filter** (§7.4.2 O-9, §7.4.3 O-19). `stoic/levels.py` is not imported.
- **No HTF-alignment gate** (§7.5.5, D-27 -- it scores, it never blocks).
- **No climax detection and no lower-high cue** (§4 J, D-5 deferred; §6.5a, D-26). Both are
  annotate-only management cues; §4.3 is a hard constraint that neither may fire, suppress or
  invalidate a signal, and neither is built anywhere in this repo, this module included.
- **No second R.** Break-even (§5.4.5) moves the *stop*, not R (engine note on 5.4.4/5.4.5). The
  `BREAK_EVEN` emission carries the event only -- no prices, no recomputed R.
- **No trade tracking, no flatten, no ledger.** That is Phase 7.
- **No TP2 value.** §6.2/D-6 give the ratio (2.618) and D-20 gives the anchor swing (the Step 2
  swing), but a trend-extension tool takes **three** points and no rule pins them (O-7). `tp2` is
  always `None` in v1 -- not derived here.

**Conventions fixed here, not in `docs/RULEBOOK.md`** (same disposition `candles.py`,
`judgment.py`, `entry.py` and `gating.py` take):

1. **A non-finite (NaN) SMA means the confluence condition is absent, never present.** No
   yardstick to read a pass off, so not confirmed -- `gating.py` convention 3's precedent. In
   practice the gate has already blocked such a bar on a fast chart; on a slow chart the 200 can
   still be NaN, since gate 2 never runs there.
2. **A close exactly equal to an SMA means the condition is absent.** Strict `>`/`<`, matching
   `gating.py` convention 1.
3. **`htf=None` makes `HTF_STEP_3` absent, and the denominator stays 3.** A caller supplying no
   HTF frame tops out at 2 of 3, which is honest -- an unread condition is not a satisfied one.
   `of` never shrinks, so scores stay comparable across records.
4. **`BREAK_EVEN` links by `(direction, fill price)`** to the **earliest** emitted signal for
   that direction that has not yet broken even. `SignalEmitter` is one per direction, so price is
   the only remaining handle -- L3's `STOP_TO_BREAK_EVEN` carries `fill=entry.fill` and no
   `fill_pos`. A break-even for a **suppressed** candidate emits **nothing**: L3 does not know
   about gating and keeps tracking the position, but a suppressed candidate was never added to
   the open-signal queue, so no match is found. Residual noted rather than hidden: two
   same-direction entries filling at the identical price make the link ambiguous, and
   earliest-first is the tie-break (a FIFO queue, matched and popped in insertion order).
5. **`signal_id` is deterministic and clock-free**:
   `f"{source}:{instrument}:{type_}:{direction}:{signal_ts.isoformat()}"`. Same inputs, same id,
   every run -- `VISION.md` requires a trade id on every ledger row and the replay must be
   reproducible.
6. **`continuation` is `False` on the first emitted-or-suppressed fill of a directional state and
   `True` thereafter, reset on `Event.RESET` for that direction** (§2.5, D-13, D-21 -- one
   directional state, one Step 3 extreme series, N entries). Candidates are counted, not just
   emitted signals, so gating does not renumber the sequence -- a suppressed candidate still
   advances the count.
7. **Within one `step` call, `entry_records` are applied before `sequence_events`' `RESET`.** A
   fill landing on the same bar as a `RESET` for the same direction is therefore attributed to
   the directional state the reset is closing, not the one it opens -- the same ordering `entry.
   py` uses internally (a fill is intrabar, a reset-worthy close is not) and consistent with O-15
   (`RESET` does not cancel a working order, so a same-bar fill against the old order is real).

L5 **consumes** L3 (`stoic.entry.EntryRecord`, via `stoic.entry.iter_replay_steps`) and L4
(`stoic.gating.gate`, unchanged, called at the anchor bar), and takes an injected `HtfAlignment`
-- mirroring how `Judgment`'s predicates are injected into L2, since the HTF's own sequence is
the caller's to run and running it here would reach past a layer. It derives nothing L3 or L4
already computed: R is `|fill - stop|`, TP1 is L3's frozen `step3_extreme`, and the two MA gates
are `stoic.gating.gate`'s, not reimplemented.

Pure functions plus one small stateful stepper (`SignalEmitter`), mirroring `EntryMachine` and
`SequenceMachine`: no disk I/O, no network, no clock reads, no model, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

import numpy as np
import pandas as pd

from stoic.entry import BarStep, EntryEvent, EntryRecord, iter_replay_steps
from stoic.gating import GateDecision, GateReason, gate
from stoic.sequence import Event, EventRecord, Judgment
from stoic.structure import Direction

# ---------------------------------------------------------------------------
# Type -> setup timeframe / fast_chart (§9, D-7's 2026-08-08 amendment)
# ---------------------------------------------------------------------------


class SignalType(StrEnum):
    SCALP = "scalp"
    DAY = "day"
    SWING = "swing"
    POSITION = "position"


@dataclass(frozen=True)
class TypeSpec:
    """Setup timeframe and whether the 200 SMA gate applies (`fast_chart`, `gating.py`
    convention 4). The setup timeframe is **recorded**, never used to resample -- the caller
    passes bars already on that timeframe (§9, D-7: the sequence runs on the setup timeframe).
    """

    setup_tf: str
    fast_chart: bool


# §9's table, as amended by D-7 on 2026-08-08: Scalp and Day run wholly on the 5m (no 1m
# execution). `fast_chart` is derived from the Type here, never guessed by the caller
# (`gating.py` convention 4 -- `fast_chart` has no default and is never defaulted one layer up).
TYPE_SPECS: MappingProxyType[SignalType, TypeSpec] = MappingProxyType(
    {
        SignalType.SCALP: TypeSpec(setup_tf="5m", fast_chart=True),
        SignalType.DAY: TypeSpec(setup_tf="5m", fast_chart=True),
        SignalType.SWING: TypeSpec(setup_tf="60m", fast_chart=False),
        SignalType.POSITION: TypeSpec(setup_tf="1D", fast_chart=False),
    }
)


# ---------------------------------------------------------------------------
# Confluence (§7.1.1, §7.1.3, §7.5.5/D-27, D-32, D-33)
# ---------------------------------------------------------------------------


class Confluence(StrEnum):
    DIR_50 = "dir_50"  # §7.1.1 -- the read, distinct from L4's §7.1.2 gate
    DIR_200 = "dir_200"  # §7.1.1, §7.1.3 -- the 200 as higher-timeframe trend
    HTF_STEP_3 = "htf_step_3"  # §7.5.5, D-27 -- raises the score, never blocks


@dataclass(frozen=True)
class ConfluenceScore:
    present: tuple[Confluence, ...]  # declaration order
    score: int  # len(present) -- D-33, a plain count, no weights
    of: int  # len(Confluence) -- always 3, convention 3: htf=None never shrinks it


class HtfAlignment(Protocol):
    """§7.5.5 / D-27. Injected, exactly as `Judgment`'s predicates are injected into L2 -- the
    HTF's own sequence is the caller's to run, and running it here would reach past a layer."""

    def is_aligned(self, ts: pd.Timestamp, direction: Direction) -> bool: ...


def _sma_beyond(bars: pd.DataFrame, sma_col: str, pos: int, close: float, *, bullish: bool) -> bool:
    """One §7.1.1 direction read: is `close` strictly beyond `bars[sma_col]` at `pos`? NaN and an
    exact tie are both absent (conventions 1-2) -- never a pass by default."""
    sma_value = float(bars[sma_col].iat[pos])
    if not np.isfinite(close) or not np.isfinite(sma_value):
        return False
    return close > sma_value if bullish else close < sma_value


def _confluence_score(
    bars: pd.DataFrame, anchor_pos: int, direction: Direction, htf: HtfAlignment | None
) -> ConfluenceScore:
    """Read at `anchor_pos` -- D-32 -- never at the fill bar. §7.1.1 (`DIR_50`/`DIR_200`) and
    §7.5.5/D-27 (`HTF_STEP_3`, never a gate). Conventions 1-3 in the module docstring."""
    bullish = direction is Direction.BULLISH
    close = float(bars["close"].iat[anchor_pos])

    present: list[Confluence] = []
    if _sma_beyond(bars, "sma_50", anchor_pos, close, bullish=bullish):
        present.append(Confluence.DIR_50)
    if _sma_beyond(bars, "sma_200", anchor_pos, close, bullish=bullish):
        present.append(Confluence.DIR_200)
    if htf is not None and htf.is_aligned(bars.index[anchor_pos], direction):
        present.append(Confluence.HTF_STEP_3)

    return ConfluenceScore(present=tuple(present), score=len(present), of=len(Confluence))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalRecord:
    """`VISION.md` "What a signal actually is", plus the §5.3.10 engine note (store the trigger
    *and* the fill -- they differ on a gap, D-22, and only the fill sets R, §5.4.2)."""

    signal_id: str
    source: str
    instrument: str
    type_: SignalType
    setup_tf: str
    direction: Direction
    signal_ts: pd.Timestamp  # the fill bar's index
    anchor_ts: pd.Timestamp  # the D-32 read bar's index
    anchor_pos: int
    fill_pos: int
    trigger: float  # §5.3.10 engine note -- differs from fill on a gap
    fill: float  # D-22
    stop: float  # §5.4.1, D-10/D-18 -- the PTB's opposite extreme, no floor
    r: float  # §5.4.2 -- |fill - stop|, fixed once at fill, no floor (O-10: record, never gate)
    tp1: float | None  # §6.1, D-6 -- the Step 3 extreme frozen at fill (D-16, §3.5)
    tp2: float | None  # §6.2 -- always None in v1; anchors unpinned (O-7)
    setup_type: str  # "123_ptb" -- v1 emits exactly one setup
    continuation: bool  # §2.5, D-13/D-21
    confluence: ConfluenceScore
    gate: GateDecision  # always passed=True on an emitted signal


class EmissionEvent(StrEnum):
    SIGNAL = "signal"
    SUPPRESSED = "suppressed"  # a fill L4 gated away -- kept for Phase 6 divergence triage
    BREAK_EVEN = "break_even"  # §5.4.5, D-25 -- the event, never a second R


@dataclass(frozen=True)
class EmissionRecord:
    pos: int
    event: EmissionEvent
    direction: Direction
    signal: SignalRecord | None = None
    blocked_by: tuple[GateReason, ...] = ()
    signal_id: str | None = None


# ---------------------------------------------------------------------------
# The single-direction stepper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenSignal:
    """An emitted signal awaiting its break-even link (convention 4) -- just enough to match and
    report, not a copy of the whole `SignalRecord`."""

    signal_id: str
    fill: float


@dataclass(frozen=True)
class EmitterState:
    """A `SignalEmitter`'s current state, readable after every `step` call -- mirrors
    `stoic.entry.EntryState`."""

    continuation_open: bool = False  # True once this directional state's first candidate is seen
    open_signals: tuple[OpenSignal, ...] = ()  # emitted, not yet broken even; FIFO, convention 4


class SignalEmitter:
    """One direction's emission: candidate -> gate -> signal or suppression, plus break-even
    linking. One `SignalEmitter` per `Direction`, mirroring `EntryMachine` and `SequenceMachine`.
    """

    def __init__(
        self,
        direction: Direction,
        *,
        instrument: str,
        type_: SignalType,
        source: str = "stoic_123",
        htf: HtfAlignment | None = None,
    ) -> None:
        self.direction = direction
        self.instrument = instrument
        self.type_ = type_
        self.source = source
        self.htf = htf
        self._state = EmitterState()

    @property
    def state(self) -> EmitterState:
        return self._state

    def step(
        self,
        bars: pd.DataFrame,
        pos: int,
        *,
        entry_records: list[EntryRecord],
        sequence_events: list[EventRecord],
    ) -> list[EmissionRecord]:
        """Advance this direction's state by exactly one bar.

        `entry_records` -- this bar's L3 `EntryRecord`s for this direction (rows for the other
        direction are ignored defensively, the same convention `EntryMachine.step` uses).
        `sequence_events` -- this bar's L2 `EventRecord`s for this direction; consumed only for
        `Event.RESET` (convention 6).

        Processed in the order given (convention 7): `entry_records` first, then the `RESET`
        scan -- so a fill landing on the same bar as a `RESET` is attributed to the directional
        state the reset is closing, not the one it opens.
        """
        own_entries = [r for r in entry_records if r.direction == self.direction]
        own_reset = any(
            e.direction == self.direction and e.event == Event.RESET for e in sequence_events
        )

        state = self._state
        records: list[EmissionRecord] = []

        for rec in own_entries:
            if rec.event == EntryEvent.ENTRY_FILLED:
                state, emitted = self._on_fill(bars, pos, state, rec)
                records.extend(emitted)
            elif rec.event == EntryEvent.STOP_TO_BREAK_EVEN:
                state, emitted = self._on_break_even(pos, state, rec)
                records.extend(emitted)
            # PTB_ANCHORED / ORDER_CANCELLED: L3's bookkeeping -- nothing to emit.

        if own_reset:
            state = replace(state, continuation_open=False)  # convention 6

        self._state = state
        return records

    def _on_fill(
        self, bars: pd.DataFrame, pos: int, state: EmitterState, rec: EntryRecord
    ) -> tuple[EmitterState, list[EmissionRecord]]:
        if rec.anchor_pos is None:
            raise ValueError(
                "ENTRY_FILLED record has no anchor_pos -- D-32 requires the PTB anchor bar"
            )
        anchor_pos = rec.anchor_pos
        fast_chart = TYPE_SPECS[self.type_].fast_chart
        decision = gate(bars, anchor_pos, self.direction, fast_chart=fast_chart)

        continuation = state.continuation_open
        state = replace(state, continuation_open=True)  # convention 6: every candidate counts

        if not decision.passed:
            record = EmissionRecord(
                pos, EmissionEvent.SUPPRESSED, self.direction, blocked_by=decision.blocked_by
            )
            return state, [record]

        confluence = _confluence_score(bars, anchor_pos, self.direction, self.htf)
        signal_ts = bars.index[pos]
        signal_id = (
            f"{self.source}:{self.instrument}:{self.type_}:{self.direction}:"
            f"{signal_ts.isoformat()}"
        )
        signal = SignalRecord(
            signal_id=signal_id,
            source=self.source,
            instrument=self.instrument,
            type_=self.type_,
            setup_tf=TYPE_SPECS[self.type_].setup_tf,
            direction=self.direction,
            signal_ts=signal_ts,
            anchor_ts=bars.index[anchor_pos],
            anchor_pos=anchor_pos,
            fill_pos=pos,
            trigger=rec.trigger,
            fill=rec.fill,
            stop=rec.stop,
            r=abs(rec.fill - rec.stop),  # §5.4.2, no floor (O-10), no rounding
            tp1=rec.step3_extreme,  # already frozen by L3 -- D-16, §3.5, not re-derived
            tp2=None,  # O-7 -- anchors unpinned
            setup_type="123_ptb",
            continuation=continuation,
            confluence=confluence,
            gate=decision,
        )
        state = replace(
            state, open_signals=(*state.open_signals, OpenSignal(signal_id, rec.fill))
        )
        record = EmissionRecord(
            pos, EmissionEvent.SIGNAL, self.direction, signal=signal, signal_id=signal_id
        )
        return state, [record]

    def _on_break_even(
        self, pos: int, state: EmitterState, rec: EntryRecord
    ) -> tuple[EmitterState, list[EmissionRecord]]:
        """Convention 4: link by fill price, earliest match wins. No match (a suppressed
        candidate's break-even, which L3 still emits since it does not know about gating) means
        nothing is emitted."""
        match = next(
            (i for i, o in enumerate(state.open_signals) if o.fill == rec.fill), None
        )
        if match is None:
            return state, []
        matched = state.open_signals[match]
        remaining = (*state.open_signals[:match], *state.open_signals[match + 1 :])
        state = replace(state, open_signals=remaining)
        record = EmissionRecord(
            pos, EmissionEvent.BREAK_EVEN, self.direction, signal_id=matched.signal_id
        )
        return state, [record]


# ---------------------------------------------------------------------------
# The replay entry point
# ---------------------------------------------------------------------------

_PAYLOAD_COLUMNS = (
    "pos", "ts", "event", "direction", "blocked_by", "signal_id",
    "source", "instrument", "type_", "setup_tf",
    "signal_ts", "anchor_ts", "anchor_pos", "fill_pos",
    "trigger", "fill", "stop", "r", "tp1", "tp2",
    "setup_type", "continuation",
    "confluence_present", "confluence_score", "confluence_of",
)


def _flatten(bars: pd.DataFrame, rec: EmissionRecord) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(_PAYLOAD_COLUMNS)
    row.update(
        pos=rec.pos,
        ts=bars.index[rec.pos],
        event=rec.event,
        direction=rec.direction,
        blocked_by=rec.blocked_by,
        signal_id=rec.signal_id,
    )
    s = rec.signal
    if s is not None:
        row.update(
            source=s.source,
            instrument=s.instrument,
            type_=s.type_,
            setup_tf=s.setup_tf,
            signal_ts=s.signal_ts,
            anchor_ts=s.anchor_ts,
            anchor_pos=s.anchor_pos,
            fill_pos=s.fill_pos,
            trigger=s.trigger,
            fill=s.fill,
            stop=s.stop,
            r=s.r,
            tp1=s.tp1,
            tp2=s.tp2,
            setup_type=s.setup_type,
            continuation=s.continuation,
            confluence_present=s.confluence.present,
            confluence_score=s.confluence.score,
            confluence_of=s.confluence.of,
        )
    return row


def replay_signals(
    bars: pd.DataFrame,
    judgment: Judgment,
    *,
    instrument: str,
    type_: SignalType,
    source: str = "stoic_123",
    htf: HtfAlignment | None = None,
) -> pd.DataFrame:
    """Run both directions' `SignalEmitter`s over `bars`, one row per emitted `EmissionRecord`.

    Thin flattening layer over `stoic.entry.iter_replay_steps` -- the model is `replay_entries`.
    Does not reimplement the bar loop and does not modify `stoic.entry`.

    Requires `stoic.indicators.add_smas(bars)` and `stoic.judgment.attach_parent_pos(bars)` to
    have already been called; this function adds no validation of its own and lets `stoic.entry`,
    `stoic.sequence` and `stoic.gating` raise their own errors (`docs/CONSTRAINTS.md`).
    """
    emitter_bull = SignalEmitter(
        Direction.BULLISH, instrument=instrument, type_=type_, source=source, htf=htf
    )
    emitter_bear = SignalEmitter(
        Direction.BEARISH, instrument=instrument, type_=type_, source=source, htf=htf
    )

    rows: list[dict[str, object]] = []
    step: BarStep
    for step in iter_replay_steps(bars, judgment):
        for emitter, entry_records, sequence_events in (
            (emitter_bull, step.bull_entry_records, step.bull_sequence_events),
            (emitter_bear, step.bear_entry_records, step.bear_sequence_events),
        ):
            for emitted in emitter.step(
                bars, step.pos, entry_records=entry_records, sequence_events=sequence_events
            ):
                rows.append(_flatten(bars, emitted))

    data: dict[str, list] = {c: [row[c] for row in rows] for c in _PAYLOAD_COLUMNS}

    # Same schema whether `rows` is empty or not (replay_entries' F8 discipline): positional
    # indices are nullable Int64, prices float64, ts columns bars.index.dtype, enums/objects
    # object -- never a float64 an all-None/mixed column silently becomes.
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=bars.index.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "blocked_by": pd.Series(data["blocked_by"], dtype="object"),
            "signal_id": pd.Series(data["signal_id"], dtype="object"),
            "source": pd.Series(data["source"], dtype="object"),
            "instrument": pd.Series(data["instrument"], dtype="object"),
            "type_": pd.Series(data["type_"], dtype="object"),
            "setup_tf": pd.Series(data["setup_tf"], dtype="object"),
            "signal_ts": pd.Series(data["signal_ts"], dtype=bars.index.dtype),
            "anchor_ts": pd.Series(data["anchor_ts"], dtype=bars.index.dtype),
            "anchor_pos": pd.Series(data["anchor_pos"], dtype="Int64"),
            "fill_pos": pd.Series(data["fill_pos"], dtype="Int64"),
            "trigger": pd.Series(data["trigger"], dtype="float64"),
            "fill": pd.Series(data["fill"], dtype="float64"),
            "stop": pd.Series(data["stop"], dtype="float64"),
            "r": pd.Series(data["r"], dtype="float64"),
            "tp1": pd.Series(data["tp1"], dtype="float64"),
            "tp2": pd.Series(data["tp2"], dtype="float64"),
            "setup_type": pd.Series(data["setup_type"], dtype="object"),
            "continuation": pd.Series(data["continuation"], dtype="boolean"),
            "confluence_present": pd.Series(data["confluence_present"], dtype="object"),
            "confluence_score": pd.Series(data["confluence_score"], dtype="Int64"),
            "confluence_of": pd.Series(data["confluence_of"], dtype="Int64"),
        }
    )


__all__ = [
    "TYPE_SPECS",
    "Confluence",
    "ConfluenceScore",
    "EmissionEvent",
    "EmissionRecord",
    "EmitterState",
    "HtfAlignment",
    "OpenSignal",
    "SignalEmitter",
    "SignalRecord",
    "SignalType",
    "TypeSpec",
    "replay_signals",
]
