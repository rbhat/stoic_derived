---
name: tz-aware-day-arithmetic
description: adding Timedelta(days=1) to a tz-aware timestamp adds 24h of absolute time, not a calendar day — it silently misdates the DST fall-back day
metadata:
  type: reference
---

**Never add `Timedelta(days=1)` to a tz-aware timestamp to mean "the next calendar date".** On a
tz-aware index that adds 24 hours of *absolute* time. The US fall-back day is 25 hours long, so
local midnight + 24h lands at 23:00 on the **same date**:

```
tz-aware  midnight ET + Timedelta(1d) = 2019-11-03 23:00:00-05:00 -> date 2019-11-03   WRONG
tz-naive  midnight    + Timedelta(1d) = 2019-11-04 00:00:00       -> date 2019-11-04   right
```

Strip the zone first (`.tz_localize(None).normalize()`), shift, then take `.date`. Spring-forward
is unaffected (a 23-hour day still crosses midnight), so the bug shows up **only in November** —
which makes it look like bad data rather than bad arithmetic.

**Why it cost something here:** this was `stoic/sessions.py:session_date()` on 2026-07-31. Every bar
from 17:00 ET on each fall-back Sunday through midnight got dated a day early, which produced a
phantom 72-bar trading session and truncated its neighbour — 14 corrupted daily bars over
2019-2025, plus the weeklies containing them, plus 504 bars wrongly flagged `past_flatten`.

**It passed a DST gate that looked thorough.** The gate exercised `ny_open_utc`,
`london_open_utc`, `flatten_cutoff_utc`, `session_open_utc` and `session_close_utc` across both
transitions — every function that *takes* `session_date` as an argument, and none that *derives* it.
The lesson generalises past timezones: **a gate must feed real inputs through the function that
computes the value, not only through its consumers.**

**What actually caught it:** a number that was arithmetically impossible. The flatten cutoff is
13:58 PT = 16:58 ET and 5m bars start on the :00/:05 grid, so `past_flatten` on 5m bars can only
ever be 0; the gate printed 504. **Check whether a reported count is possible before checking
whether it looks reasonable.** The data-side check worth keeping is the one that needs no such
insight: group bars by session and flag any session far below the norm (`check_bar_spine.py`
Gate E). See [[historical-bars-2025-11-28-outage]] for what that same sweep found next.
