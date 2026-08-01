"""The session clock: CME trading days, intraday phases, and the flatten cutoff.

Every bar timestamp in this repo is stored tz-aware UTC (`ts_event`, the bar start). This module
is the only place that reasons in local wall-clock time, and it does so with `zoneinfo` so daylight
saving is handled automatically — never a fixed UTC offset. Everything else stays in UTC.

Two calendars matter and they are not the same thing:

* The **CME trading day** is a 23-hour trading session with a 1-hour daily maintenance halt, not a
  calendar day. It runs 17:00 -> 16:00 America/Chicago the next day, equivalently 18:00 -> 17:00
  America/New_York (the US zones share DST transitions, so the two phrasings pick the same instants
  every day of the year). `session_date` is the ET calendar date on which a trading day *closes* —
  the date charting platforms label it with.
* The **session phases** (asia/london/newyork/closed) are ET wall-clock-of-day windows within that
  trading day. The education speaks in ET throughout — see
  `edu/123sequence/start_here/only_trading_video.md` line 1078 ("3:00 a.m. London session opens
  up") and line 1098 ("at 9:30 market open") — so ET is the anchor zone, not a derived one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
CT = ZoneInfo("America/Chicago")

# CME Globex trading day: opens 17:00 CT / 18:00 ET, closes 16:00 CT / 17:00 ET the next day. The
# 17:00-18:00 ET hour in between is the exchange's daily maintenance halt (no trading).
CME_OPEN_HOUR_ET = 18
CME_CLOSE_HOUR_ET = 17

# 13:58 America/Los_Angeles = 16:58 ET, exactly 2 minutes before the 17:00 ET CME close. VISION.md
# picks this as the flatten boundary and requires it derived from Pacific wall-clock, not a fixed
# offset, so that it keeps landing 2 minutes before close across DST transitions in either zone.
FLATTEN_LOCAL = time(13, 58)

# Session phase boundaries, ET wall-clock time-of-day (seconds since ET midnight). asia wraps past
# midnight, so it is expressed below as "not london, newyork or closed" rather than as a range.
_LONDON_START_S = 3 * 3600  # 03:00 ET
_NY_START_S = 9 * 3600 + 30 * 60  # 09:30 ET
_CLOSED_START_S = CME_CLOSE_HOUR_ET * 3600  # 17:00 ET
_ASIA_START_S = CME_OPEN_HOUR_ET * 3600  # 18:00 ET
_RTH_END_S = 16 * 3600  # 16:00 ET

SESSION_CATEGORIES = ["asia", "london", "newyork", "closed"]

DateLike = Sequence[date] | pd.Series | pd.Index


def _local_instant(
    session_dates: DateLike, *, hour: int, minute: int, tz: ZoneInfo, day_offset: int
) -> pd.DatetimeIndex:
    """The UTC instant of `hour:minute` local time in `tz`, `day_offset` days from each date.

    Vectorised: builds naive midnight timestamps for the dates, shifts by the offset and
    time-of-day, then localizes once. None of this module's anchor times (03:00, 09:30, 13:58,
    17:00, 18:00) fall in the 01:00-03:00 window where US DST transitions make a local time
    ambiguous or nonexistent, so a plain `tz_localize` is safe here.
    """
    naive = pd.DatetimeIndex(pd.to_datetime(pd.Index(session_dates)))
    naive = naive + pd.Timedelta(days=day_offset, hours=hour, minutes=minute)
    return naive.tz_localize(tz).tz_convert("UTC").as_unit("ns")


def session_date(index: pd.DatetimeIndex) -> pd.Series:
    """The ET calendar date on which each bar's CME trading day closes.

    A trading day opens 18:00 ET and closes 17:00 ET the next date; this returns the closing date
    (the label charting platforms use). A bar at or after 17:00 ET belongs to the trading day that
    closes the *following* date; before 17:00 ET it belongs to the one closing the *same* date. The
    session opening Sunday 18:00 ET therefore has `session_date` equal to that Monday.

    The +1-day shift is done in **naive** local-date space, not on the tz-aware timestamp. On the
    US fall-back day, local midnight to local midnight is 25 real hours; adding a tz-aware
    `Timedelta(days=1)` (an absolute duration) to a fall-back midnight lands at 23:00 the *same*
    date instead of 00:00 the *next* one, silently misdating every bar from 17:00 ET that Sunday
    through the actual midnight. Stripping the tz first makes `Timedelta(days=1)` a calendar-day
    step, which is what a date label needs, DST notwithstanding.
    """
    et = index.tz_convert(ET)
    shift = (et.hour >= CME_CLOSE_HOUR_ET).astype("int64")
    naive_midnight = et.tz_localize(None).normalize()
    shifted = naive_midnight + pd.to_timedelta(shift, unit="D")
    return pd.Series(shifted.date, index=index, name="session_date", dtype=object)


def session_open_utc(session_dates: DateLike) -> pd.DatetimeIndex:
    """UTC instant the CME trading day opened: 18:00 ET on the day before `session_date`."""
    return _local_instant(session_dates, hour=CME_OPEN_HOUR_ET, minute=0, tz=ET, day_offset=-1)


def session_close_utc(session_dates: DateLike) -> pd.DatetimeIndex:
    """UTC instant the CME trading day closes: 17:00 ET on `session_date`."""
    return _local_instant(session_dates, hour=CME_CLOSE_HOUR_ET, minute=0, tz=ET, day_offset=0)


def flatten_cutoff_utc(session_dates: DateLike) -> pd.DatetimeIndex:
    """UTC instant of 13:58 America/Los_Angeles on `session_date` — 2 minutes before CME close."""
    return _local_instant(
        session_dates, hour=FLATTEN_LOCAL.hour, minute=FLATTEN_LOCAL.minute, tz=PT, day_offset=0
    )


def london_open_utc(session_dates: DateLike) -> pd.DatetimeIndex:
    """UTC instant of 03:00 ET on `session_date` — the London-session open."""
    return _local_instant(session_dates, hour=3, minute=0, tz=ET, day_offset=0)


def ny_open_utc(session_dates: DateLike) -> pd.DatetimeIndex:
    """UTC instant of 09:30 ET on `session_date` — the New York / RTH open."""
    return _local_instant(session_dates, hour=9, minute=30, tz=ET, day_offset=0)


def label_sessions(
    index: pd.DatetimeIndex, *, bar_span: pd.Timedelta | None = None
) -> pd.DataFrame:
    """Attach session/phase labels to every bar start in `index`.

    Returns a frame indexed identically to `index` with columns:

    * ``session_date`` (object, `datetime.date`) — see `session_date`.
    * ``session`` (category: asia/london/newyork/closed) — the ET wall-clock phase of the bar's
      *start*.
    * ``rth`` (bool) — bar start inside 09:30-16:00 ET (equity regular trading hours; overlaps
      ``newyork`` on purpose, they answer different questions).
    * ``is_london_open`` / ``is_ny_open`` (bool) — True for the bar that **contains** that session's
      03:00 / 09:30 ET open instant, i.e. ``bar_start <= open_instant < bar_start + bar_span``. This
      is containment, not equality: 09:30 ET never lands on a 60m UTC grid boundary, so an
      equality test would silently mark nothing on 60m bars.
    * ``past_flatten`` (bool) — bar start at or past that session_date's 13:58 PT flatten cutoff.

    `bar_span` is the (constant) duration of a bar in `index`. If not given, it is inferred as the
    modal difference between consecutive index entries — pass it explicitly when the caller already
    knows the timeframe, both to skip that computation on a large frame and to avoid it being
    thrown off by the weekend gap. Raises `ValueError` if `index` has fewer than 2 rows and no
    `bar_span` was given, since the mode cannot be inferred from 0 or 1 gaps.
    """
    if bar_span is None:
        if len(index) < 2:
            raise ValueError(
                "bar_span must be given explicitly for an index with fewer than 2 rows"
            )
        diffs = index.to_series().diff().dropna()
        bar_span = diffs.mode().iloc[0]

    sd = session_date(index)
    et = index.tz_convert(ET)
    tod = et.hour.to_numpy() * 3600 + et.minute.to_numpy() * 60 + et.second.to_numpy()

    phase = np.select(
        [
            (tod >= _NY_START_S) & (tod < _CLOSED_START_S),
            (tod >= _LONDON_START_S) & (tod < _NY_START_S),
            (tod >= _CLOSED_START_S) & (tod < _ASIA_START_S),
        ],
        ["newyork", "london", "closed"],
        default="asia",
    )
    session = pd.Categorical(phase, categories=SESSION_CATEGORIES)
    rth = (tod >= _NY_START_S) & (tod < _RTH_END_S)

    sd_values = sd.to_numpy()
    london_instant = london_open_utc(sd_values)
    ny_instant = ny_open_utc(sd_values)
    flatten_instant = flatten_cutoff_utc(sd_values)

    bar_start = index.as_unit("ns")
    bar_end = bar_start + bar_span
    is_london_open = (bar_start <= london_instant) & (london_instant < bar_end)
    is_ny_open = (bar_start <= ny_instant) & (ny_instant < bar_end)
    past_flatten = bar_start >= flatten_instant

    return pd.DataFrame(
        {
            "session_date": sd.to_numpy(),
            "session": session,
            "rth": np.asarray(rth),
            "is_london_open": np.asarray(is_london_open),
            "is_ny_open": np.asarray(is_ny_open),
            "past_flatten": np.asarray(past_flatten),
        },
        index=index,
    )
