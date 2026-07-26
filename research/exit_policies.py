"""Can a different profit target rescue the setup? Ceiling test + policy sweep.

The question "maybe the target needs modification" cannot be answered by trying
targets until one looks good -- that is optimisation, which ADR-0011 forbids,
and with n=46 it would fit noise. It is answered by asking whether the setup's
entries carry information that ANY exit policy could monetise.

Three tests, all comparing real entries against the random-entry null under
IDENTICAL treatment (ADR-0021 sec E9). Testing a policy only on real trades
measures the policy, not the setup.

1. CEILING (oracle). For each trade, walk forward from the fill and record the
   maximum favourable excursion reached BEFORE the stop is hit -- the best price
   any exit rule could ever have taken. If the real ceiling is not above the
   null ceiling, no policy monetising AVERAGE excursion can help. It does NOT
   rule out policies exploiting distribution SHAPE; see test 3.

2. POLICY SWEEP. Pre-declared exit policies, each run on real and null entries.
   Reported in full; no policy is selected.

3. SHAPE. Mean parity can hide differences that cancel. Each shape feature of
   the real MFE distribution is compared against the null's per-iteration
   distribution of the same feature. This is where the open lead lives.

Run: .venv/bin/python research/exit_policies.py
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bnr_backtest import (
    Bar,
    Params,
    derive_daily,
    flatten_ns_for,
    in_session,
    load_bars,
    run,
)

SEED = 20260726


def walk(
    entry: int,
    stop: int,
    long: bool,
    minutes: list[Bar],
    start: int,
    flatten_ns: int | None,
    p: Params,
) -> dict:
    """Walk 1m bars from the fill; return the path facts every policy needs.

    Stop-wins-ambiguous is preserved (ADR-0012): the walk terminates on the stop
    bar, so MFE is capped at what was reachable before invalidation.
    """
    risk = abs(entry - stop)
    mfe = 0
    mae = 0
    mfe_at = None
    bars_held = 0
    instrument = minutes[start].instrument_id
    ended = "open"
    last_close = entry
    for i in range(start, len(minutes)):
        b = minutes[i]
        if b.instrument_id != instrument:
            ended = "roll"
            break
        bars_held = i - start + 1
        fav = (b.h - entry) if long else (entry - b.lo)
        adv = (entry - b.lo) if long else (b.h - entry)
        if fav > mfe:
            mfe, mfe_at = fav, bars_held
        mae = max(mae, adv)
        last_close = b.c
        stop_hit = b.lo <= stop if long else b.h >= stop
        if stop_hit:
            ended = "stop"
            break
        if flatten_ns is not None and b.end_ns >= flatten_ns:
            ended = "flatten"
            break
    return {
        "risk": risk,
        "mfe_r": mfe / risk if risk else 0.0,
        "mae_r": mae / risk if risk else 0.0,
        "mfe_at_bar": mfe_at,
        "bars_held": bars_held,
        "ended": ended,
        "final_r": ((last_close - entry) if long else (entry - last_close)) / risk if risk else 0.0,
    }


def apply_policy(path: dict, policy: str, p: Params) -> float | None:
    """Net R under one exit policy, from the walked path. Fees applied once."""
    fee_r = p.fees_ticks / path["risk"] if path["risk"] else 0.0
    mfe, ended, final = path["mfe_r"], path["ended"], path["final_r"]
    if ended == "roll":
        return None

    if policy.startswith("fixed_"):
        target = float(policy.split("_")[1])
        if mfe >= target:
            return target - fee_r
        return (-1.0 if ended == "stop" else final) - fee_r

    if policy == "ceiling_oracle":
        # Unrealisable upper bound: take the exact high-water mark.
        return max(mfe, -1.0 if ended == "stop" else final) - fee_r

    if policy == "runner_flatten":
        # No target at all: stop or session flatten.
        return (-1.0 if ended == "stop" else final) - fee_r

    if policy == "breakeven_at_1R":
        # Once +1R is seen, the stop moves to entry: worst case is ~0, not -1.
        if mfe >= 2.0:
            return 2.0 - fee_r
        if mfe >= 1.0:
            return 0.0 - fee_r
        return (-1.0 if ended == "stop" else final) - fee_r

    if policy == "half_at_1R_rest_2R":
        if mfe >= 1.0:
            rest = 2.0 if mfe >= 2.0 else (0.0 if ended == "stop" else final)
            return 0.5 * 1.0 + 0.5 * rest - fee_r
        return (-1.0 if ended == "stop" else final) - fee_r

    raise ValueError(policy)


POLICIES = (
    "fixed_1.0",
    "fixed_1.5",
    "fixed_2.0",
    "fixed_3.0",
    "runner_flatten",
    "breakeven_at_1R",
    "half_at_1R_rest_2R",
    "ceiling_oracle",
)


def main() -> int:
    m1 = load_bars("1m")
    m5 = load_bars("5m")
    daily = derive_daily(m1)
    p = Params()
    res = run(p, m1, m5, daily)

    idx: dict[str, list[Bar]] = {}
    for b in m1:
        idx.setdefault(b.trading_date, []).append(b)

    # --- real paths -------------------------------------------------------
    real: list[dict] = []
    for t in res.trades:
        minutes = idx[t.trading_date]
        start = next((i for i, b in enumerate(minutes) if b.end_ns >= t.entry_ns), None)
        if start is None:
            continue
        real.append(
            walk(
                t.entry,
                t.stop,
                t.direction == "long",
                minutes,
                start,
                flatten_ns_for(t.trading_date, idx),
                p,
            )
        )

    # --- null paths: same day, same direction, same risk, random entry -----
    rng = random.Random(SEED)
    ITERS = 200
    null_by_policy: dict[str, list[float]] = {k: [] for k in POLICIES}
    null_mfe: list[float] = []
    null_feats: list[dict[str, float]] = []
    for _ in range(ITERS):
        paths = []
        for t in res.trades:
            minutes = idx[t.trading_date]
            eligible = [i for i, b in enumerate(minutes) if in_session(b.end_ns, p)]
            if not eligible:
                continue
            i = rng.choice(eligible)
            b = minutes[i]
            long = t.direction == "long"
            entry = b.c + p.entry_slippage_ticks if long else b.c - p.entry_slippage_ticks
            stop = entry - t.risk_ticks if long else entry + t.risk_ticks
            paths.append(
                walk(entry, stop, long, minutes, i, flatten_ns_for(t.trading_date, idx), p)
            )
        null_mfe.extend(x["mfe_r"] for x in paths)
        _v = sorted(x["mfe_r"] for x in paths)
        null_feats.append(
            {
                "mean": statistics.fmean(_v),
                "p50": _v[len(_v) // 2],
                "p90": _v[int(0.9 * len(_v))],
                "ge1": sum(1 for x in _v if x >= 1.0) / len(_v),
                "ge2": sum(1 for x in _v if x >= 2.0) / len(_v),
                "ge3": sum(1 for x in _v if x >= 3.0) / len(_v),
            }
        )
        for pol in POLICIES:
            vals = [v for x in paths if (v := apply_policy(x, pol, p)) is not None]
            if vals:
                null_by_policy[pol].append(statistics.fmean(vals))

    # --- report -----------------------------------------------------------
    print(f"real trades n={len(real)}   null iterations={ITERS}\n")

    rm = sorted(x["mfe_r"] for x in real)
    nm = sorted(null_mfe)

    def q(xs: list[float], f: float) -> float:
        return xs[min(int(f * len(xs)), len(xs) - 1)]

    print("=== TEST 1: CEILING -- best excursion reachable before the stop ===")
    print(
        f"{'':10s} {'n':>6s} {'mean':>8s} {'p50':>8s} "
        f"{'p75':>8s} {'p90':>8s} {'>=1R':>7s} {'>=2R':>7s}"
    )
    for name, xs in (("real", rm), ("null", nm)):
        print(
            f"{name:10s} {len(xs):6d} {statistics.fmean(xs):8.3f} {q(xs, 0.50):8.3f} "
            f"{q(xs, 0.75):8.3f} {q(xs, 0.90):8.3f} "
            f"{sum(1 for x in xs if x >= 1.0) / len(xs):6.1%} "
            f"{sum(1 for x in xs if x >= 2.0) / len(xs):6.1%}"
        )
    print(
        "\nThe MEAN ceiling bounds any policy that monetises AVERAGE excursion.\n"
        "It does not bound policies that exploit distribution SHAPE -- see test 3."
    )

    # --- TEST 3: shape, not just mean -------------------------------------
    # The mean can match while the distributions differ in opposite directions
    # that cancel. Compare each shape feature against the null's per-iteration
    # distribution of that same feature (matched n).
    feats = ("mean", "p50", "p90", "ge1", "ge2", "ge3")

    def features(xs: list[float]) -> dict[str, float]:
        s = sorted(xs)
        return {
            "mean": statistics.fmean(s),
            "p50": q(s, 0.50),
            "p90": q(s, 0.90),
            "ge1": sum(1 for x in s if x >= 1.0) / len(s),
            "ge2": sum(1 for x in s if x >= 2.0) / len(s),
            "ge3": sum(1 for x in s if x >= 3.0) / len(s),
        }

    obs = features(rm)
    print("\n=== TEST 3: CEILING SHAPE (mean parity can hide offsetting differences) ===")
    print(
        f"{'feature':8s} {'real':>8s} {'null mean':>10s} "
        f"{'p05':>8s} {'p95':>8s} {'p(null>=real)':>14s}"
    )
    for k in feats:
        nd = sorted(f[k] for f in null_feats)
        pv = sum(1 for x in nd if x >= obs[k]) / len(nd)
        star = " *" if pv < 0.05 else ""
        print(
            f"{k:8s} {obs[k]:8.3f} {statistics.fmean(nd):10.3f} "
            f"{q(nd, 0.05):8.3f} {q(nd, 0.95):8.3f} {pv:14.3f}{star}"
        )
    print(
        "\n* = real outside the null's upper 5%. NOTHING here is significant at\n"
        "n=46, but the direction is consistent: real reaches the 1R-2R band more\n"
        "reliably while the null has the fatter extreme tail. That is a LEAD to\n"
        "retest at larger n, not a result -- and it is why 'no exit policy can\n"
        "help' would be an overstatement of test 1."
    )

    print("\n=== TEST 2: POLICY SWEEP (real vs null under identical treatment) ===")
    print(
        f"{'policy':22s} {'real E[R]':>10s} {'null E[R]':>10s} "
        f"{'null p05':>9s} {'null p95':>9s} {'p':>7s}"
    )
    for pol in POLICIES:
        vals = [v for x in real if (v := apply_policy(x, pol, p)) is not None]
        obs = statistics.fmean(vals)
        nulls = sorted(null_by_policy[pol])
        better = sum(1 for x in nulls if x >= obs) / len(nulls)
        flag = "" if better > 0.05 else "  <-- outside null"
        print(
            f"{pol:22s} {obs:10.4f} {statistics.fmean(nulls):10.4f} "
            f"{q(nulls, 0.05):9.4f} {q(nulls, 0.95):9.4f} {better:7.3f}{flag}"
        )
    print(
        "\nNo policy is selected. ADR-0011 forbids an optimizer; picking the best\n"
        "row here would be fitting noise at n=46."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
