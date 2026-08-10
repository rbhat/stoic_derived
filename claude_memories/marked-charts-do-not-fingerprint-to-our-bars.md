---
name: marked-charts-do-not-fingerprint-to-our-bars
description: §10's marked charts could not be dated by matching their printed MA values against our own 5m SMAs — closest fit in 7 years was 41 points off; unresolved, and it bites Phase 3
metadata:
  type: project
---

**Attempted 2026-08-09 and it did not work.** `NQ3` (`edu/123sequence/nq-1-2-3.png`) prints four
right-axis last-values to two decimals — `28,620.18`, `28,580.09`, `28,540.74`, `28,499.84` — which
should be a fingerprint precise enough to identify the exact 5m bar. Scanning every 5m bar of
`data/historical/NQ_1m.parquet` (2019-06-10 → 2026-06-10) for a matching SMA vector, **the closest
10/20 pair in the whole series was 41 points off**, and adding the 50/200 made it worse (~170 points
on the 200).

**What is confirmed, so it is not re-derived.** The chart is **NQ 5-minute, CME**, its x-axis is
**ET** (the 09:30 candle is the cash open, and it is the session's largest), and its price band puts
it in **May–June 2026** — `28,716.75` occurs as a bar high only **3 times in the seven-year series**,
all in that window, and `27,833` / `28,155` (from `LT3`/`LT4`) land there too. So the sessions **are**
inside our data; only the identification failed.

**Candidate explanations, none tested:** the plotted MAs may not be simple averages of the *close*
(§1.1 names no input series — see the `stoic/indicators.py` convention); TradingView's continuous
contract may differ from our Databento front-month roll, which matters because the June 2026
expiry sits inside the window; or the four labels may not all be MA plots — `28,540.75` is a valid
NQ tick while `28,540.74` is not, which hints that some are drawing levels rather than indicator
values.

**Why it matters:** **Phase 3** labels fixtures off these charts, and the natural first step is to
date them and rebuild them from our own bars so the labels carry real timestamps instead of ±10
pixels. That step is not currently available.

**How to apply:**

- **Do not spend more time dating the charts to unblock a rule.** The bases and the counts are
  readable off the images directly, and *relative* measurements (span lengths, containment, whether
  a range straddles the MA band) survive the pixel error that absolute levels do not. **D-34** was
  taken without any of this.
- If it is worth another pass, test the contract-roll explanation first — it is the cheapest to
  falsify and the only one that would also affect replays.
- The probe lives nowhere; it was a scratch script. Rebuild it from this note rather than hunting.

Related: [[artifact-locality]] for where a rebuilt probe's output belongs if a decision will cite it.
