"""Tests for `scripts/forward_test.py` (Phase 7's driver).

Design: `docs/PHASE7.md` §9's exit gate, `coding_rules.md`'s negative-control rule. Hermetic: every
bar fixture is built programmatically into `tmp_path` as parquet and fed to the script via
`--bars-path` -- nothing here reads `data/historical/` (gitignored, absent on a clean clone).

**The engine fixture (`_write_1m_fixture`) drives the real engine, not a stub.** `stoic.gating`
needs 50 bars before any signal passes and 200 before one passes on a fast chart (Scalp is
`fast_chart=True`), so the fixture opens on ~220 warm-up bars at a constant price -- long enough to
clear both SMA windows -- before a hand-built bullish 1-2-3 sequence that clears
`stoic.judgment.decided_judgment()`'s real predicates (not a stub `Judgment`): a genuine Step 1
break, two non-trending ("outside") bars forming an obvious base under D-34, a break and a
meaningful close beyond it, an expansion leg, a pullback bar that anchors a PTB, and a fill. Every
5m OHLC value here is verified against the *resampled* 5m frame in this module's own smoke test
setup -- see `_expand_5m_to_1m`'s docstring for how the two are kept consistent.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.forward_test import fold_ledger, main
from stoic.bars import resample
from stoic.emission import EmissionEvent, SignalType, replay_signals
from stoic.entry import EntryEvent, replay_entries
from stoic.indicators import add_smas
from stoic.judgment import attach_parent_pos, decided_judgment
from stoic.sessions import flatten_cutoff_utc, session_close_utc, session_open_utc
from stoic.structure import Direction
from stoic.tracking import Outcome, track_outcomes

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "forward_test.py"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# The real-engine fixture: warm-up + a genuine bullish 1-2-3, as 5m OHLC rows.
# ---------------------------------------------------------------------------

WARMUP_BARS = 220
_FLAT = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}
_STEP1 = {"open": 100.0, "high": 112.0, "low": 99.0, "close": 110.0}  # Step 1
_OUTSIDE1 = {"open": 110.0, "high": 115.0, "low": 95.0, "close": 108.0}  # base candle 1 (D-34)
_OUTSIDE2 = {"open": 108.0, "high": 118.0, "low": 92.0, "close": 104.0}  # base candle 2
_BREAK_CONFIRM = {"open": 104.0, "high": 140.0, "low": 103.0, "close": 135.0}  # break + confirm
_EXPANSION = {"open": 135.0, "high": 150.0, "low": 134.0, "close": 148.0}  # new parent
_PULLBACK = {"open": 140.0, "high": 145.0, "low": 130.0, "close": 133.0}  # anchors the PTB
_FILL = {"open": 133.0, "high": 148.0, "low": 132.0, "close": 146.0}  # fills at the trigger (145)
_TP1_BAR = {"open": 146.0, "high": 152.0, "low": 145.0, "close": 150.0}  # closes the trade at TP1

FRAME_START = pd.Timestamp("2026-01-05", tz="UTC")


def _open_rows_5m() -> list[dict]:
    """Warm-up + fill, trade left open (fill bar's own high, 148, never reaches tp1 at 150)."""
    return [_FLAT] * WARMUP_BARS + [
        _STEP1, _OUTSIDE1, _OUTSIDE2, _BREAK_CONFIRM, _EXPANSION, _PULLBACK, _FILL,
    ]


def _closed_rows_5m() -> list[dict]:
    """The same trade, one bar further: TP1 (150) is cleanly traded through."""
    return [*_open_rows_5m(), _TP1_BAR]


def _expand_5m_to_1m(rows_5m: list[dict]) -> pd.DataFrame:
    """Five 1m bars per 5m row whose OHLC resample (`stoic.bars.resample`) reproduces `rows_5m`
    exactly: minute 0 sits at the open, minute 1 reaches the high, minute 2 reaches the low,
    minute 3 reaches the close from the low side, minute 4 holds the close. Every produced 1m bar
    satisfies `low <= open, close <= high` and carries positive volume, which is what
    `stoic.bars._validate` (run inside `resample`) requires.
    """
    index_5m = pd.date_range(FRAME_START, periods=len(rows_5m), freq="5min", tz="UTC")
    rows: list[dict] = []
    index: list[pd.Timestamp] = []
    for ts5, r in zip(index_5m, rows_5m, strict=True):
        o, h, low, c = r["open"], r["high"], r["low"], r["close"]
        minute_rows = [
            {"open": o, "high": o, "low": o, "close": o},
            {"open": o, "high": h, "low": o, "close": h},
            {"open": h, "high": h, "low": low, "close": low},
            {"open": low, "high": max(low, c), "low": min(low, c), "close": c},
            {"open": c, "high": c, "low": c, "close": c},
        ]
        for k, mr in enumerate(minute_rows):
            index.append(ts5 + pd.Timedelta(minutes=k))
            rows.append(mr)
    idx = pd.DatetimeIndex(index, name="ts_event")
    return pd.DataFrame(
        {
            "open": [r["open"] for r in rows],
            "high": [r["high"] for r in rows],
            "low": [r["low"] for r in rows],
            "close": [r["close"] for r in rows],
            "volume": 200,
            "symbol": "NQ",
        },
        index=idx,
    )


def _write_1m_fixture(path: Path, rows_5m: list[dict]) -> None:
    _expand_5m_to_1m(rows_5m).to_parquet(path)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, str(SCRIPT), *args], capture_output=True, text=True, cwd=REPO, timeout=60
    )


