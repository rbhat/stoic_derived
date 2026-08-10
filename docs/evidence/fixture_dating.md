# Dating the §10 marked charts — measured 2026-08-10

**Every fixture in `docs/RULEBOOK.md` §10 is now dated to a session and to the bar its screenshot
was taken on.** All five sit in 2026-07-27 → 2026-08-03, which is why they could not be dated
before: `data/historical/{NQ,ES}_1m.parquet` ended 2026-06-10 until `scripts/merge_signal_bars.py`
extended it. See `docs/PHASE3.md`.

Reproduce with `scripts/date_marked_chart.py <four printed values>`.

## Result

| Fixture | CME session | Screenshot bar (UTC) | ET | SMA worst \|Δ\| | next-best bar |
|---|---|---|---|---|---|
| `LT` | 2026-07-27 | 2026-07-27 14:05 | 10:05 | **1.77** | 32.41 |
| `LT3` / `LT4` | 2026-07-30 (exit in 07-31) | 2026-07-31 02:15 | 07-30 22:15 | **0.16** | 12.93 |
| `PTBV` (kf 0399) | 2026-07-30 | 2026-07-30 19:10 | 15:10 | **0.59** | 10.05 |
| `T1` / `T2` | 2026-07-31 | 2026-07-31 17:45 | 13:45 | **3.23** | 5.47 |
| `NQ3` | 2026-08-03 | 2026-08-03 14:35 | 10:35 | **0.08** | 18.37 |

`T2`'s margin is the narrowest and it is the one MNQ chart whose printed values were transcribed
from a lower-resolution render; it is corroborated below by three further agreements.

## The second agreement, per fixture

`docs/PHASE3.md` requires two independent agreements before a fixture counts as dated. The SMA
fingerprint is one. These are the others, and none of them is a moving average:

| Fixture | Independent agreement | Chart | Bars |
|---|---|---|---|
| `LT` | `PDC` and `LCOM` tags drawn at **the same price** | one level | `pdc` = 28,306.50 and `lcom_mtd` = 28,306.50 — equal on this session by construction |
| `LT` | `PDL` | ~28,213 | **28,212.50** |
| `LT3`/`LT4` | `PWC` printed | **28,306.75** | **28,306.50** |
| `LT3`/`LT4` | x-axis day separator `31` at the right edge | session is the 30th | 22:15 ET on 07-30 |
| `PTBV` | on-screen clock, bottom right | **`03:14:52 PM UTC-4`** | falls inside the 15:10–15:15 bar |
| `PTBV` | crosshair date label | **`Thu 30 Jul '26`** | 2026-07-30 |
| `T1`/`T2` | session low | ~28,075 | **28,079.75** |
| `T1`/`T2` | `PLOW`, measured off the plot on both snapshots | **28,212.39** / **28,212.38** | **28,212.50** |
| `T1`/`T2` | `Jun LCOM`, measured off the plot on both snapshots | **28,471.62** / **28,471.58** | **28,472.00** |
| `T1`/`T2` | session high | ~28,740 | **28,725.75** |
| `NQ3` | last-price tag with an `00:08` countdown | **28,716.75** | 10:35 bar closes **28,716.00** eight seconds later |
| `NQ3` | session low, the 09:30 wick | ~28,320 | **28,313.50** |
| `NQ3` | `PDC` | ~28,290 | **28,287.00** |

`LT`'s first row is the strongest single agreement in the table and the hardest to get by chance:
the chart stacks a `PDC` tag and an `LCOM` tag at one price, and 2026-07-27 is a session where the
previous day's close *is* the month's lowest close to date. A wrong date breaks the coincidence.

## What this corrects

**`claude_memories/marked-charts-do-not-fingerprint-to-our-bars.md` was wrong twice**, and the two
errors compounded:

1. It dated the charts to **May–June 2026** from a scan that could only see up to 2026-06-10. The
   price band recurs at the edge of the data and continues past it, so the band was real and the
   conclusion was not.
2. It read the failure as the **method** being wrong — "the plotted MAs may not be simple averages
   of the close" — and recommended testing the contract-roll explanation first. The method is
   right. On `NQ3` it reproduces all four printed values to **0.08 points**.

