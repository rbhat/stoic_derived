"""Higher-timeframe levels: previous day/week levels and month-close extremes.

Source: `docs/RULEBOOK.md` §7.3, decision **D-8**. Pure over frames produced by
`stoic.bars.resample(bars, "1D")` and `resample(bars, "1W")` — this module never calls
`load_bars` and never resamples. The `1D` frame carries a `session_date` column and is indexed by
that day's `session_open_utc`; the `1W` frame carries `week_start` and is indexed by the week's
first `session_open_utc`. The week boundary (ISO week over CME trading days) is settled by
`stoic.bars._resample_weekly` — this module does not introduce a second one.

**Known limitation, documented here rather than fixed:** session `2025-11-28` has a ~645-minute
hole in `data/historical/{NQ,ES}_1m.parquet` (see
`claude_memories/historical-bars-2025-11-28-outage.md`). A level derived from that session is
derived from partial data. These functions cannot detect that and do not try to; the caller
(Phase 3 / Phase 6) is responsible for excluding or flagging the date.

**Same class, at the boundary of history rather than a hole in the middle:** ES/NQ daily history
begins 2019-06-10, so June 2019 has only 15 sessions, and the ~45 sessions per symbol that follow
read `hcom_m1`/`hcom_m2` off that truncated month as if it were complete — no NaN, no flag. The
same applies to `pwc`/`pwh`/`plow` for a frame that starts mid-week. These functions cannot detect
either case and do not try to; the caller's exclusion list needs to cover it too.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

MONTHS_LOOKBACK = 3  # D-8: three months (month-to-date plus two prior), what the Stoic
# indicator supplies. Not exposed as a `months=` knob -- a configurable lookback would be an
# invented parameter.


def previous_day_levels(daily: pd.DataFrame) -> pd.DataFrame:
    """PDH/PDL/PDC — previous day high/low/close (§7.3, `OTV @ 35:29`, `CST @ 04:49`).

    Positional `shift(1)` over `daily` sorted by `session_date`. First session -> NaN.

    Returns a frame indexed by `session_date` with columns `pdh`, `pdl`, `pdc`.
    """
    ordered = daily.sort_values("session_date")
    return pd.DataFrame(
        {
            "pdh": ordered["high"].shift(1).to_numpy(),
            "pdl": ordered["low"].shift(1).to_numpy(),
            "pdc": ordered["close"].shift(1).to_numpy(),
        },
        index=pd.Index(ordered["session_date"].to_numpy(), name="session_date"),
    )


def previous_week_levels(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """PWC / PWH / PLOW — previous weekly close, and previous week's raw high/low (§7.3,
    `CST @ 28:12`, `PTBV @ 00:27:42`).

    `shift(1)` over `weekly` sorted by its own index, then each `session_date` is mapped onto its
    own ISO week's row. A missing week (holiday) means `shift(1)` yields the previous **present**
    week: `weekly` only has rows for weeks that actually traded, so shifting its rows in the order
    they appear already skips the hole — this does not reindex to a dense week range.

    Returns a frame indexed by `session_date` with columns `pwc`, `pwh`, `plow`.
    """
    weekly_ordered = weekly.sort_index()
    shifted = pd.DataFrame(
        {
            "pwc": weekly_ordered["close"].shift(1).to_numpy(),
            "pwh": weekly_ordered["high"].shift(1).to_numpy(),
            "plow": weekly_ordered["low"].shift(1).to_numpy(),
        },
        index=pd.Index(weekly_ordered["week_start"].to_numpy()),
    )

    ordered = daily.sort_values("session_date")
    session_dates = ordered["session_date"]
    session_week_start = [date.fromisocalendar(*d.isocalendar()[:2], 1) for d in session_dates]

    out = shifted.reindex(session_week_start)
    out.index = pd.Index(session_dates.to_numpy(), name="session_date")
    return out[["pwc", "pwh", "plow"]]


def month_close_extremes(daily: pd.DataFrame) -> pd.DataFrame:
    """HCOM / LCOM — highest / lowest daily **CLOSE** of the month (§7.3, `OTV @ 27:54`, `HOW`).

    *"Not the highest wick"* — a close, never a high or a low. `month` is the calendar month of
    the CME `session_date`. `hcom_mtd` / `lcom_mtd` are the running extremes of the current month
    computed from sessions **strictly before** the current one (NaN on a month's first session —
    no self-inclusion). `month_1` / `month_2` are the two preceding complete calendar months, with
    `hcom_m1` / `lcom_m1` / `hcom_m2` / `lcom_m2` NaN where history does not reach that far back.

    Returns a frame indexed by `session_date`.
    """
    ordered = daily.sort_values("session_date")
    session_dates = ordered["session_date"]
    close = ordered["close"]
    month = pd.PeriodIndex(session_dates, freq="M")

    mtd_max = close.groupby(month).transform(lambda s: s.shift(1).expanding().max())
    mtd_min = close.groupby(month).transform(lambda s: s.shift(1).expanding().min())

    monthly = close.groupby(month).agg(["max", "min"])
    hcom_full = monthly["max"]
    lcom_full = monthly["min"]

    month_1 = month - 1
    month_2 = month - 2

    return pd.DataFrame(
        {
            "month": month,
            "hcom_mtd": mtd_max.to_numpy(),
            "lcom_mtd": mtd_min.to_numpy(),
            "month_1": month_1,
            "hcom_m1": pd.Series(month_1).map(hcom_full).to_numpy(),
            "lcom_m1": pd.Series(month_1).map(lcom_full).to_numpy(),
            "month_2": month_2,
            "hcom_m2": pd.Series(month_2).map(hcom_full).to_numpy(),
            "lcom_m2": pd.Series(month_2).map(lcom_full).to_numpy(),
        },
        index=pd.Index(session_dates.to_numpy(), name="session_date"),
    )


def htf_levels(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """PDH/PDL/PDC, PWC/PWH/PLOW and HCOM/LCOM, joined on `session_date`.

    Raises `ValueError` if `daily["session_date"]` has a duplicate: the three joins below key on
    that column, and a duplicate label makes each `join` cartesian-product the affected rows.
    """
    if daily["session_date"].duplicated().any():
        raise ValueError("daily['session_date'] must be unique")
    return (
        previous_day_levels(daily)
        .join(previous_week_levels(daily, weekly))
        .join(month_close_extremes(daily))
    )


__all__ = [
    "MONTHS_LOOKBACK",
    "htf_levels",
    "month_close_extremes",
    "previous_day_levels",
    "previous_week_levels",
]