def _base_args(bars_path: Path, ledger_home: Path, report: Path) -> list[str]:
    return [
        "--instrument", "NQ",
        "--type", "scalp",
        "--start", "2026-01-05",
        "--end", "2026-01-05",
        "--bars-path", str(bars_path),
        "--ledger-home", str(ledger_home),
        "--report", str(report),
    ]


def _read_ledger(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# Precondition: the fixture produces a real SIGNAL through the real engine.
# ---------------------------------------------------------------------------


def test_fixture_precondition_produces_a_real_signal(tmp_path):
    """If the engine ever changes shape, this fails loudly instead of the exit-gate test passing
    vacuously (no signal ever tracked)."""
    minute_bars = _expand_5m_to_1m(_closed_rows_5m())
    bars = resample(minute_bars, "5m")
    bars = add_smas(bars)
    bars = attach_parent_pos(bars)
    judgment = decided_judgment()
    emissions = replay_signals(bars, judgment, instrument="NQ", type_=SignalType.SCALP, htf=None)
    signals = emissions[emissions["event"] == EmissionEvent.SIGNAL]
    assert len(signals) >= 1, "fixture must produce >=1 real SIGNAL -- see module docstring"


def test_tp1_and_the_break_even_trigger_are_the_same_frozen_number(tmp_path):
    """The tripwire for `docs/PHASE7.md` §2's premise, and it can actually fail.

    §2 removes a `break_even` outcome class on the ground that TP1 (§6.1, D-6/D-16 -- the Step 3
    extreme frozen at fill) and D-25's break-even trigger are the *same number*, so no trade can
    survive the bar that trips break-even. That is a claim about two engine modules, not about
    this harness: `stoic/entry.py` freezes `OpenEntry.step3_extreme` at fill and tests break-even
    against it, and `stoic/emission.py` sets `tp1` from the same `ENTRY_FILLED` record's
    `step3_extreme`. If they ever stop agreeing, the removed class has to come back -- and this
    test is what says so. Asserting `Outcome.BREAK_EVEN` never appears could not: nothing
    constructs it.
    """
    minute_bars = _expand_5m_to_1m(_closed_rows_5m())
    bars = attach_parent_pos(add_smas(resample(minute_bars, "5m")))
    judgment = decided_judgment()

    entries = replay_entries(bars, judgment)
    emissions = replay_signals(bars, judgment, instrument="NQ", type_=SignalType.SCALP, htf=None)

    filled = entries[entries["event"] == EntryEvent.ENTRY_FILLED]
    be = entries[entries["event"] == EntryEvent.STOP_TO_BREAK_EVEN]
    signals = emissions[emissions["event"] == EmissionEvent.SIGNAL]
    assert len(filled) >= 1, "fixture must fill -- otherwise this test proves nothing"
    assert len(be) >= 1, "fixture must trip break-even -- otherwise this test proves nothing"

    # The one claim: the level break-even fired against IS the tp1 the signal carries.
    assert set(be["step3_extreme"]) == set(filled["step3_extreme"])
    assert set(signals["tp1"]) == set(filled["step3_extreme"])


# ---------------------------------------------------------------------------
# Ledger fold -- torn tail, malformed interior line, duplicate signal_id (negative control)
# ---------------------------------------------------------------------------


def test_fold_recovers_torn_trailing_line(tmp_path):
    path = tmp_path / "scalp.jsonl"
    good = json.dumps({"kind": "signal", "signal_id": "a", "timestamp": "x", "source": "s"})
    path.write_text(good + "\n" + '{"kind": "signal", "signal_id": "b", "tim')

    fold = fold_ledger(path)

    assert fold.known_signal_ids == frozenset({"a"})


def test_fold_raises_on_malformed_interior_line(tmp_path):
    path = tmp_path / "scalp.jsonl"
    good = json.dumps({"kind": "signal", "signal_id": "a", "timestamp": "x", "source": "s"})
    path.write_text("not json at all\n" + good + "\n")

    with pytest.raises(ValueError, match="malformed ledger line"):
        fold_ledger(path)


def test_fold_raises_on_duplicate_signal_id_negative_control(tmp_path):
    """The check is the negative control (`coding_rules.md`): a duplicate must never happen, and
    this proves the check actually catches it when it does."""
    path = tmp_path / "scalp.jsonl"
    row = json.dumps({"kind": "signal", "signal_id": "dup", "timestamp": "x", "source": "s"})
    path.write_text(row + "\n" + row + "\n")

    with pytest.raises(ValueError, match="duplicate ledger rows"):
        fold_ledger(path)


# ---------------------------------------------------------------------------
# Frame-start gate -- refused, non-zero exit, both values named
# ---------------------------------------------------------------------------


def test_frame_start_mismatch_is_refused_non_zero_exit_names_both_values(tmp_path):
    ledger_home = tmp_path / "ledger"
    report = tmp_path / "report.md"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _open_rows_5m())

    rc1 = main(_base_args(bars_path, ledger_home, report))
    assert rc1 == 0
    pinned = fold_ledger(ledger_home / "scalp.jsonl").frame_starts[("NQ", "5m")]

    offset_path = tmp_path / "bars_offset.parquet"
    minute_bars = _expand_5m_to_1m(_open_rows_5m())
    minute_bars.iloc[25:].to_parquet(offset_path)  # drops the first five 5m bars

    rc2 = main(_base_args(offset_path, ledger_home, report))

    assert rc2 != 0
    assert str(pinned.isoformat()) != ""  # sanity: a real pinned value exists to compare against


