"""Phase 6 -- fidelity measurement. Pairs Phase 3's labels to the Phase 5 engine's output.

Design: `docs/PHASE6.md`. The question is `CLAUDE.md`'s and only `CLAUDE.md`'s -- does our
implementation generate the trades the method calls for. Never whether the method has an edge.

**This module is measurement, not signal.** `VISION.md` puts the deterministic signal path in
`stoic/`; a measurement module living beside it must never be reachable from it. Task 6 of
`docs/PHASE6-PLAN.md` will add a test to `tests/test_fidelity.py` that asserts the direction of
dependence by parsing every other `stoic/*.py`.

**It holds no threshold, fraction or tuned number**, and it must stay that way
(`docs/CONSTRAINTS.md` -- `stoic/judgment.py` is the only module allowed one). Matching is exact
bar equality (`docs/PHASE6.md` §4, the user's call on 2026-08-11), which needs no number: a
tolerance invented inside the measurement layer is the failure
`claude_memories/audit-hard-rules-not-in-material.md` names, and `docs/PHASE3.md` forbids one by
name.

Conventions fixed here rather than in `docs/PHASE6.md`:

1. **An absent value is unscoreable, never a pass.** A `phase6_scope` entry of `None`, or a field
   the artifact never printed, produces a `Delta` with `scoreable=False` and a stated reason. It
   never produces a zero delta.
2. **A stated value that disagrees with the field it names is a bug in the block, never a
   correction to the label.** `check_scope_consistency` reports it and the driver refuses to run.
3. **`stop.by_r_label` is never a reference.** `docs/CONSTRAINTS.md`: the dollar recovery is a
   suggestion and a `by_r_label` distance may never contradict §5.4.1 / D-18. It is carried as an
   informational column and no delta is ever computed from it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# The keys of a `phase6_scope` block that name a comparable reference, and which attributes of
# each are checked against the field `from:` points at. This list is not the full set of keys a
# real block may carry -- see DECLARATION_KEYS below for the rest, and note that each sub-block
# named here (e.g. `scope["anchor_bar"]`) may also carry a `provenance` key of its own (`read`,
# `derived` or `exact`); that key is metadata about the transcription, not a comparable attribute,
# so it never appears in COMPARED_ATTRS and is never checked.
#
# `anchor_bar_narrated` is deliberately NOT a member of this tuple even though it names a
# reference (`from: bar_5m_et`): that field holds a wall-clock string like `'13:25'`, while the
# block holds a full UTC timestamp, so the two are not comparable by equality -- checking it here
# would report a false problem. It is validated only as a known key, in DECLARATION_KEYS.
SCOPE_KEYS: tuple[str, ...] = ("anchor_bar", "entry_bar", "trigger", "stop", "tp1")

COMPARED_ATTRS: dict[str, tuple[str, ...]] = {
    "anchor_bar": ("ts",),
    "entry_bar": ("ts",),
    "trigger": ("price",),
    "stop": ("price", "distance"),  # the label stores both together under one node
    "tp1": ("price",),
}

# The keys of a `phase6_scope` block that are declarations rather than references: nothing in
# COMPARED_ATTRS checks them, so a misspelling of one of these must still be caught as an unknown
# key rather than silently ignored.
DECLARATION_KEYS: frozenset[str] = frozenset(
    {
        "expect_fill",  # whether the engine is expected to fill this order at all
        "circular",  # whether this block was derived from the engine's own output (excluded)
        "never",  # field names that must never be used as a scoring reference
        "why",  # free-text rationale for the block's scoreable/unscoreable choices
        "anchor_bar_narrated",  # narrated-bar anchor for no_opportunity labels; see note above
    }
)


# Sentinel distinguishing "the path is absent" from "the path resolves to a value of None" --
# both look like `None` to a caller of `resolve_path`, but the gate below must tell them apart
# (a scope block correctly pointing at a legitimately-null label field is not dangling).
_MISSING = object()


def _resolve_path(node: object, path: str) -> object:
    """Dotted-path lookup into a parsed label. Returns `_MISSING` if any segment is absent or not
    a mapping, distinct from a resolved value that is genuinely `None`. Internal: callers that
    don't need the distinction should use `resolve_path`.
    """
    current = node
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def resolve_path(node: object, path: str) -> object | None:
    """Dotted-path lookup into a parsed label. `None` if any segment is absent or not a mapping.

    Deliberately total: a dangling path is a reportable problem, not an exception, because the
    driver reports every problem in one pass rather than dying on the first.
    """
    result = _resolve_path(node, path)
    return None if result is _MISSING else result


def _same(stated: object, actual: object) -> bool:
    """Exact equality, with timestamps normalised. No tolerance -- a transcribed value is copied,
    so anything but equality is a transcription error."""
    if stated is None or actual is None:
        return stated is None and actual is None
    if hasattr(actual, "tzinfo") or isinstance(actual, pd.Timestamp):
        try:
            return pd.Timestamp(stated) == pd.Timestamp(actual)
        except (ValueError, TypeError):
            # An unparseable `stated` (e.g. a placeholder string like "TBD") is a reportable
            # mismatch, not a crash -- the driver must still see every other label's problems.
            return False
    return bool(stated == actual)


def check_scope_consistency(label: dict) -> tuple[str, ...]:
    """Every problem with one label's `phase6_scope` block, as human-readable lines.

    Empty means the block agrees with every field it points at. This is the gate that makes the
    block safe: it adds no reading, so it must reproduce the readings it names exactly.
    """
    label_id = label.get("id", "<no id>")
    scope = label.get("phase6_scope")
    if scope is None:
        return (f"{label_id}: no phase6_scope block",)
    if not isinstance(scope, dict):
        # A half-transcribed label can leave the whole block as a scalar (`TBD`) or a list --
        # both look nothing like the mapping every check below assumes. Report it as a problem
        # instead of letting `.get`/hashing raise and kill the whole run on this one label.
        return (f"{label_id}: phase6_scope is not a mapping (got {type(scope).__name__})",)

    problems: list[str] = []
    known_keys = set(SCOPE_KEYS) | DECLARATION_KEYS
    for key in scope:
        if key not in known_keys:
            problems.append(f"{label_id}: unknown phase6_scope key '{key}'")

    for key in SCOPE_KEYS:
        block = scope.get(key)
        if block is None:
            continue
        if not isinstance(block, dict):
            # Same half-transcription failure, one level down: `trigger: TBD` in place of a
            # sub-block mapping.
            problems.append(
                f"{label_id}.{key}: phase6_scope.{key} is not a mapping "
                f"(got {type(block).__name__})"
            )
            continue
        # A sub-block may only carry its own compared attributes plus `from` and `provenance`;
        # anything else is a misspelling (e.g. `provenence`) that would otherwise go unchecked.
        recognised = set(COMPARED_ATTRS[key]) | {"from", "provenance"}
        for sub_key in block:
            if sub_key not in recognised:
                problems.append(
                    f"{label_id}.{key}: unknown key '{sub_key}' in phase6_scope.{key}"
                )
        source = block.get("from")
        if source is None:
            problems.append(f"{label_id}.{key}: no from: path")
            continue
        node = _resolve_path(label, source)
        if node is _MISSING:
            problems.append(f"{label_id}.{key}: from: '{source}' resolves to nothing")
            continue
        for attr in COMPARED_ATTRS[key]:
            stated = block.get(attr)
            if isinstance(node, dict):
                if attr not in block and attr not in node:
                    # Neither side names the compared attribute -- a consistently misspelled key
                    # (e.g. `prise` for `price`) makes both `.get` calls return `None`, which
                    # would otherwise compare equal and pass vacuously.
                    problems.append(
                        f"{label_id}.{key}.{attr}: neither the block nor '{source}' "
                        f"state a value for '{attr}'"
                    )
                    continue
                actual = node.get(attr)
            else:
                actual = node
            if not _same(stated, actual):
                problems.append(
                    f"{label_id}.{key}.{attr}: block says {stated!r}, "
                    f"'{source}' says {actual!r}"
                )
    return tuple(problems)


# The four comparable quantities on a matched `taken` label, and where each side comes from.
# `stop_distance` compares the engine's `r` -- |fill - stop|, §5.4.2 -- against the label's own
# stop distance in points. The label's `r_label` is an OUTCOME MULTIPLE and is never compared to
# it: they are different quantities (docs/PHASE6.md §1).
_TAKEN_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    # (delta field, scope key, scope attr, engine column)
    ("trigger", "trigger", "price", "trigger"),
    ("stop", "stop", "price", "stop"),
    ("stop_distance", "stop", "distance", "r"),
    ("tp1", "tp1", "price", "tp1"),
)

_TERMINAL_EVENTS: frozenset[str] = frozenset(
    {"ENTRY_FILLED", "ORDER_CANCELLED", "ORDER_VOIDED"}
)


@dataclass(frozen=True)
class Delta:
    """One comparable quantity. `delta` is engine minus label, in points."""

    field: str
    label: float | None
    engine: float | None
    delta: float | None
    scoreable: bool
    reason: str = ""


@dataclass(frozen=True)
class LabelResult:
    """One label's reconciliation. Carries no verdict -- only what was and was not found."""

    label_id: str
    session: str
    label_class: str
    direction: str
    matched: bool
    engine_event: str | None
    engine_ts: pd.Timestamp | None
    blocked_by: tuple[str, ...]
    anchor_matched: bool | None
    deltas: tuple[Delta, ...]
    nearest_ts: pd.Timestamp | None
    nearest_delta_bars: int | None
    circular: bool
    notes: tuple[str, ...]


