"""Moving averages — the MA pairs the chart carries throughout the sequence.

Source: `docs/RULEBOOK.md` §1.1, §1.2, decision **D-1**. The chart carries **10 and 20 SMA** (the
pair that runs the sequence) and **50 and 200 SMA** (the higher-timeframe trend filter, §7.1).
Simple moving averages of the **close**, computed on the frame given — this module never resamples;
the sequence runs on the setup timeframe's own MAs (**D-7**, §9).

**Implementation convention, not named in the material.** §1.1/§1.2 say "10 and 20 SMA" without
naming the input series; this module uses **close**, the universal default, not an invented
predicate — but it is the same class of unpinned choice as `candles.py`'s exact-equality
convention.

Pure functions over bars: no disk I/O, no network, no clock reads.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

SEQUENCE_PERIODS = (10, 20)  # the pair that runs the sequence (D-1)
TREND_PERIODS = (50, 200)  # the gating pair (D-1, §7.1)
SMA_PERIODS = (10, 20, 50, 200)


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average of `close` over `period` bars.

    Warm-up stays **NaN** — never backfilled, never `min_periods=1`. A partial-window average is a
    different number wearing the same name. `period` longer than `close` is legal and yields an
    all-NaN series; `period < 1` raises.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return close.rolling(period, min_periods=period).mean()


def add_smas(bars: pd.DataFrame, periods: Sequence[int] = SMA_PERIODS) -> pd.DataFrame:
    """Return a copy of `bars` with an `sma_{period}` column added for each of `periods`."""
    out = bars.copy()
    for period in periods:
        out[f"sma_{period}"] = sma(bars["close"], period)
    return out


__all__ = [
    "SEQUENCE_PERIODS",
    "SMA_PERIODS",
    "TREND_PERIODS",
    "add_smas",
    "sma",
]
