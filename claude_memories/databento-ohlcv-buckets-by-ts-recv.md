---
name: databento-ohlcv-buckets-by-ts-recv
description: Databento OHLCV bars bucket trades by ts_recv, not ts_event — aggregating trades by ts_event silently mismatches the vendor bars
metadata:
  type: project
---

Databento's OHLCV-1m / OHLCV-1h bars assign each trade to a bucket by **`ts_recv`** (gateway
receive time), **not `ts_event`** (exchange event time). Any hand-rolled aggregation of the
`trades` schema must floor `ts_recv` to match.

**Why:** measured on 2026-06-08 NQ, spliced in `scripts/normalize_historical_bars.py`. Bucketing
by `ts_event` mismatched 14 of 1380 one-minute bars against Databento's own bars; by `ts_recv`, 0
of 1380. The failure signature is distinctive: **adjacent bars with equal-and-opposite volume
deltas** (+12 then -12) and a wrong close on the first / wrong open on the second. Cause is bursts
of trades stamped e.g. `ts_event 19:29:59.9996` that arrive at `ts_recv 19:30:00.0001` — the
exchange calls them the 19:29 minute, Databento counts them in the 19:30 bar.

**How to apply:** when aggregating trades into bars, sort by `(ts_recv, sequence)` and floor
`ts_recv`. `DBNStore.to_df()` already indexes by `ts_recv`. Never assume the two timestamps agree
at a bar boundary — the discrepancy is sub-millisecond but lands on exactly the trades that set a
bar's open and close. Keep an overlap check against vendor bars in any splice, because the error is
small enough to pass a visual review.