def test_frame_start_mismatch_message_names_both_values(tmp_path, capsys):
    ledger_home = tmp_path / "ledger"
    report = tmp_path / "report.md"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _open_rows_5m())
    assert main(_base_args(bars_path, ledger_home, report)) == 0
    capsys.readouterr()

    offset_path = tmp_path / "bars_offset.parquet"
    minute_bars = _expand_5m_to_1m(_open_rows_5m())
    minute_bars.iloc[25:].to_parquet(offset_path)

    rc = main(_base_args(offset_path, ledger_home, report))
    out = capsys.readouterr().out

    assert rc != 0
    assert "2026-01-05T00:00:00" in out  # the pinned value
    assert "2026-01-05T00:25:00" in out  # this run's requested value


# ---------------------------------------------------------------------------
# Idempotency -- running twice over the same bars appends no second signal row
# ---------------------------------------------------------------------------


def test_idempotent_rerun_appends_no_second_signal_row(tmp_path):
    ledger_home = tmp_path / "ledger"
    report = tmp_path / "report.md"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _closed_rows_5m())
    args = _base_args(bars_path, ledger_home, report)

    assert main(args) == 0
    assert main(args) == 0

    rows = _read_ledger(ledger_home / "scalp.jsonl")
    signal_rows = [r for r in rows if r["kind"] == "signal"]
    outcome_rows = [r for r in rows if r["kind"] == "outcome"]
    assert len(signal_rows) == 1
    assert len(outcome_rows) == 1
    assert len({r["signal_id"] for r in signal_rows}) == 1


