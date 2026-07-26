"""Run the break-and-retest probe and report per ADR-0021 (no cherry-picked cell)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bnr_backtest import (
    Params,
    derive_daily,
    load_bars,
    metrics,
    null_random_entry,
    run,
)


def main() -> int:
    m1 = load_bars("1m")
    m5 = load_bars("5m")
    daily = derive_daily(m1)
    dates = sorted({b.trading_date for b in m1})
    print(
        f"data: 1m bars={len(m1):,}  5m bars={len(m5):,}  trading dates={len(dates)} "
        f"({dates[0]} .. {dates[-1]})",
        flush=True,
    )

    # ADR-0021 sec A: data health BEFORE any metric.
    from collections import Counter

    per_day = Counter(b.trading_date for b in m1)
    counts = sorted(per_day.values())
    quality = Counter(b.quality for b in m1)
    short_days = [d for d, n in sorted(per_day.items()) if n < 1000]
    print(
        f"health: 1m bar quality={dict(quality)}  bars/day median={counts[len(counts) // 2]} "
        f"min={counts[0]} max={counts[-1]}"
    )
    print(f"health: short days (<1000 1m bars, i.e. holiday/half-session): {short_days}")
    print(f"health: instrument_ids seen (roll): {sorted({b.instrument_id for b in m1})}")

    base = Params()
    res = run(base, m1, m5, daily)
    print("\n=== BASELINE PARAMETER SET (declared up front, not fitted) ===")
    print(json.dumps(asdict(base), default=str, sort_keys=True))
    print(json.dumps(metrics(res), indent=2, sort_keys=True))

    # Pre-declared sensitivity grid. Reported in full; no cell is selected.
    print("\n=== SENSITIVITY GRID (all cells reported; ADR-0011 forbids selecting one) ===")
    print(
        f"{'variant':38s} {'trades':>7s} {'win%':>6s} {'E[R]':>8s} "
        f"{'E[ticks]':>9s} {'totR':>8s} {'maxDD_R':>8s}"
    )
    grid: list[tuple[str, Params]] = [("baseline", base)]
    for value in (2, 4, 8):
        grid.append((f"break_ticks={value}", replace(base, break_ticks=value)))
    for value in (4, 8, 16):
        grid.append((f"retest_tol_ticks={value}", replace(base, retest_tol_ticks=value)))
    for value in (1.0, 1.5, 2.0, 3.0):
        grid.append((f"r_multiple={value}", replace(base, r_multiple=value)))
    for value in (4, 8, 12):
        grid.append((f"retest_bars={value}", replace(base, retest_bars=value)))
    for value in (2, 4, 8):
        grid.append((f"stop_buffer_ticks={value}", replace(base, stop_buffer_ticks=value)))
    for value in (120, 200, 400, 800):
        grid.append((f"max_stop_ticks={value}", replace(base, max_stop_ticks=value)))
    grid.append(
        ("session=globex 24h", replace(base, session_start_ct=(0, 0), session_end_ct=(23, 59)))
    )
    grid.append(
        (
            "session=RTH cash 08:30-15:00",
            replace(base, session_start_ct=(8, 30), session_end_ct=(15, 0)),
        )
    )
    grid.append(
        (
            "costs=0 (unrealizable)",
            replace(base, entry_slippage_ticks=0, exit_slippage_ticks=0, fees_ticks=0),
        )
    )
    grid.append(
        ("costs=2x", replace(base, entry_slippage_ticks=2, exit_slippage_ticks=2, fees_ticks=2))
    )
    grid.append(
        (
            "costs=4x (wide slippage)",
            replace(base, entry_slippage_ticks=4, exit_slippage_ticks=4, fees_ticks=2),
        )
    )

    rows = []
    for name, params in grid:
        m = metrics(run(params, m1, m5, daily))
        rows.append((name, m))
        if m.get("trades", 0) == 0:
            print(f"{name:38s} {'0':>7s}")
            continue
        print(
            f"{name:38s} {m['trades']:7d} {m['win_rate'] * 100:5.1f}% {m['expectancy_r']:8.4f} "
            f"{m['expectancy_ticks']:9.2f} {m['total_r']:8.2f} {m['max_drawdown_r']:8.2f}"
        )

    # ADR-0021 sec 7: disaggregate before interpreting; sec 8: n<20 -> counts only.
    print("\n=== DISAGGREGATION (pooled numbers hide disjoint strata) ===")
    for label, key in (
        ("direction", lambda t: t.direction),
        ("month", lambda t: t.trading_date[:7]),
    ):
        print(f"-- by {label}")
        groups: dict[str, list] = {}
        for t in res.trades:
            groups.setdefault(key(t), []).append(t)
        for name, ts in sorted(groups.items()):
            rs = [t.r for t in ts]
            note = "  [n<20: counts only, no rate]" if len(ts) < 20 else ""
            wins = sum(1 for r in rs if r > 0)
            print(
                f"   {name:10s} n={len(ts):4d} wins={wins:3d} losses={len(ts) - wins:3d} "
                f"sum_R={sum(rs):+8.2f} mean_R={sum(rs) / len(ts):+.4f}{note}"
            )

    print("\n=== REFERENCE CLASS: same day, same direction, same risk, RANDOM entry time ===")
    null = null_random_entry(res, m1, base)
    print(json.dumps(null, indent=2, sort_keys=True))
    print(
        "\nRead this first: if the observed mean sits inside the null band, the setup's\n"
        "TIMING carries no information and the result is 2R geometry plus drift."
    )

    out = Path(__file__).parent / "probe_results.json"
    out.write_text(
        json.dumps({"rows": [{"variant": n, **m} for n, m in rows]}, indent=2, sort_keys=True)
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
