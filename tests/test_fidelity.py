"""Unit tests for stoic.fidelity (Phase 6) -- hand-built fixtures only, no disk or network.

The pairing rule is the measurement instrument, so it is the part that must be tested. Every
check here gets a negative control per `coding_rules.md`: inject the fault it exists to catch and
confirm it is caught.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from stoic import fidelity as fidelity_module
from stoic.emission import EmissionEvent
from stoic.entry import EntryEvent
from stoic.fidelity import (
    Delta,
    LabelResult,
    bar_offset,
    check_scope_consistency,
    reconcile_named,
    reconcile_no_opportunity,
    reconcile_taken,
    render_report,
    resolve_path,
    unlabelled_emissions,
)


def _utc(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.UTC)


def _label() -> dict:
    """A `taken` label in the shape PyYAML produces from docs/evidence/labels/."""
    return {
        "id": "T-A2",
        "class": "taken",
        "direction": "short",
        "ptb": {
            "pos_ts": _utc(2026, 7, 31, 14, 50),
            "trigger": {"bars": 28289.75, "provenance": "read"},
        },
        "entry": {"price": 28286.67, "pos_ts": _utc(2026, 7, 31, 14, 55)},
        "stop": {
            "by_ptb_extreme": {"price": 28345.50, "distance": 58.83},
            "by_r_label": {"price": 28341.09, "distance": 54.42},
        },
        "tp1": None,
        "phase6_scope": {
            "anchor_bar": {"ts": _utc(2026, 7, 31, 14, 50), "from": "ptb.pos_ts"},
            "entry_bar": {"ts": _utc(2026, 7, 31, 14, 55), "from": "entry.pos_ts"},
            "trigger": {"price": 28289.75, "from": "ptb.trigger.bars"},
            "stop": {"price": 28345.50, "distance": 58.83, "from": "stop.by_ptb_extreme"},
            "tp1": None,
            "expect_fill": True,
            "circular": False,
            "never": ["exit", "outcome"],
            "anchor_bar_narrated": "13:25",
        },
    }


def test_resolve_path_reaches_a_nested_scalar():
    assert resolve_path(_label(), "ptb.trigger.bars") == 28289.75


def test_resolve_path_returns_none_for_an_absent_segment():
    assert resolve_path(_label(), "ptb.by_rule.trigger") is None


def test_resolve_path_returns_none_when_a_segment_is_not_a_mapping():
    assert resolve_path(_label(), "entry.price.nope") is None


def test_consistent_scope_reports_no_problems():
    assert check_scope_consistency(_label()) == ()


def test_negative_control_wrong_price_is_caught():
    label = _label()
    label["phase6_scope"]["trigger"]["price"] = 28290.00
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "trigger.price" in problems[0]


def test_negative_control_wrong_timestamp_is_caught():
    label = _label()
    label["phase6_scope"]["entry_bar"]["ts"] = _utc(2026, 7, 31, 15, 0)
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "entry_bar.ts" in problems[0]


def test_negative_control_distance_is_compared_too():
    label = _label()
    label["phase6_scope"]["stop"]["distance"] = 54.42  # the by_r_label distance
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "stop.distance" in problems[0]


def test_dangling_from_path_is_caught():
    label = _label()
    label["phase6_scope"]["trigger"]["from"] = "ptb.by_rule.trigger"
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "resolves to nothing" in problems[0]


def test_missing_scope_block_is_caught():
    label = _label()
    del label["phase6_scope"]
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "no phase6_scope" in problems[0]


def test_null_scope_entries_are_not_checked():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    assert check_scope_consistency(label) == ()


# --- Fix pass: six review findings -----------------------------------------------------------


def test_unparseable_timestamp_is_reported_not_raised():
    """Finding 1: a coercion failure (e.g. a placeholder like "TBD") must be a reported problem,
    not an exception that kills the whole run on the first bad label."""
    label = _label()
    label["phase6_scope"]["entry_bar"]["ts"] = "TBD"
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "entry_bar.ts" in problems[0]


def test_misspelled_scope_key_is_caught_even_with_a_bad_value_inside():
    """Finding 2: a block under a misspelled key (`enty_bar` for `entry_bar`) must be reported as
    an unknown key -- even though nothing in SCOPE_KEYS ever looks at it, so the wrong timestamp
    inside it would otherwise sail through unvalidated."""
    label = _label()
    block = label["phase6_scope"].pop("entry_bar")
    block["ts"] = _utc(2026, 7, 31, 15, 0)  # wrong; would go unchecked under the misspelled key
    label["phase6_scope"]["enty_bar"] = block
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "enty_bar" in problems[0]


def test_declaration_keys_are_not_reported_as_unknown():
    label = _label()
    label["phase6_scope"]["why"] = "scoreable: direction and entry bar."
    assert check_scope_consistency(label) == ()


def test_from_path_resolving_to_a_legitimate_null_is_not_dangling():
    """Finding 3: `resolve_path` returns `None` both when a path is absent and when it is present
    but genuinely null. A scope block pointing at a real, null-valued field must not be reported
    as dangling."""
    label = _label()
    label["tp1"] = None
    label["phase6_scope"]["tp1"] = {"price": None, "from": "tp1"}
    assert check_scope_consistency(label) == ()


def test_docstring_does_not_claim_the_import_direction_test_already_exists():
    """Finding 4: the module docstring must not assert, in the present tense, a test that Task 6
    has not written yet."""
    doc = fidelity_module.__doc__
    assert "Task 6" in doc
    assert "tests/test_fidelity.py` asserts the direction of dependence" not in doc


def test_anchor_bar_narrated_is_declared_but_never_a_scope_key():
    """Finding 5 (hardening pass): behaviour, not prose -- `anchor_bar_narrated` must be validated
    as a known top-level `phase6_scope` key (via DECLARATION_KEYS) but never treated as a
    comparable reference (SCOPE_KEYS), because its `from:` target is a wall-clock string, not
    comparable by equality to a UTC timestamp."""
    assert "anchor_bar_narrated" in fidelity_module.DECLARATION_KEYS
    assert "anchor_bar_narrated" not in fidelity_module.SCOPE_KEYS


def _label_with_tp1() -> dict:
    label = _label()
    label["tp1"] = {"price": 28297.75}
    label["phase6_scope"]["tp1"] = {"price": 28297.75, "from": "tp1"}
    return label


def test_negative_control_anchor_bar_wrong_timestamp_is_caught():
    """Finding 6: SCOPE_KEYS coverage -- deleting `anchor_bar` from SCOPE_KEYS must break this."""
    label = _label()
    label["phase6_scope"]["anchor_bar"]["ts"] = _utc(2026, 7, 31, 15, 0)
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "anchor_bar.ts" in problems[0]


def test_negative_control_tp1_wrong_price_is_caught():
    """Finding 6: SCOPE_KEYS coverage -- deleting `tp1` from SCOPE_KEYS must break this."""
    label = _label_with_tp1()
    label["phase6_scope"]["tp1"]["price"] = 0.0
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "tp1.price" in problems[0]


def test_missing_from_key_is_reported():
    label = _label()
    del label["phase6_scope"]["trigger"]["from"]
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "no from: path" in problems[0]


def test_three_simultaneous_faults_produce_three_problem_lines():
    """The driver reports every problem in one pass rather than dying on the first -- verify it
    for three independent, simultaneous faults in one block."""
    label = _label()
    label["phase6_scope"]["trigger"]["price"] = 0.0  # wrong price
    label["phase6_scope"]["entry_bar"]["ts"] = _utc(2026, 7, 31, 15, 0)  # wrong timestamp
    del label["phase6_scope"]["stop"]["from"]  # missing from: path
    problems = check_scope_consistency(label)
    assert len(problems) == 3


# --- Hardening pass: four more review findings ------------------------------------------------


def test_scalar_sub_block_is_reported_not_raised():
    """Finding 2: `phase6_scope: {trigger: TBD}` -- a scalar where a sub-block mapping is expected
    -- must be reported, not raise AttributeError from `block.get(...)`."""
    label = _label()
    label["phase6_scope"]["trigger"] = "TBD"
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "trigger" in problems[0]


def test_scalar_phase6_scope_block_is_reported_not_raised():
    """Finding 2: `phase6_scope: TBD` -- the whole block a scalar -- must be reported, not raise
    AttributeError from `scope.get(...)`."""
    label = _label()
    label["phase6_scope"] = "TBD"
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "phase6_scope" in problems[0]


def test_list_phase6_scope_block_is_reported_not_raised():
    """Finding 2: `phase6_scope: [...]` -- a list -- must be reported, not raise TypeError from
    hashing an unhashable dict element while checking membership."""
    label = _label()
    label["phase6_scope"] = [{"trigger": "x"}]
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "phase6_scope" in problems[0]


def test_unrecognised_key_inside_a_sub_block_is_reported():
    """Finding 3: an unknown key inside a phase6_scope sub-block -- a misspelling (`provenence`)
    or unrelated junk -- must be reported. The top-level unknown-key guard is blind to it because
    it only inspects the top level of the block."""
    label = _label()
    label["phase6_scope"]["trigger"]["provenence"] = "read"
    label["phase6_scope"]["trigger"]["junk"] = 1
    problems = check_scope_consistency(label)
    assert any("provenence" in p for p in problems)
    assert any("junk" in p for p in problems)


def test_attribute_absent_on_both_sides_is_reported():
    """Finding 3: the compared attribute simply missing from both the block and the referenced
    label node (no misspelling, no junk key) must still be reported -- a scope entry that
    compares nothing is a bug in the block, not a pass."""
    label = _label()
    label["tp1"] = {}
    label["phase6_scope"]["tp1"] = {"from": "tp1"}
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "price" in problems[0]


def test_consistently_misspelled_attribute_does_not_pass_vacuously():
    """Finding 3: the exact scenario from the review -- `tp1: {prise: 28628.0}` in the label,
    matched by a scope block that carries the same misspelling, must not compare `None` to `None`
    and pass. Both the unknown-key check and the absent-on-both-sides check should fire."""
    label = _label()
    label["tp1"] = {"prise": 28628.0}
    label["phase6_scope"]["tp1"] = {"prise": 28628.0, "from": "tp1"}
    problems = check_scope_consistency(label)
    assert problems  # not the vacuous ()
    assert any("price" in p for p in problems)


# --- Task 3: pairing and deltas for class `taken` ----------------------------------------------

BAR_INDEX = pd.date_range("2026-07-31 14:00", periods=24, freq="5min", tz="UTC")


def _emissions(rows: list[dict]) -> pd.DataFrame:
    """Mirrors `stoic/emission.py:504-531`'s `replay_signals` frame construction
    (`_PAYLOAD_COLUMNS`) completely -- same columns, same order, same dtypes -- not just the
    subset `reconcile_taken` reads today, so a Task 4/5 addition that reads a column outside that
    subset inherits a fixture that already carries the real dtype rather than re-litigating this
    defect class there. `ts`, `signal_ts` and `anchor_ts` are tz-aware datetime64
    (`bars.index.dtype` there), so a null anchor arrives as `NaT` here exactly as it does on a
    real SUPPRESSED row.
    """
    columns = [
        "pos", "ts", "event", "direction", "blocked_by", "signal_id", "source", "instrument",
        "type_", "setup_tf", "signal_ts", "anchor_ts", "anchor_pos", "fill_pos", "trigger",
        "fill", "stop", "r", "tp1", "tp2", "setup_type", "continuation", "confluence_present",
        "confluence_score", "confluence_of",
    ]
    data = {c: [row.get(c) for row in rows] for c in columns}
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=BAR_INDEX.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "blocked_by": pd.Series(data["blocked_by"], dtype="object"),
            "signal_id": pd.Series(data["signal_id"], dtype="object"),
            "source": pd.Series(data["source"], dtype="object"),
            "instrument": pd.Series(data["instrument"], dtype="object"),
            "type_": pd.Series(data["type_"], dtype="object"),
            "setup_tf": pd.Series(data["setup_tf"], dtype="object"),
            "signal_ts": pd.Series(data["signal_ts"], dtype=BAR_INDEX.dtype),
            "anchor_ts": pd.Series(data["anchor_ts"], dtype=BAR_INDEX.dtype),
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


def _entries(rows: list[dict]) -> pd.DataFrame:
    """Mirrors `stoic/entry.py:471-514`'s `replay_entries` frame construction (`_PAYLOAD_COLUMNS`)
    exactly. There is no `anchor_ts` column on the real L3 frame -- only `anchor_pos`, a nullable
    Int64 *position* into the replay bar index -- so rows here carry `anchor_pos`, and
    `_l3_prices` translates it. A schema drift from the real constructor should fail a test here,
    not surface as a `KeyError` the first time Task 7's driver passes real `replay_entries` output.
    """
    columns = [
        "pos", "ts", "event", "direction", "anchor_pos", "trigger", "stop", "fill", "step3_extreme"
    ]
    data = {c: [row.get(c) for row in rows] for c in columns}
    return pd.DataFrame(
        {
            "pos": pd.Series(data["pos"], dtype="Int64"),
            "ts": pd.Series(data["ts"], dtype=BAR_INDEX.dtype),
            "event": pd.Series(data["event"], dtype="object"),
            "direction": pd.Series(data["direction"], dtype="object"),
            "anchor_pos": pd.Series(data["anchor_pos"], dtype="Int64"),
            "trigger": pd.Series(data["trigger"], dtype="float64"),
            "stop": pd.Series(data["stop"], dtype="float64"),
            "fill": pd.Series(data["fill"], dtype="float64"),
            "step3_extreme": pd.Series(data["step3_extreme"], dtype="float64"),
        }
    )


def _signal_row(**over) -> dict:
    row = {
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": EmissionEvent.SIGNAL,
        "direction": "bearish",
        "blocked_by": (),
        "anchor_ts": pd.Timestamp("2026-07-31 14:50", tz="UTC"),
        "trigger": 28289.75,
        "fill": 28286.67,
        "stop": 28345.50,
        "r": 58.83,
        "tp1": None,
    }
    row.update(over)
    return row


def test_bar_offset_is_signed_and_in_bars():
    a = pd.Timestamp("2026-07-31 14:55", tz="UTC")
    b = pd.Timestamp("2026-07-31 14:40", tz="UTC")
    assert bar_offset(BAR_INDEX, a, b) == 3
    assert bar_offset(BAR_INDEX, b, a) == -3


def test_bar_offset_is_none_off_the_frame():
    off = pd.Timestamp("2026-07-31 09:00", tz="UTC")
    assert bar_offset(BAR_INDEX, off, BAR_INDEX[0]) is None


def test_exact_bar_match_produces_zero_deltas():
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert isinstance(result, LabelResult)
    assert result.matched is True
    assert result.engine_event == EmissionEvent.SIGNAL
    assert result.anchor_matched is True
    by_field = {d.field: d for d in result.deltas}
    assert by_field["trigger"].delta == 0.0
    assert by_field["stop"].delta == 0.0
    # Exact, not approx: this fixture's emission row carries `r: 58.83` as a hard-coded literal
    # (SIGNAL path never recomputes it), so it subtracts against the label's identical `58.83`
    # literal to exactly zero. The SUPPRESSED-path test below recomputes `r` by subtraction and
    # needs `pytest.approx` for the same value -- real data would carry the same float residual
    # on both paths; only this fixture's shortcut makes the SIGNAL path exact.
    assert by_field["stop_distance"].delta == 0.0


def test_one_bar_off_is_unmatched_and_characterised():
    late = _signal_row(ts=pd.Timestamp("2026-07-31 15:00", tz="UTC"))
    result = reconcile_taken(_label(), "2026-07-31", _emissions([late]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_delta_bars == 1
    assert result.nearest_ts == pd.Timestamp("2026-07-31 15:00", tz="UTC")
    assert all(d.scoreable is False for d in result.deltas)
    # No emission landed on the label's bar, so no anchor comparison ran -- `None`, not `False`
    # (a regression here would otherwise pass silently: nothing else in this file pins it).
    assert result.anchor_matched is None


def test_opposite_direction_emission_never_matches():
    wrong = _signal_row(direction="bullish")
    result = reconcile_taken(_label(), "2026-07-31", _emissions([wrong]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_ts is None


def test_no_emissions_at_all_leaves_nearest_none():
    result = reconcile_taken(_label(), "2026-07-31", _emissions([]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_ts is None
    assert result.nearest_delta_bars is None


def test_suppressed_matches_and_borrows_prices_from_l3():
    suppressed = _signal_row(
        event=EmissionEvent.SUPPRESSED, blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    l3 = _entries([{
        "pos": 11,
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": EntryEvent.ENTRY_FILLED,
        "direction": "bearish",
        "anchor_pos": 10,  # BAR_INDEX[10] == 14:50 -- the real L3 frame has no anchor_ts column
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(_label(), "2026-07-31", _emissions([suppressed]), l3, BAR_INDEX)
    assert result.matched is True
    assert result.engine_event == EmissionEvent.SUPPRESSED
    assert result.blocked_by == ("trend_50",)
    by_field = {d.field: d for d in result.deltas}
    assert by_field["trigger"].delta == 0.0
    # _l3_prices recomputes r as abs(fill - stop), mirroring stoic/emission.py's own arithmetic
    # (§5.4.2 -- no floor: D-18 on the stop, O-10 on gating R) -- so, like the engine's real
    # output, it lands a ~1e-12 float residual off the label's 2-dp literal 58.83. That residual
    # is arithmetic, not a divergence (see the comment on `_l3_prices`'s `r` line); this is
    # float-comparison hygiene, matching tests/test_levels.py's existing `pytest.approx`
    # convention, not a tolerance in the module.
    assert by_field["stop_distance"].delta == pytest.approx(0.0, abs=1e-9)
    assert result.anchor_matched is True


def test_unscoreable_field_states_a_reason_and_never_a_zero():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.scoreable is False
    assert trigger.delta is None
    assert trigger.reason != ""


def test_circular_flag_is_carried_onto_the_result():
    label = _label()
    label["phase6_scope"]["circular"] = True
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert result.circular is True


def test_delta_sign_is_engine_minus_label():
    high = _signal_row(trigger=28292.75)
    result = reconcile_taken(_label(), "2026-07-31", _emissions([high]), _entries([]), BAR_INDEX)
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.delta == 3.0
    assert isinstance(trigger, Delta)


def test_suppressed_with_no_matching_l3_entry_is_matched_but_unscoreable():
    """Negative control for _l3_prices' empty-dict branch: a SUPPRESSED row with no L3
    ENTRY_FILLED on the same bar still pairs (the SUPPRESSED emission itself landed on the
    label's bar), but carries no prices to score, and says so in `notes`."""
    suppressed = _signal_row(
        event=EmissionEvent.SUPPRESSED, blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([suppressed]), _entries([]), BAR_INDEX
    )
    assert result.matched is True
    assert result.engine_event == EmissionEvent.SUPPRESSED
    assert all(d.scoreable is False for d in result.deltas)
    by_field = {d.field: d for d in result.deltas}
    # `trigger` has a scope block (the label states a value), so its unscoreable cause is the
    # engine's missing value, not a null scope entry -- distinct from e.g. `tp1`, whose scope is
    # already null in this fixture and would report "unscoreable" for that reason regardless.
    assert by_field["trigger"].reason == "the engine emitted no value"
    assert any("prices unavailable" in note for note in result.notes)
    # The engine emitted no anchor_ts at all -- not compared, not a mismatch (item 2, round 3).
    assert result.anchor_matched is None


def test_no_entry_bar_in_scope_states_why_in_notes():
    """The one existing assertion-free path that produces a `notes` entry: the driver's Phase 6
    report prints this string as evidence, so its exact content is worth pinning."""
    label = _label()
    label["phase6_scope"]["entry_bar"] = None
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert result.matched is False
    assert result.anchor_matched is None
    assert result.notes == ("no entry bar in scope -- nothing to pair on",)


def test_anchor_mismatch_pins_the_false_case():
    """`anchor_matched` is `bool | None`; only two other tests exercise it, and both land on
    `True`/`None` -- nothing pins `False`. A one-bar-off anchor on an otherwise-matched emission
    is a real comparison that really differs, so this is the third of the three states."""
    wrong_anchor = _signal_row(anchor_ts=pd.Timestamp("2026-07-31 14:45", tz="UTC"))
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([wrong_anchor]), _entries([]), BAR_INDEX
    )
    assert result.matched is True
    assert result.anchor_matched is False