# ---------------------------------------------------------------------------
# The exit gate, as a real process boundary (docs/PHASE7.md §9)
# ---------------------------------------------------------------------------


def test_exit_gate_across_a_real_process_restart(tmp_path):
    """A signal emitted on one run is tracked to a closed outcome on a later run, across a real
    process restart, with no row lost or duplicated."""
    ledger_home = tmp_path / "ledger"
    report1 = tmp_path / "report1.md"
    report2 = tmp_path / "report2.md"
    open_path = tmp_path / "open.parquet"
    closed_path = tmp_path / "closed.parquet"
    _write_1m_fixture(open_path, _open_rows_5m())
    _write_1m_fixture(closed_path, _closed_rows_5m())

    proc1 = _run(_base_args(open_path, ledger_home, report1))
    assert proc1.returncode == 0, proc1.stdout + proc1.stderr

    ledger_path = ledger_home / "scalp.jsonl"
    fold1 = fold_ledger(ledger_path)
    assert len(fold1.known_signal_ids) == 1
    assert len(fold1.closed_signal_ids) == 0
    signal_id = next(iter(fold1.known_signal_ids))

    proc2 = _run(_base_args(closed_path, ledger_home, report2))
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr

    fold2 = fold_ledger(ledger_path)
    assert fold2.known_signal_ids == {signal_id}
    assert fold2.closed_signal_ids == {signal_id}

    rows = _read_ledger(ledger_path)
    signal_rows = [r for r in rows if r["kind"] == "signal" and r["signal_id"] == signal_id]
    outcome_rows = [r for r in rows if r["kind"] == "outcome" and r["signal_id"] == signal_id]
    assert len(signal_rows) == 1
    assert len(outcome_rows) == 1
    assert outcome_rows[0]["outcome"] == Outcome.TP1


# ---------------------------------------------------------------------------
# --dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path):
    ledger_home = tmp_path / "ledger"
    report = tmp_path / "report.md"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _closed_rows_5m())

    rc = main([*_base_args(bars_path, ledger_home, report), "--dry-run"])

    assert rc == 0
    assert not ledger_home.exists()
    assert not report.exists()


# ---------------------------------------------------------------------------
# The report -- counts and named rows only, never an aggregate of r_realized (docs/PHASE7.md §8)
# ---------------------------------------------------------------------------


def test_report_excludes_forbidden_aggregates(tmp_path):
    ledger_home = tmp_path / "ledger"
    report = tmp_path / "report.md"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _closed_rows_5m())

    assert main(_base_args(bars_path, ledger_home, report)) == 0

    text = report.read_text(encoding="utf-8").lower()
    for forbidden in ("expectancy", "win rate", "average r", "avg r", "drawdown"):
        assert forbidden not in text, f"report must never mention {forbidden!r}"


# ---------------------------------------------------------------------------
# Item 0 -- stoic.tracking's inferred bar span, on a 60m frame with real maintenance-break gaps
# ---------------------------------------------------------------------------


