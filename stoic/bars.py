"""Load 1-minute bars from data/historical and derive every other timeframe by resampling.

Source: ``data/historical/{symbol}_1m.parquet``, produced by
``scripts/normalize_historical_bars.py`` — a tz-aware UTC `DatetimeIndex` named ``ts_event`` holding
the bar start, columns ``symbol, instrument_id, publisher_id, open, high, low, close, volume,
source``. This module treats that file as the single source of truth for 1-minute bars; every other
timeframe is derived from it by
`resample`, which is pure (no disk writes, no caching) and takes ~0.2s per symbol/timeframe on the
full history — materialising resampled parquet is deliberately not in scope.

Timeframe semantics
--------------------
Intraday bars (5m/15m/60m) floor the UTC clock (``label="left"``, ``closed="left"``) and drop any
bucket with no source 1m bars — the vendor never emits empty bars, so re-inserting them here would
disagree with ``data/historical/{symbol}_1h.parquet``, which is exactly what
``scripts/check_bar_spine.py`` Gate A checks for 60m. ``instrument_id``/``publisher_id`` are dropped
(a bucket can span more than one source row) and ``source`` is overwritten with
``"resampled-1m"``.

1D and 1W bars are grouped by CME trading day / ISO week via `stoic.sessions.session_date`, not by
the UTC calendar — a trading day runs 18:00 ET to 17:00 ET the next day, so grouping by UTC date
would split a session across two rows. Both stay indexed by the UTC instant their trading day (1D)
or its first trading day (1W) opened, so the index stays UTC, monotonic, and labelled by bar start
like the intraday frames.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stoic.sessions import label_sessions, session_date, session_open_utc

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = REPO_ROOT / "data" / "historical"

TIMEFRAMES = ("1m", "5m", "15m", "60m", "1D", "1W")
SYMBOLS = ("NQ", "ES")

RESAMPLED_SOURCE = "resampled-1m"

# Intraday floor frequency for pandas .resample().
_INTRADAY_FREQ = {"5m": "5min", "15m": "15min", "60m": "60min"}

# Bar duration per timeframe, used as label_sessions's bar_span for the open-containment checks.
# 1D/1W are approximate (a trading day is 22-24h, not exactly 24h, around DST) but only need to
# comfortably contain the london/ny open instants of their own session_date, which they do.
BAR_SPAN = {
    "1m": pd.Timedelta(minutes=1),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "60m": pd.Timedelta(minutes=60),
    "1D": pd.Timedelta(days=1),
    "1W": pd.Timedelta(weeks=1),
}

_INTRADAY_AGG = {
    "symbol": "first",
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def load_1m(symbol: str) -> pd.DataFrame:
    """Load the source 1-minute bars for `symbol` (NQ or ES) unchanged, validated on the way in."""
    if symbol not in SYMBOLS:
        raise ValueError(f"unknown symbol {symbol!r}, expected one of {SYMBOLS}")
    frame = pd.read_parquet(HISTORICAL / f"{symbol}_1m.parquet")
    _validate(frame, f"{symbol} 1m")
    return frame


def resample(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample 1m `bars` to `timeframe`. Pure — no disk I/O, no caching.

    See the module docstring for what each timeframe does. `1m` returns `bars` unchanged.
    """
    if timeframe == "1m":
        return bars
    if timeframe in _INTRADAY_FREQ:
        out = _resample_intraday(bars, _INTRADAY_FREQ[timeframe])
    elif timeframe == "1D":
        out = _resample_daily(bars)
    elif timeframe == "1W":
        out = _resample_weekly(_resample_daily(bars))
    else:
        raise ValueError(f"unknown timeframe {timeframe!r}, expected one of {TIMEFRAMES}")

    _validate(out, timeframe)
    return out


def _resample_intraday(bars: pd.DataFrame, freq: str) -> pd.DataFrame:
    """5m/15m/60m: floor the UTC clock, OHLC-aggregate, drop buckets with no source bars."""
    grouped = bars.resample(freq, label="left", closed="left")
    out = grouped.agg(_INTRADAY_AGG)
    out = out.dropna(subset=["open"])
    out["volume"] = out["volume"].astype("uint64")
    out["source"] = RESAMPLED_SOURCE
    out.index.name = "ts_event"
    return out


def _resample_daily(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per CME trading day, indexed by that day's session_open_utc."""
    sd = session_date(bars.index)
    grouped = bars.groupby(sd.to_numpy(), sort=True)
    out = grouped.agg(
        symbol=("symbol", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    out["volume"] = out["volume"].astype("uint64")
    out["source"] = RESAMPLED_SOURCE
    session_dates = out.index.to_numpy()
    out.index = session_open_utc(session_dates)
    out.index.name = "ts_event"
    out["session_date"] = session_dates
    return out


def _resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per ISO week of `daily`'s sessions, indexed by the week's first session_open_utc."""
    reset = daily.reset_index()
    iso_year, iso_week = zip(
        *(d.isocalendar()[:2] for d in reset["session_date"]), strict=True
    )
    reset = reset.assign(_iso_year=iso_year, _iso_week=iso_week)
    grouped = reset.groupby(["_iso_year", "_iso_week"], sort=True)
    out = grouped.agg(
        ts_event=("ts_event", "first"),
        symbol=("symbol", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    week_start = [date.fromisocalendar(year, week, 1) for year, week in out.index]
    out = out.set_index("ts_event")
    out.index.name = "ts_event"
    out["volume"] = out["volume"].astype("uint64")
    out["source"] = RESAMPLED_SOURCE
    out["week_start"] = week_start
    return out


def load_bars(symbol: str, timeframe: str, *, sessions: bool = False) -> pd.DataFrame:
    """Load `symbol` at `timeframe`, resampling from 1m as needed.

    With `sessions=True`, joins `stoic.sessions.label_sessions` columns (session_date, session,
    rth, is_london_open, is_ny_open, past_flatten) onto the result, using this timeframe's own
    `BAR_SPAN` for the open-containment checks. `1D` already carries a `session_date` column from
    resampling; the duplicate from `label_sessions` is dropped rather than joined.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}, expected one of {TIMEFRAMES}")

    out = resample(load_1m(symbol), timeframe)

    if sessions:
        labels = label_sessions(out.index, bar_span=BAR_SPAN[timeframe])
        labels = labels.drop(columns=[c for c in labels.columns if c in out.columns])
        out = out.join(labels)

    return out


def _validate(frame: pd.DataFrame, label: str) -> None:
    """Assert the invariants a bar series must hold (mirrors normalize_historical_bars.validate)."""
    if frame.index.has_duplicates:
        raise ValueError(f"{label}: duplicate bar timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{label}: bar timestamps are not sorted")
    bad = frame[
        (frame["high"] < frame["low"])
        | (frame["open"] > frame["high"])
        | (frame["open"] < frame["low"])
        | (frame["close"] > frame["high"])
        | (frame["close"] < frame["low"])
    ]
    if not bad.empty:
        raise ValueError(f"{label}: {len(bad)} bars violate low <= open,close <= high")
    if (frame["volume"] == 0).any():
        raise ValueError(f"{label}: bars with zero volume")


__all__ = [
    "BAR_SPAN",
    "SYMBOLS",
    "TIMEFRAMES",
    "load_1m",
    "load_bars",
    "resample",
]
