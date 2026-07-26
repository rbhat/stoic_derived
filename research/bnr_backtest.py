"""Break-and-retest at a prior-session level: first honest expectancy probe on NQ.

RESEARCH ARTIFACT (ADR-0013). Not a rulebook release, not a live gate (ADR-0011).

What this is
------------
`strategy/rulebook.yaml` carries three `executable_rule` entries whose every
claim reads "No deterministic contract is validated", and twelve
`unresolved_decisions` that are exactly the numbers a predicate needs. This
file commits to one concrete set of those numbers so the price data can be
asked a question. The parameters are DECLARED UP FRONT and not fitted;
ADR-0011 forbids an optimizer, so the sensitivity grid below is reported in
full and no cell is selected as "the" result.

Fill model is ADR-0012, implemented literally:
  - fill observation starts strictly AFTER the signal bar's end
  - entry requires a range touch of a planned level, on complete 1m bars
  - stop wins any bar where both stop and target are touchable
  - a target touched on the entry bar is ignored unless confirmed later
  - gaps through the stop fill at the worse open; targets get no favorable gap
  - entry/exit slippage and round-turn fees are explicit integer ticks
  - non-Position flatten on the 1m bar whose end is 13:58:00 America/Los_Angeles
  - a position becomes unresolved rather than crossing a physical contract roll

Results are reported in TICKS and R. ADR-0012 holds dollar P/L until an
approved contract economics manifest exists; any dollar figure quoted from
this output is illustrative arithmetic, not a system output.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
PACIFIC = ZoneInfo("America/Los_Angeles")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[1]
BARS = REPO / ".artifacts/research/bars"


def to_ct(ns: int) -> datetime:
    return (EPOCH + timedelta(microseconds=ns // 1000)).astimezone(CHICAGO)


def to_pt(ns: int) -> datetime:
    return (EPOCH + timedelta(microseconds=ns // 1000)).astimezone(PACIFIC)


@dataclass(frozen=True, slots=True)
class Bar:
    start_ns: int
    end_ns: int
    o: int
    h: int
    lo: int
    c: int
    volume: int
    trading_date: str
    instrument_id: int
    quality: str


def load_bars(timeframe: str) -> list[Bar]:
    out: list[Bar] = []
    with (BARS / f"NQ_{timeframe}.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(
                Bar(
                    start_ns=d["start_ns"],
                    end_ns=d["end_ns"],
                    o=d["open_ticks"],
                    h=d["high_ticks"],
                    lo=d["low_ticks"],
                    c=d["close_ticks"],
                    volume=d["volume"],
                    trading_date=d["trading_date"],
                    instrument_id=d["instrument_id"],
                    quality=d["quality"],
                )
            )
    out.sort(key=lambda b: (b.end_ns, b.start_ns))
    return out


def derive_daily(m1: list[Bar]) -> list[Bar]:
    """Session high/low per trading date, derived from the 1m bars themselves.

    Preferred over the aggregator's DAILY series so the level and the fill data
    provably come from the same bars -- a daily bar built from a different pass
    could disagree at a session edge and silently move every level.
    """
    by_date: dict[str, list[Bar]] = {}
    for bar in m1:
        by_date.setdefault(bar.trading_date, []).append(bar)
    out: list[Bar] = []
    for trading_date, bars in sorted(by_date.items()):
        out.append(
            Bar(
                start_ns=min(b.start_ns for b in bars),
                end_ns=max(b.end_ns for b in bars),
                o=min(bars, key=lambda b: b.start_ns).o,
                h=max(b.h for b in bars),
                lo=min(b.lo for b in bars),
                c=max(bars, key=lambda b: b.end_ns).c,
                volume=sum(b.volume for b in bars),
                trading_date=trading_date,
                instrument_id=max(bars, key=lambda b: b.end_ns).instrument_id,
                quality="derived",
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Params:
    """Every one of these is an `unresolved_decision` given a committed value."""

    break_ticks: int = 4  # close beyond the level by this much = a break
    retest_bars: int = 6  # 5m bars after the break in which a retest must occur
    retest_tol_ticks: int = 8  # how close price must return to the level
    stop_buffer_ticks: int = 4  # beyond the retest extreme
    entry_offset_ticks: int = 1  # stop-entry beyond the retest bar extreme
    r_multiple: float = 2.0  # target distance as a multiple of risk
    min_stop_ticks: int = 8  # reject setups whose stop is implausibly tight
    # NOTE: an early run set this to 120 and it silently discarded 83% of
    # qualifying setups -- a sweep-and-reclaim bar is by construction a WIDE
    # bar (observed retest-bar ranges 121-553 ticks), and NQ near 26,000 makes
    # tick-denominated stops much larger than intuition from lower index
    # levels. Set wide enough not to bind; it is a reported sensitivity axis.
    max_stop_ticks: int = 400
    entry_expiry_min: int = 30  # cancel unfilled entry after this many 1m bars
    entry_slippage_ticks: int = 1
    exit_slippage_ticks: int = 1
    fees_ticks: int = 1  # round turn
    target_confirm_ticks: int = 1  # target must trade THROUGH by this much
    session_start_ct: tuple[int, int] = (8, 30)
    session_end_ct: tuple[int, int] = (14, 30)


@dataclass
class Trade:
    direction: str
    level: int
    signal_ns: int
    entry_ns: int | None = None
    entry: int | None = None
    stop: int | None = None
    target: int | None = None
    exit_ns: int | None = None
    exit: int | None = None
    outcome: str = "pending"
    risk_ticks: int = 0
    pnl_ticks: int = 0
    r: float = 0.0
    trading_date: str = ""


@dataclass
class Result:
    trades: list[Trade] = field(default_factory=list)
    cancelled: int = 0
    expired: int = 0
    unresolved_roll: int = 0
    setups_seen: int = 0


def in_session(ns: int, p: Params) -> bool:
    t = to_ct(ns)
    start = t.replace(
        hour=p.session_start_ct[0], minute=p.session_start_ct[1], second=0, microsecond=0
    )
    end = t.replace(hour=p.session_end_ct[0], minute=p.session_end_ct[1], second=0, microsecond=0)
    return start <= t <= end


def flatten_ns_for(trading_date: str, minute_index: dict[str, list[Bar]]) -> int | None:
    """End_ns of the 1m bar whose end converts to 13:58:00 Pacific (ADR-0012)."""
    for bar in minute_index.get(trading_date, ()):
        pt = to_pt(bar.end_ns)
        if (pt.hour, pt.minute, pt.second) == (13, 58, 0):
            return bar.end_ns
    return None


def simulate_entry_and_exit(
    trade: Trade,
    minutes: list[Bar],
    start_idx: int,
    p: Params,
    flatten_ns: int | None,
) -> str:
    """ADR-0012 fill model on complete 1m bars strictly after the signal."""
    long = trade.direction == "long"
    entry_level = trade.entry
    assert entry_level is not None
    filled_idx: int | None = None
    signal_instrument = minutes[start_idx].instrument_id if start_idx < len(minutes) else None

    # --- entry: planned level, range touch, strictly after the signal ---
    for i in range(start_idx, min(start_idx + p.entry_expiry_min, len(minutes))):
        bar = minutes[i]
        if bar.instrument_id != signal_instrument:
            return "unresolved_roll"
        if flatten_ns is not None and bar.end_ns > flatten_ns:
            return "expired_cutoff"
        touched = bar.h >= entry_level if long else bar.lo <= entry_level
        if touched:
            # gap through the entry stop fills at the worse open
            if long:
                base = max(entry_level, bar.o)
                trade.entry = base + p.entry_slippage_ticks
            else:
                base = min(entry_level, bar.o)
                trade.entry = base - p.entry_slippage_ticks
            trade.entry_ns = bar.end_ns
            filled_idx = i
            break
    if filled_idx is None:
        return "expired_unfilled"

    # risk and target are recomputed off the ACTUAL fill (planned risk was
    # already range-checked before any fill was simulated)
    entry = trade.entry
    stop = trade.stop
    assert entry is not None and stop is not None
    risk = abs(entry - stop)
    trade.risk_ticks = risk
    trade.target = (
        entry + round(p.r_multiple * risk) if long else entry - round(p.r_multiple * risk)
    )

    # --- exit: stop wins ambiguous bars; entry-bar target ignored ---
    for i in range(filled_idx, len(minutes)):
        bar = minutes[i]
        if bar.instrument_id != signal_instrument:
            trade.exit_ns, trade.exit = bar.start_ns, bar.o
            return "unresolved_roll"

        stop_hit = bar.lo <= stop if long else bar.h >= stop
        tgt = trade.target
        assert tgt is not None
        target_hit = (
            bar.h >= tgt + p.target_confirm_ticks
            if long
            else bar.lo <= tgt - p.target_confirm_ticks
        )
        if i == filled_idx:
            target_hit = False  # entry-bar target ignored unless confirmed later

        if stop_hit:
            # gap through the stop fills at the worse open
            base = min(stop, bar.o) if long else max(stop, bar.o)
            trade.exit = base - p.exit_slippage_ticks if long else base + p.exit_slippage_ticks
            trade.exit_ns = bar.end_ns
            return "stop"
        if target_hit:
            trade.exit = tgt  # no favorable gap improvement
            trade.exit_ns = bar.end_ns
            return "target"
        if flatten_ns is not None and bar.end_ns >= flatten_ns:
            trade.exit = bar.c
            trade.exit_ns = bar.end_ns
            return "flatten"
    return "unresolved_no_data"


def run(p: Params, m1: list[Bar], m5: list[Bar], daily: list[Bar]) -> Result:
    res = Result()
    minute_index: dict[str, list[Bar]] = {}
    for bar in m1:
        minute_index.setdefault(bar.trading_date, []).append(bar)

    prev_level: dict[str, tuple[int, int]] = {}
    ordered_days = sorted({b.trading_date for b in daily})
    daily_by_date = {b.trading_date: b for b in daily}
    for i in range(1, len(ordered_days)):
        prior = daily_by_date[ordered_days[i - 1]]
        prev_level[ordered_days[i]] = (prior.h, prior.lo)

    five_by_date: dict[str, list[Bar]] = {}
    for bar in m5:
        five_by_date.setdefault(bar.trading_date, []).append(bar)

    for trading_date, bars5 in sorted(five_by_date.items()):
        levels = prev_level.get(trading_date)
        if levels is None:
            continue
        pdh, pdl = levels
        minutes = minute_index.get(trading_date, [])
        if not minutes:
            continue
        flatten_ns = flatten_ns_for(trading_date, minute_index)
        used: set[str] = set()

        for direction, level in (("long", pdh), ("short", pdl)):
            broke_idx: int | None = None
            for idx, bar in enumerate(bars5):
                if direction in used:
                    break
                broke = (
                    bar.c >= level + p.break_ticks
                    if direction == "long"
                    else bar.c <= level - p.break_ticks
                )
                if broke_idx is not None and idx - broke_idx > p.retest_bars:
                    broke_idx = None  # window expired; this bar may re-break below
                if broke_idx is None:
                    if broke:
                        broke_idx = idx
                    continue
                retest = (
                    bar.lo <= level + p.retest_tol_ticks and bar.c >= level
                    if direction == "long"
                    else bar.h >= level - p.retest_tol_ticks and bar.c <= level
                )
                if not retest:
                    continue
                if not in_session(bar.end_ns, p):
                    continue
                trade = Trade(
                    direction=direction,
                    level=level,
                    signal_ns=bar.end_ns,
                    trading_date=trading_date,
                )
                if direction == "long":
                    trade.entry = bar.h + p.entry_offset_ticks
                    trade.stop = bar.lo - p.stop_buffer_ticks
                else:
                    trade.entry = bar.lo - p.entry_offset_ticks
                    trade.stop = bar.h + p.stop_buffer_ticks

                # planned risk gates the SETUP, before any fill is simulated
                planned_risk = abs(trade.entry - trade.stop)
                if planned_risk < p.min_stop_ticks or planned_risk > p.max_stop_ticks:
                    broke_idx = None
                    continue

                res.setups_seen += 1
                used.add(direction)
                start_idx = next(
                    (k for k, mb in enumerate(minutes) if mb.start_ns >= bar.end_ns), None
                )
                if start_idx is None:
                    res.expired += 1
                    break
                outcome = simulate_entry_and_exit(trade, minutes, start_idx, p, flatten_ns)
                trade.outcome = outcome
                if outcome in {"stop", "target", "flatten"}:
                    gross = (
                        trade.exit - trade.entry
                        if direction == "long"
                        else trade.entry - trade.exit
                    )
                    trade.pnl_ticks = gross - p.fees_ticks
                    trade.r = trade.pnl_ticks / trade.risk_ticks if trade.risk_ticks else 0.0
                    res.trades.append(trade)
                elif outcome == "unresolved_roll":
                    res.unresolved_roll += 1
                else:
                    res.cancelled += 1
                break
    return res


def r_stats(rs: list[float], iters: int = 10_000, seed: int = 20260726) -> dict:
    """Mean R with a standard error, t-stat, and a bootstrap 95% CI.

    ADR-0021 sec E: a point estimate with no error bar is not a result. With a
    2R target, per-trade R has sd ~1.4, so n=14 gives se ~0.37 -- an
    expectancy of +0.28 is inside the noise and must be reported as such.
    """
    import random

    n = len(rs)
    if n < 2:
        return {
            "n": n,
            "mean_r": round(rs[0], 4) if rs else None,
            "se": None,
            "t": None,
            "ci95": None,
        }
    mean = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    se = sd / (n**0.5)
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(rs, k=n)) for _ in range(iters))
    lo = means[int(0.025 * iters)]
    hi = means[int(0.975 * iters)]
    return {
        "n": n,
        "mean_r": round(mean, 4),
        "sd_r": round(sd, 4),
        "se": round(se, 4),
        "t": round(mean / se, 3) if se else None,
        "ci95": [round(lo, 4), round(hi, 4)],
        "ci95_excludes_zero": bool(lo > 0 or hi < 0),
    }


def null_random_entry(
    res: Result,
    m1: list[Bar],
    p: Params,
    iters: int = 400,
    seed: int = 20260726,
) -> dict:
    """Reference class (ADR-0021 sec E9): same geometry, same day, random entry time.

    For each real trade, take a trade in the SAME direction on the SAME trading
    date with the SAME risk in ticks and the same R multiple, entered at a
    randomly chosen in-session 1m bar. If break-and-retest carries no timing
    information, the real result should sit inside this distribution.
    """
    import random

    rng = random.Random(seed)
    minute_index: dict[str, list[Bar]] = {}
    for bar in m1:
        minute_index.setdefault(bar.trading_date, []).append(bar)

    observed = statistics.fmean([t.r for t in res.trades]) if res.trades else 0.0
    null_means: list[float] = []
    for _ in range(iters):
        rs: list[float] = []
        for real in res.trades:
            minutes = minute_index.get(real.trading_date, [])
            eligible = [i for i, b in enumerate(minutes) if in_session(b.end_ns, p)]
            if not eligible:
                continue
            idx = rng.choice(eligible)
            bar = minutes[idx]
            long = real.direction == "long"
            entry = bar.c + p.entry_slippage_ticks if long else bar.c - p.entry_slippage_ticks
            risk = real.risk_ticks
            stop = entry - risk if long else entry + risk
            target = (
                entry + round(p.r_multiple * risk) if long else entry - round(p.r_multiple * risk)
            )
            flatten_ns = flatten_ns_for(real.trading_date, minute_index)
            pnl = None
            for j in range(idx, len(minutes)):
                b = minutes[j]
                if b.instrument_id != bar.instrument_id:
                    break
                stop_hit = b.lo <= stop if long else b.h >= stop
                tgt_hit = (
                    b.h >= target + p.target_confirm_ticks
                    if long
                    else b.lo <= target - p.target_confirm_ticks
                )
                if j == idx:
                    tgt_hit = False
                if stop_hit:
                    base = min(stop, b.o) if long else max(stop, b.o)
                    ex = base - p.exit_slippage_ticks if long else base + p.exit_slippage_ticks
                    pnl = (ex - entry if long else entry - ex) - p.fees_ticks
                    break
                if tgt_hit:
                    pnl = (target - entry if long else entry - target) - p.fees_ticks
                    break
                if flatten_ns is not None and b.end_ns >= flatten_ns:
                    pnl = (b.c - entry if long else entry - b.c) - p.fees_ticks
                    break
            if pnl is not None and risk:
                rs.append(pnl / risk)
        if rs:
            null_means.append(statistics.fmean(rs))
    if not null_means:
        return {"iters": 0}
    null_means.sort()
    better = sum(1 for m in null_means if m >= observed)
    return {
        "iters": len(null_means),
        "observed_mean_r": round(observed, 4),
        "null_mean_r": round(statistics.fmean(null_means), 4),
        "null_p05": round(null_means[int(0.05 * len(null_means))], 4),
        "null_p95": round(null_means[int(0.95 * len(null_means))], 4),
        "p_value_one_sided": round(better / len(null_means), 4),
    }


def metrics(res: Result) -> dict:
    trades = res.trades
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    rs = [t.r for t in trades]
    ticks = [t.pnl_ticks for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return {
        "trades": n,
        "win_rate": round(len(wins) / n, 4),
        "expectancy_r": round(statistics.fmean(rs), 4),
        "expectancy_ticks": round(statistics.fmean(ticks), 3),
        "total_r": round(sum(rs), 2),
        "avg_win_r": round(statistics.fmean(wins), 3) if wins else None,
        "avg_loss_r": round(statistics.fmean(losses), 3) if losses else None,
        "max_drawdown_r": round(max_dd, 2),
        "median_risk_ticks": statistics.median([t.risk_ticks for t in trades]),
        "outcomes": {
            k: sum(1 for t in trades if t.outcome == k) for k in ("stop", "target", "flatten")
        },
        "setups_seen": res.setups_seen,
        "cancelled_or_unfilled": res.cancelled,
        "unresolved_roll": res.unresolved_roll,
        "stats": r_stats(rs),
    }
