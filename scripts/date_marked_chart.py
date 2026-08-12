"""Date a marked chart by matching its printed right-axis values against our own SMAs.

Every marked chart in `docs/RULEBOOK.md` §10 is a TradingView screenshot whose right price axis
prints the current value of each plotted indicator to two decimals. Four such values are a strong
fingerprint: on the fixtures dated so far the correct bar's worst-field error is 0.08-3.23 points
while the next-best bar in a two-month window is 5-32 points away.

**The chart does not say which label belongs to which moving average**, so this matches the sorted
multiset of four values rather than an assignment. That also means it does not assume the 10/20/50/
200 pairing — it only assumes those four periods are the ones plotted.

Usage::

    python scripts/date_marked_chart.py 28620.18 28580.09 28540.74 28499.84
    python scripts/date_marked_chart.py --symbol NQ --timeframe 5m --from 2026-06-01 <values...>

Two things this script is not:

* **Not a labeller.** It identifies the *bar the screenshot was taken on*. Which candle carries a
  Step 1 mark is read off the chart — see `docs/PHASE3.md` section 2.
* **Not evidence on its own.** `docs/PHASE3.md` requires two independent agreements before a
  fixture is called dated. This supplies one of them; a printed daily/weekly level, an on-screen
  clock or a day separator supplies the other. A single sharp minimum is a candidate, not a date.

Why this works now and did not before: the fixtures are July-August 2026 sessions, and until
`scripts/merge_signal_bars.py` extended the spine the bars simply were not in the series. The
earlier failure was read as the *method* being wrong; it was the *range* --
`claude_memories/negative-result-over-an-incomplete-range.md`.

The input series is the **close**, and that is no longer a convention — see the module docstring in
`stoic/indicators.py`. On `NQ3` the close reproduces all four printed values to within 0.08 points
while `hl2`, `hlc3` and `ohlc4` are 9-13 points out.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from stoic.bars import load_bars  # noqa: E402

DEFAULT_PERIODS = (10, 20, 50, 200)
ET = "America/New_York"


def sma_frame(symbol: str, timeframe: str, periods: tuple[int, ...]) -> pd.DataFrame:
    """One column per period: the simple moving average of the close on `timeframe`."""
    close = load_bars(symbol, timeframe)["close"]
    return pd.DataFrame({n: close.rolling(n).mean() for n in periods})


def rank_bars(smas: pd.DataFrame, printed: list[float]) -> pd.Series:
    """Worst-field absolute error per bar, comparing sorted SMAs to the sorted printed values."""
    ordered = smas.apply(sorted, axis=1, result_type="expand")
    return (ordered - pd.Series(sorted(printed)).to_numpy()).abs().max(axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("values", type=float, nargs="+", help="printed right-axis values")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--periods", type=int, nargs="+", default=list(DEFAULT_PERIODS))
    parser.add_argument("--from", dest="start", default="2026-06-01", help="scan from this date")
    parser.add_argument("--top", type=int, default=5, help="how many candidate bars to print")
    args = parser.parse_args()

    if len(args.values) != len(args.periods):
        print(
            f"got {len(args.values)} values but {len(args.periods)} periods — "
            "supply one printed value per plotted moving average",
            file=sys.stderr,
        )
        return 1

    smas = sma_frame(args.symbol, args.timeframe, tuple(args.periods)).loc[args.start :]
    err = rank_bars(smas, args.values)

    print(f"printed : {sorted(args.values)}")
    print(f"scanned : {args.symbol} {args.timeframe}, {len(smas):,} bars from {args.start}")
    print(f"periods : {args.periods}\n")
    for ts, worst in err.nsmallest(args.top).items():
        ours = [round(v, 2) for v in sorted(smas.loc[ts])]
        print(f"  {ts}  ET {ts.tz_convert(ET):%Y-%m-%d %H:%M}  worst|Δ| {worst:8.2f}   {ours}")

    print(
        "\nA date needs a SECOND, independent agreement (docs/PHASE3.md section 2): a printed "
        "daily/weekly level, an on-screen clock, or a day separator."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
