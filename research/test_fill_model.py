"""ADR-0012 compliance tests for the research fill model.

ADR-0021 check 5: verify the implementation against the spec the number claims
to implement. A backtest that quietly resolves ambiguity in its own favour
produces a confident, optimistic, wrong number -- exactly the failure class
this repo has already been burned by. These assert the conservative choices.

Run: .venv/bin/python research/test_fill_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dataclasses import replace

from bnr_backtest import Bar, Params, Trade, simulate_entry_and_exit

P = Params()


def bar(o: int, h: int, lo: int, c: int, i: int = 0) -> Bar:
    return Bar(
        start_ns=i * 60_000_000_000,
        end_ns=(i + 1) * 60_000_000_000,
        o=o,
        h=h,
        lo=lo,
        c=c,
        volume=1,
        trading_date="2026-01-05",
        instrument_id=1,
        quality="complete",
    )


def long_trade() -> Trade:
    t = Trade(direction="long", level=100, signal_ns=0)
    t.entry, t.stop = 100, 90
    return t


def test_stop_wins_ambiguous_bar() -> None:
    """Both stop and target inside one bar's range -> stop, never target."""
    t = long_trade()
    minutes = [bar(100, 101, 99, 100, 0), bar(100, 130, 85, 100, 1)]
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "stop", outcome
    assert t.entry == 101, t.entry  # fill 100 + 1 tick entry slippage
    assert t.target == 123, t.target  # 101 + 2 * risk(11)
    print("ok  stop wins ambiguous bar")


def test_entry_bar_target_ignored() -> None:
    """A target touched on the entry bar does not count unless confirmed later."""
    t = long_trade()
    # bar0 fills entry at 101 AND ranges through target 123 -- must be ignored
    minutes = [bar(100, 200, 100, 150, 0), bar(150, 150, 80, 100, 1)]
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "stop", f"entry-bar target was honoured: {outcome}"
    print("ok  entry-bar target ignored")


def test_stop_gap_fills_at_worse_open() -> None:
    """Gapping through the stop fills at the open, not the stop price."""
    t = long_trade()
    minutes = [bar(100, 101, 99, 100, 0), bar(80, 85, 75, 80, 1)]
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "stop", outcome
    assert t.exit == 79, t.exit  # min(stop 90, open 80) - 1 slippage
    print("ok  stop gap fills at worse open")


def test_target_gets_no_favorable_gap() -> None:
    """Gapping far past the target still fills at the target."""
    t = long_trade()
    minutes = [bar(100, 101, 99, 100, 0), bar(200, 205, 195, 200, 1)]
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "target", outcome
    assert t.exit == 123, t.exit  # exactly the target, no improvement
    print("ok  target gets no favorable gap")


def test_entry_gap_fills_at_worse_open() -> None:
    """Gapping through the buy-stop entry fills at the open, not the level."""
    t = long_trade()
    minutes = [bar(120, 125, 118, 120, 0), bar(120, 121, 119, 120, 1)]
    simulate_entry_and_exit(t, minutes, 0, P, None)
    assert t.entry == 121, t.entry  # max(level 100, open 120) + 1 slippage
    print("ok  entry gap fills at worse open")


def test_unfilled_entry_expires() -> None:
    """Price never touching the planned entry produces no trade."""
    t = long_trade()
    minutes = [bar(95, 99, 90, 95, i) for i in range(5)]
    # low 90 == stop but entry 100 never touched -> no position was ever taken
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "expired_unfilled", outcome
    print("ok  unfilled entry expires without a trade")


def test_roll_makes_position_unresolved() -> None:
    """A physical contract change resolves the trade as unresolved, not as P/L."""
    t = long_trade()
    rolled = replace(bar(100, 130, 85, 100, 1), instrument_id=2)
    minutes = [bar(100, 101, 99, 100, 0), rolled]
    outcome = simulate_entry_and_exit(t, minutes, 0, P, None)
    assert outcome == "unresolved_roll", outcome
    print("ok  position unresolved at contract roll, not counted as P/L")


if __name__ == "__main__":
    test_stop_wins_ambiguous_bar()
    test_entry_bar_target_ignored()
    test_stop_gap_fills_at_worse_open()
    test_target_gets_no_favorable_gap()
    test_entry_gap_fills_at_worse_open()
    test_unfilled_entry_expires()
    test_roll_makes_position_unresolved()
    print("\nall ADR-0012 conservative-fill invariants hold")