Both errors have the same shape: a negative result over an incomplete range was read as a fact
about the world rather than about the range.

## Two things this settles, neither of them a decision

**The SMA input series is the close.** `stoic/indicators.py` had to pick one because §1.1 names
none, and `docs/STATE.md` carried it as an unpinned convention. Measured on `NQ3`'s bar:

| Series | 10 / 20 / 50 / 200 | worst \|Δ\| vs printed |
|---|---|---|
| **close** | 28,620.10 / 28,540.70 / 28,499.83 / 28,580.08 | **0.08** |
| `hl2` | 28,607.31 / 28,531.51 / 28,495.58 / 28,579.24 | 12.87 |
| `hlc3` | 28,611.58 / 28,534.58 / 28,496.99 / 28,579.52 | 8.60 |
| `ohlc4` | 28,607.64 / 28,532.91 / 28,496.61 / 28,579.47 | 12.54 |

The convention was already correct. It is now corroborated against a source artifact, which is a
different status — but it is **not** a new rule and gets no D-row.

**`NQ3` plots the 10, 20, 50 and 200 together on the 5m**, since all four printed values resolve.
That is §7.1's filter and §2's sequence pair on one chart, as `docs/RULEBOOK.md` §10.7 describes.

## One §10 reading this puts in doubt

**§10.7 records `NQ3`'s stop as "28,540.75, the PTB low (§5.4.1) — box bottom".** That value is
within **0.04** of the same chart's **20 SMA** (28,540.70), which is what the right-axis label
`28,540.74` is. The 10:00 ET pullback bar's low is **28,534.50**, not 28,540.75.

So the number §10.7 reads as a stop is an axis label for an indicator. Whether the drawn box bottom
independently sits at the PTB low is a separate question that pixels cannot settle here. **Not
edited into `docs/RULEBOOK.md` — reported.** §10.10 already states that no chart in §10 draws a
stop, which is consistent with this and was the safer reading all along.

## Method, and its one real limit

Four printed indicator values, matched as a **sorted multiset** against our SMAs — the chart never
says which label is which average, so an assignment would be an assumption. `--periods` makes the
set of periods explicit rather than assumed.

**The limit is that a printed number may not be a level at all** — the same trap as §10.7's stop,
one section up.

This paragraph used to say the limit was **contract drift**: that `T1`/`T2` and `LT3`/`LT4` print a
`Jun LCOM` of **28,473.81** and **28,471.53** on sessions one day apart, so month-old levels move
~2 points between screenshots while same-week levels hold to a tick. **Every part of that reading
was wrong, and it was wrong the same way §10.7's stop is.** Measured on the artifacts while
labelling `T1`/`T2` (`docs/evidence/labels/2026-07-31_T1_T2.yaml`):

| Printed | §10 calls it | It is | Ours |
|---|---|---|---|
| 28,482.85 (`T1` axis tag) | §10.2 *"Jun LCOM at 28,482"* | `T1`'s **200 SMA** at its last bar | 28,483.03 |
| 28,473.81 (`T2` axis tag) | §10.8 *"into `Jun LCOM` 28,473.81"* | `T2`'s **200 SMA** at its last bar | 28,473.70 |
| 28,471.53 (`LT3`/`LT4` axis tag) | §10.9 *"`Jun LCOM` 28,471.53"* | that chart's **10 SMA** at its last bar | 28,471.40 |

The **drawn** `Jun LCOM` line on `T1`/`T2` measures **28,471.62** / **28,471.58** against our
**28,472.00** — under half a point, on a level a month old. So month-old levels do **not** drift
here; the drift was an artefact of reading three axis tags as levels. On the same charts `PLOW`
measures 28,212.39 / 28,212.38 against our **28,212.50**, and the plotted brown line reproduces our
200 SMA to **0.01** at the 11:10 ET bar.

**The standing advice survives, with a different reason.** Anchor on a level you have **measured off
the plot**, not on a number printed in the price axis: the axis carries every indicator's last
value, and those are the non-tick-valid prints (`28,540.74`, `28,473.81`) the old memory flagged and
could not place. **§10 is not edited** — that is the user's call.