def test_tracking_60m_frame_flatten_bar_found_correctly_despite_maintenance_gaps():
    """`stoic/tracking.py`'s `_BAR_SPAN` used to be a hardcoded 5 minutes -- wrong for
    `SignalType.SWING`/`POSITION`, which manage on 60m/Daily (`VISION.md` Timeframes). This drives
    `track_outcomes` over three real CME trading days of 60m bars (`stoic.sessions.session_open_
    utc`/`session_close_utc`), which carry a genuine ~2h gap at each day boundary (the 17:00-18:00
    ET maintenance halt) among otherwise-1h diffs -- the exact case the module docstring says a
    `max`-based span would get wrong and a median does not. The trade fills at the open of the
    middle day and must flatten on the 60m bar containing that day's 13:58 PT cutoff, not on the
    first (wrong-timeframe) bar a stale 5-minute assumption would have found.
    """
    days = [dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)]
    opens = session_open_utc(days)
    closes = session_close_utc(days)
    index_set: set[pd.Timestamp] = set()
    for o, c in zip(opens, closes, strict=True):
        index_set.update(pd.date_range(o, c, freq="60min", inclusive="left"))
    index = pd.DatetimeIndex(sorted(index_set), name="ts_event")

    diffs = index.to_series().diff().dropna()
    assert (diffs == pd.Timedelta(hours=2)).sum() >= 2  # the maintenance-break gaps are present
    assert (diffs == pd.Timedelta(hours=1)).sum() > (diffs == pd.Timedelta(hours=2)).sum()

    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}, index=index
    )

    cutoff = flatten_cutoff_utc([days[1]])[0]
    expected_pos = int(index.searchsorted(cutoff, side="right")) - 1
    fill_pos = int(index.searchsorted(opens[1]))  # the middle day's own open

    emissions = pd.DataFrame(
        {
            "pos": pd.Series([fill_pos], dtype="Int64"),
            "ts": pd.Series([index[fill_pos]], dtype=index.dtype),
            "event": pd.Series([EmissionEvent.SIGNAL], dtype="object"),
            "direction": pd.Series([Direction.BULLISH], dtype="object"),
            "blocked_by": pd.Series([()], dtype="object"),
            "signal_id": pd.Series(["sig-60m"], dtype="object"),
            "source": pd.Series(["stoic_123"], dtype="object"),
            "instrument": pd.Series(["NQ"], dtype="object"),
            "type_": pd.Series([SignalType.SWING], dtype="object"),
            "setup_tf": pd.Series(["60m"], dtype="object"),
            "signal_ts": pd.Series([index[fill_pos]], dtype=index.dtype),
            "anchor_ts": pd.Series([index[fill_pos]], dtype=index.dtype),
            "anchor_pos": pd.Series([fill_pos], dtype="Int64"),
            "fill_pos": pd.Series([fill_pos], dtype="Int64"),
            "trigger": pd.Series([100.0], dtype="float64"),
            "fill": pd.Series([100.0], dtype="float64"),
            "stop": pd.Series([50.0], dtype="float64"),  # far away -- never reached
            "r": pd.Series([50.0], dtype="float64"),
            "tp1": pd.Series([200.0], dtype="float64"),  # far away -- never reached
            "tp2": pd.Series([None], dtype="float64"),
            "setup_type": pd.Series(["123_ptb"], dtype="object"),
            "continuation": pd.Series([False], dtype="boolean"),
            "confluence_present": pd.Series([()], dtype="object"),
            "confluence_score": pd.Series([0], dtype="Int64"),
            "confluence_of": pd.Series([3], dtype="Int64"),
        }
    )
    sequence_events = pd.DataFrame(
        {
            "pos": pd.Series([], dtype="Int64"),
            "ts": pd.Series([], dtype=index.dtype),
            "event": pd.Series([], dtype="object"),
            "direction": pd.Series([], dtype="object"),
            "boundary_level": pd.Series([], dtype="float64"),
            "base_start": pd.Series([], dtype="Int64"),
            "base_end": pd.Series([], dtype="Int64"),
            "step2_swing_pos": pd.Series([], dtype="Int64"),
            "step2_swing_price": pd.Series([], dtype="float64"),
            "step3_extreme": pd.Series([], dtype="float64"),
        }
    )

    out = track_outcomes(
        bars, emissions=emissions, sequence_events=sequence_events, minute_bars=None,
        type_=SignalType.SWING,
    )
    row = out.iloc[0]

    assert row["outcome"] == Outcome.FLATTEN
    assert row["exit_pos"] == expected_pos
    assert index[expected_pos] == pd.Timestamp("2026-01-06 21:00:00", tz="UTC")


# ---------------------------------------------------------------------------
# Findings the 2026-08-12 audit confirmed. Each of these failed before its fix.
# ---------------------------------------------------------------------------


