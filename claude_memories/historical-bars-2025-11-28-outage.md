---
name: historical-bars-2025-11-28-outage
description: data/historical NQ+ES 1m bars are missing ~645 contiguous minutes on session 2025-11-28; a real hole, not a holiday early close
metadata:
  type: project
---

`data/historical/{NQ,ES}_1m.parquet` is missing **~645 contiguous minutes** on session date
**2025-11-28**, from Thu 2025-11-27 21:45 ET to Fri 08:29 ET — the whole Asia and London portion of
that trading day. Identical window in both instruments.

```
NQ session 2025-11-28: 508 of 1155 minutes present   volume   149,531
ES session 2025-11-28: 510 of 1155 minutes present   volume   320,654
contrast NQ 2024-11-29: 1155 of 1155 present         volume   282,643
```

**Why it is easy to misdiagnose:** the session is the day after Thanksgiving, so the obvious reading
is "CME early close". That reading is wrong. The early close is present in *every* year of this
dataset and always yields 231 5m bars over Thu 18:00 -> Fri 13:10 ET. 2025 spans the identical
window holding 102. The shortfall is absent bars, not a shorter session. An earlier version of
`scripts/check_bar_spine.py` Gate E labelled it as the early close, which turned a data defect into
a named exception the gate then passed over.

**How to tell a data gap from a trading halt** — the discriminator, now built into Gate E:

- **Price frozen to the penny across the gap => halt.** No trade may print through a limit, so the
  resume open equals the last close exactly. NQ 2020-03-16 has six such halts, all resuming at
  exactly 7556.00, session low -11.45% vs the prior close. Those are genuine COVID limit-down
  halts, not missing data.
- **Price moved across the gap => data is missing.** 2025-11-28 resumes +0.08% (NQ) and +0.10% (ES)
  away from where it stopped: the market traded, we have no record of it.

**How to apply:** any Phase 3 label, Phase 5 replay or Phase 6 reconciliation touching 2025-11-28
must exclude or flag that session — indicators with a lookback crossing the hole are computed from
a truncated window and will silently disagree with a chart. `scripts/check_bar_spine.py` Gate E
reports it on every run and fails on any *unnamed* gap over 30 minutes, so a new outage in a future
data pull surfaces rather than passing quietly. See [[databento-ohlcv-buckets-by-ts-recv]] for the
other way these files can disagree with a vendor chart.