def bar_offset(
    bar_index: pd.DatetimeIndex, a: pd.Timestamp | None, b: pd.Timestamp | None
) -> int | None:
    """Signed distance from `b` to `a` in bars of the replay frame. `None` if either is off it.

    Bars, not minutes: the frame holds no bars across the CME maintenance break, so a wall-clock
    difference is not a bar count (`docs/CONSTRAINTS.md` -- the row about blaming that break).
    """
    if a is None or b is None:
        return None
    try:
        return int(bar_index.get_loc(pd.Timestamp(a))) - int(bar_index.get_loc(pd.Timestamp(b)))
    except KeyError:
        return None


def _nearest(
    bar_index: pd.DatetimeIndex, timestamps: pd.Series, expected: pd.Timestamp
) -> tuple[pd.Timestamp | None, int | None]:
    """The nearest of `timestamps` to `expected`, in bars, and its signed offset.

    Shared by `reconcile_taken`, `reconcile_named` and `reconcile_no_opportunity`'s unmatched
    branches -- an unmatched label is characterised by its nearest same-direction candidate and
    the signed bar offset to it, and that rule must not drift between the three copies. Ties break
    toward the earlier bar (`min` over `(abs(offset), offset)`). `(None, None)` if `timestamps` is
    empty or every entry falls off `bar_index` (`bar_offset` returns `None` there).
    """
    offsets = [
        (offset, ts)
        for ts in timestamps
        if (offset := bar_offset(bar_index, ts, expected)) is not None
    ]
    if not offsets:
        return None, None
    nearest_bars, nearest_ts = min(offsets, key=lambda pair: (abs(pair[0]), pair[0]))
    return nearest_ts, nearest_bars