def test_l3_anchor_translation_never_raises_and_falls_back_to_none():
    """Negative control for the three "never raise, fall back to None" guards in `_l3_prices`: a
    null `anchor_pos`, an out-of-range `anchor_pos`, and (item 1's guard, round 5) an L3 row whose
    own `pos`/`ts` disagree with `bar_index` -- proof the caller passed the wrong frame. The first
    two guards degrade only the anchor; prices still resolve normally, showing the guards are
    scoped to the anchor and don't spuriously block price recovery. The third distrusts the whole
    row -- `_l3_prices` returns `{}`, matching the "no ENTRY_FILLED" case, because a `bar_index`
    that disagrees with the row's own position cannot be trusted for anything on that row.

    (`test_suppressed_matches_and_borrows_prices_from_l3` already covers the positive case --
    `anchor_pos` translating to the label's real anchor bar -- so it is not repeated here.)
    """
    suppressed = _signal_row(
        event=EmissionEvent.SUPPRESSED, blocked_by=(),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )

    # Case 1: anchor_pos is null (no anchor recorded) -- prices still resolve, the anchor does not.
    na_anchor = _entries([{
        "pos": 11, "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": EntryEvent.ENTRY_FILLED, "direction": "bearish", "anchor_pos": pd.NA,
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([suppressed]), na_anchor, BAR_INDEX
    )
    assert result.matched is True
    assert result.anchor_matched is None
    assert {d.field: d for d in result.deltas}["trigger"].scoreable is True

    # Case 2: anchor_pos is out of range for this 24-bar frame -- same fallback, not an IndexError.
    oob_anchor = _entries([{
        "pos": 11, "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": EntryEvent.ENTRY_FILLED, "direction": "bearish", "anchor_pos": 999,
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([suppressed]), oob_anchor, BAR_INDEX
    )
    assert result.matched is True
    assert result.anchor_matched is None
    assert {d.field: d for d in result.deltas}["trigger"].scoreable is True

    # Case 3 (item 1): the row's own pos disagrees with bar_index at that position -- BAR_INDEX[5]
    # is 14:25, not this row's own ts of 14:55, so bar_index cannot be the frame `pos` was
    # recorded against. _l3_prices must refuse the whole row, not just translate a wrong anchor.
    wrong_frame = _entries([{
        "pos": 5, "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": EntryEvent.ENTRY_FILLED, "direction": "bearish", "anchor_pos": 10,
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([suppressed]), wrong_frame, BAR_INDEX
    )
    assert result.matched is True
    assert result.anchor_matched is None
    assert all(d.scoreable is False for d in result.deltas)
    assert any("prices unavailable" in note for note in result.notes)


def test_suppressed_anchor_nat_in_a_real_datetime64_column_is_not_a_mismatch():
    """Defect 2's negative control: the real emissions frame stores `anchor_ts` as a tz-aware
    datetime64 column (`stoic/emission.py:517`), so a SUPPRESSED row's absent anchor arrives as
    `NaT`, not a bare Python `None`. Before the fix, `engine_anchor is None` missed `NaT` and this
    fixture reported `anchor_matched=False` -- "compared and differed" for a comparison that never
    ran. Confirms the fixture actually produces `NaT` (not `None`) before asserting on it."""
    suppressed = _emissions([_signal_row(
        event=EmissionEvent.SUPPRESSED, blocked_by=(),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )])
    assert pd.isna(suppressed.loc[0, "anchor_ts"])
    assert suppressed["anchor_ts"].dtype == BAR_INDEX.dtype
    result = reconcile_taken(_label(), "2026-07-31", suppressed, _entries([]), BAR_INDEX)
    assert result.matched is True
    assert result.anchor_matched is None


def test_event_filter_keys_off_the_engines_real_enum_value_not_a_retyped_literal():
    """The defect the first real engine run exposed: every event filter in `stoic/fidelity.py`
    compared `.astype(str)` against a hand-retyped uppercase literal (`"SIGNAL"`), while
    `EmissionEvent`/`EntryEvent` are `StrEnum`s whose real values are lowercase (`"signal"`) --
    so every filter matched nothing on real data, and all 57 tests still passed because their
    fixtures independently retyped the same wrong casing. This is the third instance of that
    fixture-agrees-with-the-bug class in this phase (after the invented `anchor_ts` column and
    the `None`-vs-`NaT` guard) -- this test pins it structurally rather than by inspection: an
    emission row carrying the engine's own `EmissionEvent.SIGNAL` must match, and the same row
    carrying the uppercase string a fixture author (or a regressed filter) might type by hand
    must not -- so a future re-introduction of a string literal in place of the enum member fails
    loudly here, not silently on the first real run.
    """
    real = _signal_row(event=EmissionEvent.SIGNAL)
    result = reconcile_taken(_label(), "2026-07-31", _emissions([real]), _entries([]), BAR_INDEX)
    assert result.matched is True

    retyped = _signal_row(event="SIGNAL")
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([retyped]), _entries([]), BAR_INDEX
    )
    assert result.matched is False


# --- Task 4: pairing for `named` and `no_opportunity` -------------------------------------------

NAMED_INDEX = pd.date_range("2026-07-27 13:30", periods=24, freq="5min", tz="UTC")
NOPP_INDEX = pd.date_range("2026-07-30 17:00", periods=24, freq="5min", tz="UTC")


def _named_label() -> dict:
    return {
        "id": "LT-B1",
        "class": "named",
        "direction": "short",
        "phase6_scope": {
            "anchor_bar": {"ts": _utc(2026, 7, 27, 13, 50), "from": "ptb.pos_ts"},
            "entry_bar": None,
            "trigger": {"price": 28446.50, "from": "ptb.trigger.bars"},
            "stop": None, "tp1": None, "expect_fill": None, "circular": False,
        },
    }


def _nopp_label() -> dict:
    return {
        "id": "PTBV30-N1",
        "class": "no_opportunity",
        "direction": "long",
        "phase6_scope": {
            "anchor_bar": None, "entry_bar": None, "trigger": None, "stop": None, "tp1": None,
            "expect_fill": False, "circular": False,
            "anchor_bar_narrated": {"ts": _utc(2026, 7, 30, 17, 25), "from": "bar_5m_et"},
        },
    }


def _anchor(ts, direction="bearish", trigger=28446.50) -> dict:
    """An L3 `PTB_ANCHORED` row, in `_entries`'s real schema. No `anchor_ts` key: the real frame
    (`stoic/entry.py:471`) has no such column, only `pos`/`anchor_pos` positions, and neither
    `reconcile_named` nor `reconcile_no_opportunity` reads either -- both pair on `ts`, `event`,
    `direction` and `trigger` alone."""
    return {
        "pos": None, "ts": ts, "event": EntryEvent.PTB_ANCHORED, "direction": direction,
        "anchor_pos": None, "trigger": trigger, "stop": None, "fill": None, "step3_extreme": None,
    }


def test_named_matches_when_the_engine_anchored_on_that_bar():
    ts = pd.Timestamp("2026-07-27 13:50", tz="UTC")
    result = reconcile_named(_named_label(), "2026-07-27", _entries([_anchor(ts)]), NAMED_INDEX)
    assert result.matched is True
    assert result.engine_event == EntryEvent.PTB_ANCHORED
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.delta == 0.0


def test_named_delta_sign_is_engine_minus_label():
    """The only other named test with a scoreable trigger delta asserts `== 0.0` (an exact-price
    fixture), so the sign convention -- engine minus label, matching reconcile_taken's own pinned
    test -- was untested here. An engine trigger 3.0 above the label's states the sign."""
    ts = pd.Timestamp("2026-07-27 13:50", tz="UTC")
    result = reconcile_named(
        _named_label(), "2026-07-27", _entries([_anchor(ts, trigger=28449.50)]), NAMED_INDEX
    )
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.delta == 3.0


def test_named_records_a_fill_as_correct_but_not_taken():
    ts = pd.Timestamp("2026-07-27 13:50", tz="UTC")
    fill = {
        "ts": pd.Timestamp("2026-07-27 13:55", tz="UTC"), "event": EntryEvent.ENTRY_FILLED,
        "direction": "bearish", "trigger": 28446.50, "stop": 28500.0,
        "fill": 28440.0, "step3_extreme": None,
    }
    result = reconcile_named(
        _named_label(), "2026-07-27", _entries([_anchor(ts), fill]), NAMED_INDEX
    )
    assert result.matched is True
    assert any("correct-but-not-taken" in note for note in result.notes)


def test_named_unmatched_is_characterised_by_the_nearest_anchor():
    ts = pd.Timestamp("2026-07-27 14:00", tz="UTC")
    result = reconcile_named(_named_label(), "2026-07-27", _entries([_anchor(ts)]), NAMED_INDEX)
    assert result.matched is False
    assert result.nearest_delta_bars == 2
    # Review finding 1: no engine anchor exists on the label's bar, so no comparison ran --
    # `None`, not `False` (reconcile_taken's structurally identical branch already pins this;
    # nothing here did until now, and an edit restoring `False` would pass silently).
    assert result.anchor_matched is None


def test_no_opportunity_with_a_cancelled_order_is_a_match():
    ts = pd.Timestamp("2026-07-30 17:25", tz="UTC")
    cancel = {
        "ts": pd.Timestamp("2026-07-30 17:40", tz="UTC"), "event": EntryEvent.ORDER_CANCELLED,
        "direction": "bullish", "trigger": 28100.0, "stop": None,
        "fill": None, "step3_extreme": None,
    }
    result = reconcile_no_opportunity(
        _nopp_label(), "2026-07-30",
        _entries([_anchor(ts, direction="bullish", trigger=28100.0), cancel]), NOPP_INDEX,
    )
    assert result.matched is True
    assert result.engine_event == EntryEvent.ORDER_CANCELLED
    assert result.notes == ("engine emitted no fill -- the label's expectation",)


def test_no_opportunity_negative_control_a_fill_is_a_divergence():
    ts = pd.Timestamp("2026-07-30 17:25", tz="UTC")
    fill = {
        "ts": pd.Timestamp("2026-07-30 17:35", tz="UTC"), "event": EntryEvent.ENTRY_FILLED,
        "direction": "bullish", "trigger": 28100.0, "stop": 28050.0,
        "fill": 28101.0, "step3_extreme": None,
    }
    result = reconcile_no_opportunity(
        _nopp_label(), "2026-07-30",
        _entries([_anchor(ts, direction="bullish", trigger=28100.0), fill]), NOPP_INDEX,
    )
    assert result.matched is False
    assert result.engine_event == EntryEvent.ENTRY_FILLED
    assert any("DIVERGENCE" in note for note in result.notes)


def test_no_opportunity_with_no_anchor_at_all_says_so():
    result = reconcile_no_opportunity(_nopp_label(), "2026-07-30", _entries([]), NOPP_INDEX)
    assert result.matched is False
    assert any("never anchored" in note for note in result.notes)
    # Review finding 1: same pinning as the named test above -- no engine anchor exists to
    # compare the label's declared bar against, so no comparison ran.
    assert result.anchor_matched is None


def test_no_opportunity_with_no_anchor_bar_declared_in_scope_says_so():
    """Review finding 2: when the label declares neither `anchor_bar` nor `anchor_bar_narrated`,
    there is nothing to pair on -- reporting "the engine never anchored" here would blame the
    engine for a gap that is the label's. Mirrors reconcile_named's `anchor_bar is None` branch."""
    label = _nopp_label()
    label["phase6_scope"]["anchor_bar_narrated"] = None
    result = reconcile_no_opportunity(label, "2026-07-30", _entries([]), NOPP_INDEX)
    assert result.matched is False
    assert result.anchor_matched is None
    assert result.notes == ("no anchor bar in scope -- nothing to pair on",)


def test_no_opportunity_with_scalar_anchor_bar_narrated_is_reported_not_raised():
    """Hardening: `anchor_bar_narrated` is the one anchor source `check_scope_consistency` never
    mapping-checks (deliberately -- its `from: bar_5m_et` field is a wall-clock string, not
    comparable by equality, so SCOPE_KEYS excludes it and only DECLARATION_KEYS validates it as a
    known key). A half-transcribed `anchor_bar_narrated: "TBD"` is therefore a truthy non-mapping
    that reaches `reconcile_no_opportunity` unchecked. Before the fix this passed the `is None`
    guard and raised `TypeError` on `anchor_block["ts"]`; it must instead be reported, matching the
    report-never-raise discipline `check_scope_consistency` already states for itself."""
    label = _nopp_label()
    label["phase6_scope"]["anchor_bar_narrated"] = "TBD"
    result = reconcile_no_opportunity(label, "2026-07-30", _entries([]), NOPP_INDEX)
    assert result.matched is False
    assert result.anchor_matched is None
    assert any("not a mapping" in note for note in result.notes)


# --- Task 5: unlabelled emissions and report rendering -----------------------------------------


def test_unlabelled_drops_the_matched_bars_only():
    matched = _signal_row()
    other = _signal_row(ts=pd.Timestamp("2026-07-31 15:10", tz="UTC"))
    results = [
        reconcile_taken(_label(), "2026-07-31", _emissions([matched]), _entries([]), BAR_INDEX)
    ]
    left = unlabelled_emissions(_emissions([matched, other]), results)
    assert len(left) == 1
    assert left.iloc[0]["ts"] == pd.Timestamp("2026-07-31 15:10", tz="UTC")


def test_unlabelled_keeps_a_same_bar_emission_of_the_other_direction():
    matched = _signal_row()
    opposite = _signal_row(direction="bullish")
    results = [
        reconcile_taken(_label(), "2026-07-31", _emissions([matched]), _entries([]), BAR_INDEX)
    ]
    left = unlabelled_emissions(_emissions([matched, opposite]), results)
    assert len(left) == 1
    assert str(left.iloc[0]["direction"]) == "bullish"


def test_report_states_the_no_verdict_line_and_the_counts():
    results = [
        reconcile_taken(
            _label(), "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
        )
    ]
    text = render_report(results, _emissions([]), {"instrument": "NQ", "frame": "5m"})
    assert "label set is not exhaustive" in text
    assert "no verdict" in text
    assert "T-A2" in text
    assert "instrument" in text


def test_report_marks_a_circular_row():
    label = _label()
    label["phase6_scope"]["circular"] = True
    results = [
        reconcile_taken(label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX)
    ]
    assert "circular" in render_report(results, _emissions([]), {}).lower()


def test_report_prints_unscoreable_rather_than_a_blank():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    results = [
        reconcile_taken(label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX)
    ]
    assert "unscoreable" in render_report(results, _emissions([]), {})


def test_unlabelled_emissions_preserves_columns_when_none_are_left():
    """Negative control: pandas treats an *empty* list as a column selector, not a boolean mask,
    so `rows[[]]` collapses a frame with no SIGNAL/SUPPRESSED rows to shape (0, 0) -- no columns --
    rather than an empty frame carrying the real schema. A caller doing `unlabelled["ts"]` on that
    session would get a KeyError."""
    empty = _emissions([])
    left = unlabelled_emissions(empty, [])
    assert len(left) == 0
    assert list(left.columns) == list(empty.columns)
    assert left["ts"].tolist() == []  # KeyError before the fix


def test_report_renders_a_non_empty_unlabelled_table_with_nan_as_an_em_dash():
    """No prior test rendered a non-empty §3 table, so the seven column accesses in that loop had
    zero coverage -- the exact defect class that bit Tasks 3 and 4. A SUPPRESSED row with no
    recovered fill carries NaN in trigger/fill/stop/r, which must render as an em-dash, not the
    literal string 'nan', in a document a human reads."""
    suppressed = _signal_row(
        ts=pd.Timestamp("2026-07-31 15:10", tz="UTC"),
        event=EmissionEvent.SUPPRESSED, blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    unlabelled = _emissions([suppressed])
    text = render_report([], unlabelled, {})
    assert "## 3. Emissions not paired to a taken label (n = 1)" in text
    assert "2026-07-31 15:10:00+00:00" in text
    # The table renders the engine's own event string -- lowercase, per EmissionEvent's real
    # values -- not an uppercase label invented by the fixture.
    assert EmissionEvent.SUPPRESSED in text
    assert "nan" not in text.lower()
    assert "—" in text


STOIC = Path(__file__).resolve().parents[1] / "stoic"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_engine_module_imports_fidelity():
    """Measurement must never be reachable from the signal path (docs/PHASE6.md §5)."""
    offenders = [
        path.name
        for path in sorted(STOIC.glob("*.py"))
        if path.name != "fidelity.py"
        if any("fidelity" in name for name in _imported_names(path))
    ]
    assert offenders == []


def test_the_import_check_can_actually_see_an_import(tmp_path):
    """Negative control: the same parser must catch a planted import."""
    planted = tmp_path / "planted.py"
    planted.write_text("from stoic.fidelity import reconcile_taken\n", encoding="utf-8")
    assert any("fidelity" in name for name in _imported_names(planted))
