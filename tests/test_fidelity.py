"""Unit tests for stoic.fidelity (Phase 6) -- hand-built fixtures only, no disk or network.

The pairing rule is the measurement instrument, so it is the part that must be tested. Every
check here gets a negative control per `coding_rules.md`: inject the fault it exists to catch and
confirm it is caught.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from stoic import fidelity as fidelity_module
from stoic.fidelity import (
    Delta,
    LabelResult,
    bar_offset,
    check_scope_consistency,
    reconcile_taken,
    resolve_path,
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
    columns = [
        "ts", "event", "direction", "blocked_by", "anchor_ts",
        "trigger", "fill", "stop", "r", "tp1",
    ]
    return pd.DataFrame([{c: row.get(c) for c in columns} for row in rows], columns=columns)


def _entries(rows: list[dict]) -> pd.DataFrame:
    columns = ["ts", "event", "direction", "anchor_ts", "trigger", "stop", "fill", "step3_extreme"]
    return pd.DataFrame([{c: row.get(c) for c in columns} for row in rows], columns=columns)


def _signal_row(**over) -> dict:
    row = {
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": "SIGNAL",
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
    assert result.engine_event == "SIGNAL"
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
        event="SUPPRESSED", blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    l3 = _entries([{
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": "ENTRY_FILLED",
        "direction": "bearish",
        "anchor_ts": pd.Timestamp("2026-07-31 14:50", tz="UTC"),
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(_label(), "2026-07-31", _emissions([suppressed]), l3, BAR_INDEX)
    assert result.matched is True
    assert result.engine_event == "SUPPRESSED"
    assert result.blocked_by == ("trend_50",)
    by_field = {d.field: d for d in result.deltas}
    assert by_field["trigger"].delta == 0.0
    # _l3_prices recomputes r as abs(fill - stop), mirroring stoic/emission.py's own arithmetic
    # (§5.4.2, D-18) -- so, like the engine's real output, it lands a ~1e-12 float residual off
    # the label's 2-dp literal 58.83. That residual is arithmetic, not a divergence (see the
    # comment on `_l3_prices`'s `r` line); this is float-comparison hygiene, matching
    # tests/test_levels.py's existing `pytest.approx` convention, not a tolerance in the module.
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
        event="SUPPRESSED", blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([suppressed]), _entries([]), BAR_INDEX
    )
    assert result.matched is True
    assert result.engine_event == "SUPPRESSED"
    assert all(d.scoreable is False for d in result.deltas)
    assert any("prices unavailable" in note for note in result.notes)


def test_no_entry_bar_in_scope_states_why_in_notes():
    """The one existing assertion-free path that produces a `notes` entry: the driver's Phase 6
    report prints this string as evidence, so its exact content is worth pinning."""
    label = _label()
    label["phase6_scope"]["entry_bar"] = None
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert result.notes == ("no entry bar in scope -- nothing to pair on",)