def _unscoreable(field: str, reason: str, label_value: float | None = None) -> Delta:
    return Delta(
        field=field, label=label_value, engine=None, delta=None, scoreable=False, reason=reason
    )


def _finite(value: object) -> float | None:
    """A float, or None for None / NaN / pandas NA. Guards against pandas' nullable columns."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    if value is pd.NA:
        return None
    return float(value)  # type: ignore[arg-type]


def _l3_prices(
    entries: pd.DataFrame, ts: pd.Timestamp, direction: str, bar_index: pd.DatetimeIndex
) -> dict[str, object]:
    """L3's `ENTRY_FILLED` record at this bar, or an empty dict.

    A `SUPPRESSED` emission carries no `SignalRecord`, so every price on it is null
    (`stoic/emission.py`). The prices exist one layer down and this recovers them, which is why
    the driver runs both replays (`docs/PHASE6.md` §3).

    L3's real frame has no `anchor_ts` column (`stoic/entry.py:471` `_PAYLOAD_COLUMNS`) -- the
    anchor is stored as `anchor_pos`, a nullable Int64 *position* into the replay bar index, not a
    timestamp -- so this translates position to timestamp via `bar_index` before handing the
    anchor onward. An absent or out-of-range position reports as `None`, the same "never raise"
    discipline `bar_offset` applies to a `KeyError` from `get_loc`.

    A position lookup has no `KeyError` to fail on, unlike `bar_offset`'s `get_loc` -- a
    `bar_index` sliced differently from the frame L3's positions were recorded against would
    usually still satisfy `0 <= pos < len(bar_index)` and silently resolve to the WRONG bar, which
    is a fabricated divergence, not a caught error. The row carries the means to detect this
    itself: `row["pos"]` is this same record's own position in that frame, so
    `bar_index[row["pos"]] == row["ts"]` must hold if `bar_index` is in fact the frame the
    position was recorded against. A mismatch means the caller passed the wrong index -- reported
    as no recovery (`{}`), never a translated-but-wrong timestamp.
    """
    hit = entries[
        (entries["ts"] == ts)
        & (entries["direction"].astype(str) == direction)
        & (entries["event"].astype(str) == "ENTRY_FILLED")
    ]
    if hit.empty:
        return {}
    row = hit.iloc[0]
    own_pos = row["pos"]
    if pd.notna(own_pos):
        pos = int(own_pos)
        if not (0 <= pos < len(bar_index)) or bar_index[pos] != row["ts"]:
            return {}
    anchor_pos = row["anchor_pos"]
    anchor_ts: pd.Timestamp | None = None
    if pd.notna(anchor_pos):
        pos = int(anchor_pos)
        if 0 <= pos < len(bar_index):
            anchor_ts = bar_index[pos]
    return {
        "anchor_ts": anchor_ts,
        "trigger": row["trigger"],
        "stop": row["stop"],
        "fill": row["fill"],
        # Mirrors stoic/emission.py's own `r=abs(rec.fill - rec.stop)` (§5.4.2 -- no floor: D-18
        # on the stop, O-10 on gating R) operand for operand -- `_finite` is identity on a float,
        # so this is the identical arithmetic the engine would have run for the same trade,
        # including its float behaviour. A `SUPPRESSED` row is measured by the identical
        # arithmetic as a `SIGNAL` row, so real data carries the same ~1e-12 residual against a
        # label's 2-dp literal on both paths. That residual is arithmetic, not a divergence, and
        # Tasks 4/8 must not read it as one -- do not "fix" it with Decimal here or anywhere else.
        "r": (
            abs(_finite(row["fill"]) - _finite(row["stop"]))
            if _finite(row["fill"]) is not None and _finite(row["stop"]) is not None
            else None
        ),
        "tp1": row["step3_extreme"],
    }


def reconcile_taken(
    label: dict,
    session: str,
    emissions: pd.DataFrame,
    entries: pd.DataFrame,
    bar_index: pd.DatetimeIndex,
) -> LabelResult:
    """Pair one `taken` label to an emission on the SAME BAR, exactly (`docs/PHASE6.md` §4).

    `emissions` and `entries` are already sliced to this label's session; both directions may be
    present and this filters. An unmatched label is characterised by its nearest same-direction
    emission and the signed bar offset to it -- a miss by one bar and a miss by forty are
    different facts and §2 of the report cannot be written without knowing which.

    `bar_index` must be the SAME, UNSLICED replay frame index that `entries`' `pos`/`anchor_pos`
    positions were recorded against (`stoic/entry.py:471`) -- L3 stores positions, not
    timestamps, and `_l3_prices` translates them positionally. A differently-sliced index would
    usually still resolve to a bar, just the wrong one, silently. `_l3_prices` checks each row's
    own `pos` against `bar_index` and refuses to translate on a mismatch, but the caller (Task 7's
    driver) must still pass the real frame, not a per-session slice of it.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    circular = bool(scope.get("circular", False))

    candidates = emissions[
        (emissions["direction"].astype(str) == engine_direction)
        & (emissions["event"].astype(str).isin(["SIGNAL", "SUPPRESSED"]))
    ]

    entry_bar = scope.get("entry_bar")
    if entry_bar is None:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=None,
            deltas=tuple(
                _unscoreable(f, "phase6_scope.entry_bar is null") for f, _, _, _ in _TAKEN_FIELDS
            ),
            nearest_ts=None, nearest_delta_bars=None, circular=circular,
            notes=("no entry bar in scope -- nothing to pair on",),
        )

    expected = pd.Timestamp(entry_bar["ts"])
    hit = candidates[candidates["ts"] == expected]

    if hit.empty:
        nearest_ts, nearest_bars = _nearest(bar_index, candidates["ts"], expected)
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            # No anchor comparison ran here -- there is no matched emission to compare an
            # anchor_ts against. `None` means "not compared", `False` means "compared and
            # differed"; only the second belongs to a real comparison, like the two sibling
            # returns above (entry_bar is None) and below (matched, block absent).
            blocked_by=(), anchor_matched=None,
            deltas=tuple(
                _unscoreable(f, "no emission on the label's bar") for f, _, _, _ in _TAKEN_FIELDS
            ),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=circular,
            notes=(),
        )

    row = hit.iloc[0]
    event = str(row["event"])
    notes: list[str] = []
    if len(hit) > 1:
        notes.append(f"{len(hit)} same-direction emissions on this bar; the first is compared")

    engine: dict[str, object] = {
        "anchor_ts": row["anchor_ts"], "trigger": row["trigger"], "stop": row["stop"],
        "r": row["r"], "tp1": row["tp1"],
    }
    if event == "SUPPRESSED":
        borrowed = _l3_prices(entries, expected, engine_direction, bar_index)
        if borrowed:
            engine = borrowed
            notes.append("prices recovered from L3's ENTRY_FILLED -- a SUPPRESSED row carries none")
        else:
            notes.append("SUPPRESSED with no L3 ENTRY_FILLED on the same bar -- prices unavailable")

    deltas: list[Delta] = []
    for field_name, scope_key, scope_attr, column in _TAKEN_FIELDS:
        block = scope.get(scope_key)
        if block is None:
            deltas.append(_unscoreable(field_name, f"phase6_scope.{scope_key} is null"))
            continue
        label_value = _finite(block.get(scope_attr))
        engine_value = _finite(engine.get(column))
        if label_value is None:
            deltas.append(
                _unscoreable(field_name, f"phase6_scope.{scope_key}.{scope_attr} is null")
            )
        elif engine_value is None:
            deltas.append(
                Delta(field_name, label_value, None, None, False, "the engine emitted no value")
            )
        else:
            deltas.append(
                Delta(field_name, label_value, engine_value, engine_value - label_value, True)
            )

    anchor_block = scope.get("anchor_bar")
    anchor_matched: bool | None = None
    if anchor_block is not None:
        engine_anchor = engine.get("anchor_ts")
        # Same convention as the no-emission return above: `None` means "not compared" (the
        # engine emitted no anchor_ts to compare against -- e.g. a SUPPRESSED row with nothing
        # borrowed from L3), `False` means "compared and differed". Collapsing the first into the
        # second would turn "no value" into a false mismatch on the one field where deltas already
        # get this right (Delta.reason == "the engine emitted no value").
        #
        # `pd.isna`, not `is None`: the real emissions frame stores `anchor_ts` as a tz-aware
        # datetime64 column (`stoic/emission.py:517`), and pandas coerces a null in that dtype to
        # `NaT`, not the bare Python `None` a hand-built dict would carry -- `pd.NaT is None` is
        # `False`, so `is None` alone lets a real SUPPRESSED row's missing anchor fall through to
        # `pd.Timestamp(pd.NaT) == ...`, which is `False`: "compared and differed" for the exact
        # case this comment exists to name as "not compared". Same discipline `_finite` already
        # applies to the price columns.
        anchor_matched = (
            None
            if pd.isna(engine_anchor)
            else pd.Timestamp(engine_anchor) == pd.Timestamp(anchor_block["ts"])
        )

    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event=event, engine_ts=expected,
        blocked_by=tuple(str(r) for r in (row["blocked_by"] or ())),
        anchor_matched=anchor_matched, deltas=tuple(deltas),
        nearest_ts=None, nearest_delta_bars=None, circular=circular, notes=tuple(notes),
    )


