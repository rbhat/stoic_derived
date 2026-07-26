---
name: red-day-definition
description: "Strategy decision — a red day is close < open; the First Red/Green Day sequence is Day1-3 new HCOM then Day4 red = confirmation, and you trade Day 5, not the signal"
metadata:
  type: project
---

**A red day is `close < open`.** Human strategy decision by the user, 2026-07-26 (ADR-0004). The
user said: *"take my word for the red definition."* Do not re-litigate it and do not try to derive
it from data — across all 7 labelled NQ red/green case-study pages, `close<open` and
`close<prior_close` agree on **every single date**, under both D-0 and D-1 scoring. The data cannot
discriminate. Green day is the mirror.

**The sequence** is verbatim on a slide in `concept_simple_stoic_setups_sss`, held **00:35:05 →
00:37:00** (115 s; corrected 2026-07-26 by the WP-V harvest — the earlier "00:35:12 → 00:35:57" was
two sparse keyframes inside a longer hold). This is on-screen text, not spoken — it is in no
transcript:

> Day 1 / Day 2 / Day 3: Highest Close of the Month · **Day 4: First Red Day = CONFIRMATION**

**Signal vs trade day:** the red day is the *signal*; you trade the **next** day.
`concept_simple_stoic_setups_sss` 00:37:33 — *"we don't trade the signal, we trade the day after the
signal."* Confirm with consolidation on the 5m chart. After a first red day the setup may appear in
**Asia or London**, not only the New York range (00:22:48). The red day itself is sometimes traded
but is explicitly the worse variant (`cs_vol1` 00:16:43, `cs_vol5` 00:33:28).

**Canonical fixture**, verified against `.artifacts/research/bars/NQ_D.jsonl`: Jan 26 / 27 / 28 all
`close>open` with the 28th setting January's highest close (26,268.25) → **2026-01-29 red**
(open 26,282.50, close 25,982.50) = signal → **2026-01-30** is the trade day (closed −343.25).

Test case to implement: 3 consecutive `close>open` days, the third setting the month's highest
close → Day 4 `close<open` = signal → trade Day 5. Note **2026-03-05 fails this precondition**
(March's new-HCOM days were Mar 2 and Mar 4, not consecutive) — the instructor calls it "ugly" and
"not as clean". Do not use it as a positive fixture.

Also settled: on the case-study PDFs the **arrow marks the trade day** (= page-title date), and the
title parenthetical is a **cycle-context label**, not a per-date candle classification — so p06-p09
all reading "(First Red Day)" is one cycle across four sessions.

Full write-up: `docs/notes/2026-07-25-case-study-fixture-track.md` §4a.
See [[case-study-fixture-track]], [[slide-text-not-in-transcripts]], [[audit-derived-numbers]].