def test_append_after_a_torn_tail_loses_nothing(tmp_path):
    """The negative control the first build was missing. Its torn-tail test only *folded*; the
    step that actually failed is the APPEND after a tear. Appending straight onto a torn line
    silently swallows the whole next batch, and the batch after that turns it into a malformed
    interior line every later fold rejects -- one torn write bricking the ledger permanently."""
    from scripts.forward_test import _append_ledger_rows

    path = tmp_path / "scalp.jsonl"
    good = json.dumps({"kind": "signal", "signal_id": "a", "timestamp": "x", "source": "s"})
    path.write_text(good + "\n" + '{"kind": "signal", "signal_i')  # torn tail

    _append_ledger_rows(path, [{"kind": "signal", "signal_id": "c"}])
    assert fold_ledger(path).known_signal_ids == {"a", "c"}  # 'c' survives the tear

    _append_ledger_rows(path, [{"kind": "signal", "signal_id": "d"}])
    assert fold_ledger(path).known_signal_ids == {"a", "c", "d"}  # and the file still folds


def test_suppressed_key_does_not_collide_across_instruments(tmp_path):
    """`pos` indexes a per-instrument frame while one Type's ledger holds several instruments, so
    a key without the instrument drops every ES row whose (pos, direction) matches an NQ one."""
    from scripts.forward_test import _append_ledger_rows

    path = tmp_path / "scalp.jsonl"
    _append_ledger_rows(path, [
        {"kind": "suppressed", "instrument": "NQ", "pos": 7, "direction": "bullish"},
        {"kind": "suppressed", "instrument": "ES", "pos": 7, "direction": "bullish"},
    ])
    keys = fold_ledger(path).known_suppressed_keys
    assert keys == {("NQ", 7, "bullish"), ("ES", 7, "bullish")}


@pytest.mark.parametrize(
    "kind, row",
    [
        ("signal", {"kind": "signal", "signal_id": "x"}),
        ("outcome", {"kind": "outcome", "signal_id": "x", "outcome": "tp1"}),
        ("suppressed", {"kind": "suppressed", "instrument": "NQ", "pos": 1,
                        "direction": "bullish"}),
        ("break_even", {"kind": "break_even", "instrument": "NQ", "pos": 1,
                        "direction": "bullish", "signal_id": "x"}),
        ("frame", {"kind": "frame", "instrument": "NQ", "timeframe": "5m",
                   "frame_start": "2026-01-05T00:00:00+00:00"}),
    ],
)
def test_duplicate_detection_covers_every_row_kind(tmp_path, kind, row):
    """Negative control per row kind. The first build checked `signal` only, so a duplicate of any
    other kind was absorbed silently into a set -- a lost row reporting as success."""
    path = tmp_path / "scalp.jsonl"
    line = json.dumps(row)
    path.write_text(line + "\n" + line + "\n")
    with pytest.raises(ValueError, match="duplicate ledger rows"):
        fold_ledger(path)


def test_a_noop_rerun_appends_nothing_at_all(tmp_path):
    """Including the watermark: a row appended unconditionally makes the file grow without bound
    and makes 'this run appended nothing' untrue."""
    ledger_home = tmp_path / "ledger"
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _closed_rows_5m())
    args = _base_args(bars_path, ledger_home, tmp_path / "r.md")

    assert main(args) == 0
    first = (ledger_home / "scalp.jsonl").read_bytes()
    assert main([*args, "--report", str(tmp_path / "r2.md")]) == 0
    assert (ledger_home / "scalp.jsonl").read_bytes() == first  # byte-identical, not just same len


@pytest.mark.parametrize("bad_type", ["swing", "position"])
def test_non_5m_types_are_refused_not_resampled_wrong(tmp_path, bad_type):
    """D-7 puts Swing on the 60m and Position on the Daily; this driver resamples to 5m. Running
    them would silently mismatch the timeframe the emitted SignalRecord claims."""
    bars_path = tmp_path / "bars.parquet"
    _write_1m_fixture(bars_path, _closed_rows_5m())
    args = _base_args(bars_path, tmp_path / "ledger", tmp_path / "r.md")
    args[args.index("--type") + 1] = bad_type

    proc = _run(args)
    assert proc.returncode != 0
    assert bad_type in (proc.stdout + proc.stderr)