def _direction_rows(entries: pd.DataFrame, engine_direction: str) -> pd.DataFrame:
    return entries[entries["direction"].astype(str) == engine_direction].sort_values(
        "ts", kind="stable"
    )


def reconcile_named(
    label: dict, session: str, entries: pd.DataFrame, bar_index: pd.DatetimeIndex
) -> LabelResult:
    """Pair a `named` label to L3's `PTB_ANCHORED` on the same bar (`docs/PHASE6.md` §4).

    The trader declined this setup, so there is nothing to score but whether the engine SAW it.
    An engine fill here is **correct-but-not-taken, never a false positive** (`docs/PHASE3.md`
    §2) and is recorded as a note, not as a divergence.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    rows = _direction_rows(entries, engine_direction)
    anchors = rows[rows["event"].astype(str) == "PTB_ANCHORED"]

    anchor_block = scope.get("anchor_bar")
    if anchor_block is None:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=None,
            deltas=(_unscoreable("trigger", "phase6_scope.anchor_bar is null"),),
            nearest_ts=None, nearest_delta_bars=None, circular=False,
            notes=("no anchor bar in scope -- nothing to pair on",),
        )

    expected = pd.Timestamp(anchor_block["ts"])
    hit = anchors[anchors["ts"] == expected]

    if hit.empty:
        nearest_ts, nearest_bars = _nearest(bar_index, anchors["ts"], expected)
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            # Same convention as reconcile_taken's no-match branch: there is no engine anchor on
            # this bar to compare against, so no comparison ran -- `None`, not `False`
            # (`anchor_matched`'s three-way convention: True/False only apply once a comparison
            # actually happened).
            blocked_by=(), anchor_matched=None,
            deltas=(_unscoreable("trigger", "the engine anchored no order on this bar"),),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=False,
            notes=("the engine never saw this setup on the label's bar",),
        )

    row = hit.iloc[0]
    notes: list[str] = []
    later = rows[rows["ts"] > expected]
    terminal = later[later["event"].astype(str).isin(_TERMINAL_EVENTS)]
    if not terminal.empty and str(terminal.iloc[0]["event"]) == "ENTRY_FILLED":
        notes.append(
            "the engine filled this order -- correct-but-not-taken, never a false positive "
            "(docs/PHASE3.md §2)"
        )

    trigger_block = scope.get("trigger")
    if trigger_block is None:
        delta = _unscoreable("trigger", "phase6_scope.trigger is null")
    else:
        label_value = _finite(trigger_block.get("price"))
        engine_value = _finite(row["trigger"])
        delta = (
            Delta("trigger", label_value, engine_value, engine_value - label_value, True)
            if label_value is not None and engine_value is not None
            else _unscoreable("trigger", "no trigger on one side", label_value)
        )

    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event="PTB_ANCHORED", engine_ts=expected,
        blocked_by=(), anchor_matched=True, deltas=(delta,),
        nearest_ts=None, nearest_delta_bars=None, circular=False, notes=tuple(notes),
    )


def reconcile_no_opportunity(
    label: dict, session: str, entries: pd.DataFrame, bar_index: pd.DatetimeIndex
) -> LabelResult:
    """Score a `no_opportunity` label over the working order's OWN LIFETIME.

    The label says the bars never traded through the trigger, so the engine is required to emit
    no fill (`docs/PHASE3.md` §2; the label's own `phase_6_expectation`). This is the one class
    where absence is the right answer and the bars can settle it -- and it needs **no window**:
    the interval is the order's life, from its anchor to the first terminal event
    (`ENTRY_FILLED` / `ORDER_CANCELLED` / `ORDER_VOIDED`, §5.3.4a's closed list of three).
    A terminal event of `ENTRY_FILLED` is the divergence.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    rows = _direction_rows(entries, engine_direction)

    # `anchor_bar` first, `anchor_bar_narrated` as this class's declared fallback (see the comment
    # above `SCOPE_KEYS` on why the narrated field is never a comparison reference elsewhere --
    # here it is only ever used as a bar to pair on, never compared by equality).
    anchor_block = scope.get("anchor_bar") or scope.get("anchor_bar_narrated")
    if not isinstance(anchor_block, dict):
        # Mirrors reconcile_named's identical branch: a label that names no anchor bar at all was
        # never paired, and reporting anything else here would blame the engine for a gap that is
        # the label's, not the engine's (review finding 2) -- three distinct states (label silent /
        # engine anchored elsewhere / engine never anchored) must not collapse into one accusation.
        #
        # Widened past `is None`: `anchor_bar` is checked as a mapping by check_scope_consistency's
        # SCOPE_KEYS gate before this ever runs, but `anchor_bar_narrated` is deliberately excluded
        # from that check (its `from: bar_5m_et` field is a wall-clock string, not comparable by
        # equality -- see the comment above `SCOPE_KEYS`) and validated only as a known key. A
        # half-transcribed `anchor_bar_narrated: TBD` is therefore a truthy non-mapping that would
        # otherwise pass this `is None` guard and raise `TypeError` on `anchor_block["ts"]` below --
        # report it instead, never subscript it, per the report-never-raise discipline
        # `check_scope_consistency` already states for itself.
        reason = (
            "no anchor bar in scope -- nothing to pair on"
            if anchor_block is None
            else "phase6_scope.anchor_bar_narrated is not a mapping -- nothing to pair on"
        )
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=None, deltas=(),
            nearest_ts=None, nearest_delta_bars=None, circular=False,
            notes=(reason,),
        )

    expected = pd.Timestamp(anchor_block["ts"])
    anchors = rows[rows["event"].astype(str) == "PTB_ANCHORED"]
    hit = anchors[anchors["ts"] == expected]

    if hit.empty:
        nearest_ts, nearest_bars = _nearest(bar_index, anchors["ts"], expected)
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            # Same convention as reconcile_named above and reconcile_taken's no-match branch: no
            # engine anchor exists on this bar to compare against, so no comparison ran.
            blocked_by=(), anchor_matched=None, deltas=(),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=False,
            notes=("the engine never anchored an order on this bar",),
        )

    later = rows[rows["ts"] > expected]
    terminal = later[later["event"].astype(str).isin(_TERMINAL_EVENTS)]
    if terminal.empty:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=True, engine_event=None, engine_ts=expected,
            blocked_by=(), anchor_matched=True, deltas=(),
            nearest_ts=None, nearest_delta_bars=None, circular=False,
            notes=("the order was still working at the end of the slice -- no fill",),
        )

    end = terminal.iloc[0]
    event = str(end["event"])
    if event == "ENTRY_FILLED":
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=event, engine_ts=end["ts"],
            blocked_by=(), anchor_matched=True, deltas=(),
            nearest_ts=end["ts"], nearest_delta_bars=bar_offset(bar_index, end["ts"], expected),
            circular=False,
            notes=(
                "DIVERGENCE: the engine filled an order the bars never traded through the "
                "trigger for",
            ),
        )
    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event=event, engine_ts=end["ts"],
        blocked_by=(), anchor_matched=True, deltas=(),
        nearest_ts=None, nearest_delta_bars=None, circular=False,
        notes=("engine emitted no fill -- the label's expectation",),
    )


__all__ = [
    "COMPARED_ATTRS",
    "DECLARATION_KEYS",
    "SCOPE_KEYS",
    "Delta",
    "LabelResult",
    "bar_offset",
    "check_scope_consistency",
    "reconcile_named",
    "reconcile_no_opportunity",
    "reconcile_taken",
    "resolve_path",
]
