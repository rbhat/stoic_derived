"""The Phase 0 exit gate: prove the resampled bar spine and session clock are correct.

Five gates, each printing literal evidence (never a summary) and its own [PASS]/[FAIL] line:

* **Gate A** — resample 1m to 60m and compare against the vendor's own 1h bars, per symbol, over
  the full history. This is the load-bearing check: if our resample doesn't reproduce Databento's
  own aggregation exactly, nothing built on top of `stoic.bars` can be trusted.
* **Gate B** — a negative control for Gate A (coding_rules.md: "a check never observed failing is
  not evidence"). Two faults are injected into the comparison Gate A runs, and each must be caught.
* **Gate C** — the session clock across both 2025-11-02 (fall back) and 2026-03-08 (spring
  forward): every anchor instant, the real-time span each trading day covers, `session_date()`
  itself on the boundary bars of each transition Sunday, and a negative control that re-introduces
  the tz-aware `+ Timedelta(days=1)` bug `session_date()` used to have and confirms it's caught.
* **Gate D** — coverage counts for every symbol/timeframe, plus the session-label breakdown on the
  5m frame.
* **Gate E** — session continuity over the whole dataset: every session_date's 5m bar count should
  sit near the normal-day norm (~273); an outlier session is exactly the shape a `session_date()`
  bug produces (a phantom short session plus a truncated neighbour), so this is the check that
  would have caught the fall-back bug from the data side rather than from knowing where to look.

Read-only: this script writes nothing to disk. It takes well under a minute, so there is nothing to
resume; each gate prints its own elapsed time as it goes.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

# `stoic` lives at the repo root, one level up from scripts/. Running this file directly (as the
# Definition of Done does: `.venv/bin/python scripts/check_bar_spine.py`) puts only scripts/ on
# sys.path, not the repo root — [tool.uv] package = false means there's no installed package to
# fall back on either, so the path needs this explicit push before the local import below.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stoic.bars import HISTORICAL, SYMBOLS, load_1m, load_bars, resample
from stoic.sessions import (
    CME_CLOSE_HOUR_ET,
    ET,
    flatten_cutoff_utc,
    london_open_utc,
    ny_open_utc,
    session_close_utc,
    session_date,
    session_open_utc,
)

OHLCV = ["open", "high", "low", "close", "volume"]


def _et_ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> pd.Timestamp:
    """A UTC Timestamp built from a wall-clock instant in America/New_York.

    Goes through `zoneinfo` rather than a hand-computed UTC offset, deliberately: a hand-computed
    offset is exactly the class of mistake `session_date()`'s bug was.
    """
    return pd.Timestamp(datetime(year, month, day, hour, minute, tzinfo=ET)).tz_convert("UTC")


@dataclass(frozen=True)
class SpineComparison:
    """A resampled frame compared against the vendor's own bars over their shared timestamps."""

    resampled_bars: int
    vendor_bars: int
    shared: int
    resampled_only: int
    vendor_only: int
    mismatched: int
    worst: pd.DataFrame

    @property
    def ok(self) -> bool:
        return self.resampled_only == 0 and self.vendor_only == 0 and self.mismatched == 0


def compare_to_vendor(resampled: pd.DataFrame, vendor: pd.DataFrame) -> SpineComparison:
    """Compare `resampled` to `vendor` on index membership and on open/high/low/close/volume.

    "Worst" rows are ranked by the largest single-field absolute difference, across any of the 5
    fields — not just close — since a fault could show up in volume alone.
    """
    resampled_idx, vendor_idx = resampled.index, vendor.index
    shared = resampled_idx.intersection(vendor_idx)
    resampled_only = resampled_idx.difference(vendor_idx)
    vendor_only = vendor_idx.difference(resampled_idx)

    diff = (
        resampled.loc[shared, OHLCV].astype("float64")
        - vendor.loc[shared, OHLCV].astype("float64")
    ).abs()
    worst_field = diff.max(axis=1)
    mismatched = diff[worst_field > 0]
    worst = mismatched.assign(_worst=worst_field[worst_field > 0]).nlargest(5, "_worst")
    worst = worst.drop(columns="_worst")

    return SpineComparison(
        resampled_bars=len(resampled),
        vendor_bars=len(vendor),
        shared=len(shared),
        resampled_only=len(resampled_only),
        vendor_only=len(vendor_only),
        mismatched=len(mismatched),
        worst=worst,
    )


