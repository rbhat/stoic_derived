"""Unit tests for stoic.fidelity (Phase 6) -- hand-built fixtures only, no disk or network.

The pairing rule is the measurement instrument, so it is the part that must be tested. Every
check here gets a negative control per `coding_rules.md`: inject the fault it exists to catch and
confirm it is caught.
"""

from __future__ import annotations

import datetime as dt

from stoic.fidelity import check_scope_consistency, resolve_path


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