def gate_a() -> bool:
    """60m resample vs vendor 1h, full overlap, per symbol — literal counts, no summarising."""
    print("\n=== Gate A: 60m resample vs vendor 1h ===")
    started = time.perf_counter()
    ok = True

    for symbol in SYMBOLS:
        resampled = resample(load_1m(symbol), "60m")
        vendor = pd.read_parquet(HISTORICAL / f"{symbol}_1h.parquet")
        cmp = compare_to_vendor(resampled, vendor)

        print(f"  {symbol}:")
        print(f"    resampled bar count : {cmp.resampled_bars:,}")
        print(f"    vendor bar count    : {cmp.vendor_bars:,}")
        print(f"    shared timestamps   : {cmp.shared:,}")
        print(f"    resampled-only      : {cmp.resampled_only:,}")
        print(f"    vendor-only         : {cmp.vendor_only:,}")
        print(f"    mismatched bars     : {cmp.mismatched:,}")
        if cmp.mismatched > 0:
            print("    worst 5 mismatched bars:")
            print(cmp.worst.to_string())
        ok = ok and cmp.ok

    elapsed = time.perf_counter() - started
    print(f"[{'PASS' if ok else 'FAIL'}] Gate A  ({elapsed:.2f}s)")
    return ok


def gate_b() -> bool:
    """Negative control for Gate A: inject two faults and confirm the comparison catches each."""
    print("\n=== Gate B: negative controls for Gate A ===")
    started = time.perf_counter()
    symbol = "NQ"
    m1 = load_1m(symbol)
    resampled = resample(m1, "60m")
    vendor = pd.read_parquet(HISTORICAL / f"{symbol}_1h.parquet")

    # Fault 1: perturb one resampled close by +0.25 — must surface as exactly 1 mismatched bar.
    faulted = resampled.copy()
    victim = faulted.index[100]
    before = float(faulted.loc[victim, "close"])
    faulted.loc[victim, "close"] = before + 0.25
    cmp1 = compare_to_vendor(faulted, vendor)
    fault1_caught = cmp1.mismatched == 1
    print(f"  fault 1: perturbed {symbol} 60m close at {victim}")
    print(f"    injected: {before} -> {before + 0.25}")
    print(f"    reported mismatched bars : {cmp1.mismatched}  (expected 1)")
    print(f"    [{'CAUGHT' if fault1_caught else 'MISSED'}]")

    # Fault 2: resample with label="right" instead of "left" — must surface as a large index
    # disagreement (Gate A's real run reports 0/0 resampled-only/vendor-only; this must not).
    agg = {
        "symbol": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    wrong = m1.resample("60min", label="right", closed="left").agg(agg).dropna(subset=["open"])
    wrong["volume"] = wrong["volume"].astype("uint64")
    cmp2 = compare_to_vendor(wrong, vendor)
    # A real pass reports 0/0; treat "large" as three orders of magnitude above that, well below
    # the ~1,812 actually observed, so the bar is easy to clear without being a coincidence.
    fault2_caught = cmp2.resampled_only > 500 and cmp2.vendor_only > 500
    print('  fault 2: resampled with label="right" instead of label="left"')
    print(
        f"    reported: shared={cmp2.shared:,} resampled-only={cmp2.resampled_only:,} "
        f"vendor-only={cmp2.vendor_only:,}  (expect resampled-only and vendor-only both > 500)"
    )
    print(f"    [{'CAUGHT' if fault2_caught else 'MISSED'}]")

    ok = fault1_caught and fault2_caught
    elapsed = time.perf_counter() - started
    print(f"[{'PASS' if ok else 'FAIL'}] Gate B  ({elapsed:.2f}s)")
    return ok


def _session_date_with_flag(index: pd.DatetimeIndex, *, buggy: bool) -> pd.Series:
    """session_date(), with `buggy=True` reproducing the pre-fix arithmetic — Gate C's negative
    control only; `stoic.sessions.session_date` never contains the `buggy=True` branch.

    The bug: shifting the +1-day offset on the tz-aware ET timestamp makes `Timedelta(days=1)` add
    24 *real* hours rather than one calendar day. On the US fall-back day (25 real hours from local
    midnight to local midnight), that lands 1 hour short of the next midnight and misdates the bar.
    """
    et = index.tz_convert(ET)
    shift = (et.hour >= CME_CLOSE_HOUR_ET).astype("int64")
    if buggy:
        shifted = et.normalize() + pd.to_timedelta(shift, unit="D")
    else:
        shifted = et.tz_localize(None).normalize() + pd.to_timedelta(shift, unit="D")
    return pd.Series(shifted.date, index=index, name="session_date", dtype=object)


def gate_c() -> bool:
    """Session boundaries across DST, both directions, with the real-time span each day covers."""
    print("\n=== Gate C: session boundaries across DST ===")
    started = time.perf_counter()
    ok = True

    fall_back_dates = [date(2025, 11, 1), date(2025, 11, 2), date(2025, 11, 3)]
    spring_forward_dates = [date(2026, 3, 6), date(2026, 3, 8), date(2026, 3, 9)]
    transitions = [
        ("fall back (America/New_York falls back 2025-11-02)", fall_back_dates),
        ("spring forward (America/New_York springs forward 2026-03-08)", spring_forward_dates),
    ]
    expected_span_h = {
        date(2025, 11, 1): 23.0,
        date(2025, 11, 2): 24.0,
        date(2025, 11, 3): 23.0,
        date(2026, 3, 6): 23.0,
        date(2026, 3, 8): 22.0,
        date(2026, 3, 9): 23.0,
    }

    ny_by_date: dict[date, pd.Timestamp] = {}
    flatten_by_date: dict[date, pd.Timestamp] = {}

    for label, dates in transitions:
        print(f"  -- {label} --")
        opened = session_open_utc(dates)
        closed = session_close_utc(dates)
        london = london_open_utc(dates)
        ny = ny_open_utc(dates)
        flatten = flatten_cutoff_utc(dates)
        for i, d in enumerate(dates):
            ny_by_date[d] = ny[i]
            flatten_by_date[d] = flatten[i]
            span_h = (closed[i] - opened[i]).total_seconds() / 3600
            print(f"    session_date={d}")
            print(f"      session_open_utc   = {opened[i]}")
            print(f"      london_open_utc    = {london[i]}")
            print(f"      ny_open_utc        = {ny[i]}")
            print(f"      flatten_cutoff_utc = {flatten[i]}")
            print(f"      session_close_utc  = {closed[i]}")
            print(f"      open->close span   = {span_h:.1f}h")
            expected = expected_span_h[d]
            span_ok = span_h == expected
            print(f"      [{'PASS' if span_ok else 'FAIL'}] expected span {expected:.1f}h")
            ok = ok and span_ok

    print("  -- offsets flip in the correct direction --")
    flip_checks = [
        ("ny_open before fall-back (EDT)", ny_by_date[date(2025, 11, 1)], "2025-11-01 13:30"),
        ("ny_open after fall-back (EST)", ny_by_date[date(2025, 11, 3)], "2025-11-03 14:30"),
        ("ny_open before spring-fwd (EST)", ny_by_date[date(2026, 3, 6)], "2026-03-06 14:30"),
        ("ny_open after spring-fwd (EDT)", ny_by_date[date(2026, 3, 9)], "2026-03-09 13:30"),
        ("flatten before fall-back (PDT)", flatten_by_date[date(2025, 11, 1)], "2025-11-01 20:58"),
        ("flatten after fall-back (PST)", flatten_by_date[date(2025, 11, 3)], "2025-11-03 21:58"),
        ("flatten before spring-fwd (PST)", flatten_by_date[date(2026, 3, 6)], "2026-03-06 21:58"),
        ("flatten after spring-fwd (PDT)", flatten_by_date[date(2026, 3, 9)], "2026-03-09 20:58"),
    ]
    for name, actual, expected_str in flip_checks:
        expected = pd.Timestamp(expected_str, tz="UTC")
        passed = actual == expected
        print(f"    {name}: {actual}  (expected {expected})  [{'PASS' if passed else 'FAIL'}]")
        ok = ok and passed

    # session_date() itself, fed real UTC bar timestamps spanning both transitions. This is the
    # function ny_open_utc/flatten_cutoff_utc/etc. above all *consume* session_date as an argument
    # from; none of them exercise session_date()'s own +1-day derivation, which is where the bug
    # actually lived. The 17:00 ET bar is the last bar of the closing trading day; the 18:00 ET bar
    # is the first bar of the next one — both must roll to the next calendar date.
    print("  -- session_date() on the 17:00/18:00 ET boundary bars of each transition Sunday --")
    boundary_transitions = [
        ("fall back", date(2025, 11, 2), date(2025, 11, 3)),
        ("spring forward", date(2026, 3, 8), date(2026, 3, 9)),
    ]
    for label, sunday, expected_sd in boundary_transitions:
        y, m, d = sunday.year, sunday.month, sunday.day
        bars = pd.DatetimeIndex([_et_ts(y, m, d, 17), _et_ts(y, m, d, 18)])
        et_local = bars.tz_convert(ET)
        derived = session_date(bars)
        for i, tag in enumerate(("17:00 ET (closing bar)", "18:00 ET (opening bar)")):
            passed = derived.iloc[i] == expected_sd
            print(
                f"    {label} {sunday} {tag}: utc={bars[i]}  et={et_local[i]}  "
                f"-> session_date={derived.iloc[i]}  (expected {expected_sd})  "
                f"[{'PASS' if passed else 'FAIL'}]"
            )
            ok = ok and passed

    # Negative control (coding_rules.md: a check never observed failing is not evidence). Re-run
    # the same fall-back assertion through the pre-fix arithmetic and confirm it fails, then
    # through the fix (mirrored locally, and separately through the real import) and confirm both
    # pass — proving this gate can actually tell the bug from the fix, not just repeat the fix back.
    print("  -- negative control: pre-fix tz-aware + Timedelta(days=1) arithmetic --")
    fallback_boundary = pd.DatetimeIndex([_et_ts(2025, 11, 2, 17), _et_ts(2025, 11, 2, 18)])
    expected_sd = date(2025, 11, 3)

    expected_pair = [expected_sd, expected_sd]

    buggy_dates = _session_date_with_flag(fallback_boundary, buggy=True)
    buggy_wrongly_passes = bool((buggy_dates == expected_sd).all())
    buggy_verdict = "UNEXPECTEDLY PASSED — negative control is broken"
    if not buggy_wrongly_passes:
        buggy_verdict = "FAIL as expected — bug reproduced"
    print(f"    buggy=True   -> {list(buggy_dates)}  (expected {expected_pair})")
    print(f"      [{buggy_verdict}]")

    mirrored_fixed_dates = _session_date_with_flag(fallback_boundary, buggy=False)
    mirrored_fix_passes = bool((mirrored_fixed_dates == expected_sd).all())
    print(f"    buggy=False  -> {list(mirrored_fixed_dates)}  (expected {expected_pair})")
    print(f"      [{'PASS' if mirrored_fix_passes else 'FAIL'}]")

    real_dates = session_date(fallback_boundary)
    real_fix_passes = bool((real_dates == expected_sd).all())
    real_verdict = "PASS" if real_fix_passes else "FAIL"
    print(f"    stoic.sessions.session_date -> {list(real_dates)}  [{real_verdict}]")

    negative_control_ok = (not buggy_wrongly_passes) and mirrored_fix_passes and real_fix_passes
    ok = ok and negative_control_ok

    elapsed = time.perf_counter() - started
    print(f"[{'PASS' if ok else 'FAIL'}] Gate C  ({elapsed:.2f}s)")
    return ok


def gate_d() -> bool:
    """Coverage counts for every symbol/timeframe, plus the session breakdown on the 5m frame."""
    print("\n=== Gate D: coverage counts ===")
    started = time.perf_counter()
    ok = True

    for symbol in SYMBOLS:
        print(f"  -- {symbol} --")
        m1 = load_1m(symbol)
        for timeframe in ("5m", "15m", "60m", "1D", "1W"):
            out = resample(m1, timeframe)
            print(f"    {timeframe:>3}: {len(out):>9,} bars  {out.index[0]} .. {out.index[-1]}")
            if len(out) == 0:
                ok = False
            if timeframe == "1D":
                n_sessions = out["session_date"].nunique()
                print(f"         session dates: {n_sessions:,}")
                ok = ok and n_sessions == len(out)
            if timeframe == "1W":
                n_weeks = out["week_start"].nunique()
                print(f"         ISO weeks: {n_weeks:,}")
                ok = ok and n_weeks == len(out)

        labelled = load_bars(symbol, "5m", sessions=True)
        print("    5m session-category counts:")
        counts = labelled["session"].value_counts().sort_index()
        for category, count in counts.items():
            print(f"      {category:>8}: {count:>9,}")
        rth_count = int(labelled["rth"].sum())
        past_flatten_count = int(labelled["past_flatten"].sum())
        print(f"    5m rth count         : {rth_count:,}")
        print(f"    5m past_flatten count: {past_flatten_count:,}")

        ok = ok and int(counts.sum()) == len(labelled)
        ok = ok and rth_count > 0
        # past_flatten = bar start >= 16:58 ET. 5m bars start on the :00/:05/.../:55 grid, and
        # 16:58 ET falls strictly inside the [16:55, 17:00) bucket without ever being its start —
        # so on a clean 5m frame this is arithmetically 0, not just empirically so. A nonzero count
        # here means a bar is starting somewhere it shouldn't (this is exactly how the session_date
        # DST bug first surfaced: it produced 504 = 7 fall-back Sundays x 72 phantom-session bars).
        if past_flatten_count != 0:
            print(f"    [FAIL] expected 0 past_flatten 5m bars, got {past_flatten_count}:")
            print(labelled.loc[labelled["past_flatten"], ["session_date", "session"]].to_string())
        ok = ok and past_flatten_count == 0

    elapsed = time.perf_counter() - started
    print(f"[{'PASS' if ok else 'FAIL'}] Gate D  ({elapsed:.2f}s)")
    return ok


# Genuine, named exceptions to Gate E's session-length floor: real holiday half-days, source-data
# outages we have already characterised, and the dataset's own start/end edges — not bugs. Anything
# below the floor that is NOT listed here fails the gate rather than being silently accepted.
#
# 2025-11-28 was originally labelled here as the Thanksgiving early close. That was wrong, and the
# mislabel mattered: it explained a real hole in the source data away as a benign exchange
# schedule. The early close happens every year in this dataset and yields 231 5m bars (session
# Thu 18:00 -> Fri 13:10 ET); 2025 spans that identical window holding only 102, because ~645
# minutes of 1m bars are simply absent. See `_GATE_E_NAMED_GAPS` for the measured hole.
_GATE_E_NAMED_EXCEPTIONS: dict[str, dict[date, str]] = {
    "NQ": {
        date(2025, 11, 28): "source-data outage — ~645 min of 1m bars absent inside an "
        "otherwise-normal Black Friday session; see the Gate E gap sweep below",
    },
    "ES": {
        date(2025, 11, 28): "source-data outage — ~645 min of 1m bars absent inside an "
        "otherwise-normal Black Friday session; see the Gate E gap sweep below",
        date(2026, 6, 9): "last session in data/historical/ES_1m.parquet — truncated mid-day by "
        "the pull's end, not by trading activity",
    },
}

# Named exceptions to the intra-session gap sweep, keyed by (symbol, session_date). A session-length
# floor is a single threshold over a mixed population — the anti-pattern coding_rules.md warns about
# under "Stratify before gating" — and it cannot see a hole *inside* an otherwise-full session:
# 2020-03-16 keeps 172 5m bars and sails over the floor while containing six multi-hour halts. The
# sweep below is what catches that class.
#
# The gate does not take these labels on faith; it prints the price on either side of every gap,
# which is what actually separates the two causes. Trading halted at a price limit resumes at the
# *same price to the penny* (no trade may print through the limit). A hole in the data resumes
# wherever the market drifted to while we were not recording it.
_GATE_E_NAMED_GAPS: dict[str, dict[date, str]] = {
    "NQ": {
        date(2020, 3, 16): "COVID limit-down halts — six halts, price frozen at 7556.00 across "
        "every one; session low -11.45% vs the prior session close",
        date(2020, 3, 17): "COVID limit-down halt carrying into the next session",
        date(2025, 11, 28): "source-data outage — price moved across the hole, so not a halt",
    },
    "ES": {
        date(2025, 11, 28): "source-data outage — price moved across the hole, so not a halt",
    },
}

# Gaps lying entirely inside the 17:00-18:00 ET maintenance halt are not intra-session gaps at all:
# a stray bar printed at 17:00 ET already carries the *next* day's session_date (the same stray-bar
# population Gate D reports as `closed`), so the halt shows up spanning two bars of one session.
# Excluded by construction rather than named per-date, since it is structural, not incidental.
_GAP_FLOOR = pd.Timedelta(minutes=30)


def gate_e() -> bool:
    """Session continuity over the whole dataset: every session_date's 5m bar count vs. the norm.

    A normal trading day has ~273 5m bars (23h open minus the 5 5m buckets the maintenance halt
    removes). A phantom or truncated session — exactly the shape the pre-fix session_date() bug
    produced, one 72-bar phantom plus one bar short its opening hours, per fall-back year — shows
    up as an outlier far below that. This is the check that finds that class of bug from the data
    itself, without already knowing which date or which function to suspect.
    """
    print("\n=== Gate E: session continuity over the full dataset ===")
    started = time.perf_counter()
    ok = True
    floor = 150

    for symbol in SYMBOLS:
        m1 = load_1m(symbol)
        fivem = resample(m1, "5m")
        sd = session_date(fivem.index)
        counts = sd.value_counts().sort_index()
        outliers = counts[counts < floor]

        print(f"  {symbol}: {len(counts):,} session dates, floor={floor} 5m bars/session")
        if outliers.empty:
            print("    no outlier sessions")
        for session_dt, count in outliers.items():
            weekday = pd.Timestamp(session_dt).day_name()
            reason = _GATE_E_NAMED_EXCEPTIONS.get(symbol, {}).get(session_dt)
            tag = f"NAMED: {reason}" if reason else "UNEXPLAINED"
            print(f"    {session_dt} ({weekday}): {count} bars  [{tag}]")
            if reason is None:
                ok = False

        ok = _report_intra_session_gaps(symbol, m1) and ok

    ok = _gap_sweep_negative_control() and ok

    elapsed = time.perf_counter() - started
    print(f"[{'PASS' if ok else 'FAIL'}] Gate E  ({elapsed:.2f}s)")
    return ok


def _gap_sweep_negative_control() -> bool:
    """Cut a hole in a known-clean session and confirm the sweep reports it as UNEXPLAINED.

    coding_rules.md: a check never observed failing is not evidence. The sweep passing on real data
    only means something once it has been seen to fail on a fault it was built to catch.
    """
    print("  negative control: excise 90 min from a clean session and re-sweep")
    m1 = load_1m("NQ")
    sd = session_date(m1.index).to_numpy()
    victim = date(2024, 5, 15)  # an ordinary full session, no halts, no outages
    session_only = m1[sd == victim]
    hole = session_only.index[100:190]
    injured = session_only.drop(index=hole)

    caught = not _report_intra_session_gaps("NQ_INJECTED", injured)
    verdict = "[CAUGHT]" if caught else "[MISSED — the sweep does not work]"
    print(f"    excised {len(hole)} min from session {victim}: {verdict}")
    return caught


def _report_intra_session_gaps(symbol: str, m1: pd.DataFrame) -> bool:
    """Print every gap over `_GAP_FLOOR` between consecutive 1m bars of the *same* session.

    Prints the price on both sides of each gap, because that is the evidence that classifies it:
    a limit halt resumes at the same price to the penny, a data outage resumes wherever the market
    drifted to meanwhile. An unnamed gap fails the gate.
    """
    sd = session_date(m1.index).to_numpy()
    deltas = m1.index.to_series().diff()
    same_session = pd.Series(False, index=m1.index)
    same_session.iloc[1:] = sd[1:] == sd[:-1]

    et = m1.index.tz_convert(ET)
    in_maintenance = np.asarray(et.hour == CME_CLOSE_HOUR_ET)
    starts_in_maintenance = pd.Series(False, index=m1.index)
    starts_in_maintenance.iloc[1:] = in_maintenance[:-1]

    flagged = (deltas > _GAP_FLOOR) & same_session & ~starts_in_maintenance
    gaps = deltas[flagged].sort_values(ascending=False)

    print(f"    intra-session gaps > {int(_GAP_FLOOR.total_seconds() // 60)} min: {len(gaps)}")
    ok = True
    for resume_ts, delta in gaps.items():
        halt_ts = resume_ts - delta
        last_close = float(m1["close"].asof(halt_ts))
        resume_open = float(m1.at[resume_ts, "open"])
        moved = (resume_open / last_close - 1) * 100
        signature = "price frozen -> halt" if last_close == resume_open else "price moved -> gap"
        session_dt = sd[m1.index.get_loc(resume_ts)]
        reason = _GATE_E_NAMED_GAPS.get(symbol, {}).get(session_dt)
        tag = f"NAMED: {reason}" if reason else "UNEXPLAINED"
        print(
            f"      {int(delta.total_seconds() // 60):4d} min  "
            f"{halt_ts.astimezone(ET):%Y-%m-%d %a %H:%M} -> {resume_ts.astimezone(ET):%H:%M} ET  "
            f"(session {session_dt})"
        )
        print(
            f"             {last_close:,.2f} -> {resume_open:,.2f} ({moved:+.2f}%)  "
            f"{signature}  [{tag}]"
        )
        if reason is None:
            ok = False
    return ok


def main() -> int:
    started = time.perf_counter()
    results = {"A": gate_a(), "B": gate_b(), "C": gate_c(), "D": gate_d(), "E": gate_e()}
    elapsed = time.perf_counter() - started

    print(f"\ntotal {elapsed:.1f}s")
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        print(f"FAILED: gate(s) {', '.join(failed)}")
        return 1
    print("all gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
