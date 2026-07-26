---
name: bars-match-education-not-tradingview
description: "Our NQ.c.0 bars reproduce the instructor's drawn levels to the tick; a stock TradingView chart ran ~+506.5 higher — a contract/back-adjustment difference, not a data bug"
metadata:
  type: project
---

On 2026-07-26 the user's TradingView showed 2026-03-04 close **25,645** and 2026-03-05
O 25,663 / H 25,757 / L 25,279.6 / C 25,517. Our `.artifacts/research/bars/NQ_D.jsonl` (`NQ.c.0`)
gives 25,138.00 and O 25,156.50 / H 25,250.00 / L 24,772.50 / C 25,010.50 — a **near-constant
+506.5 to +507.1 offset on all four legs**. A constant offset across O/H/L/C is a contract or
back-adjustment difference, **not a data error**.

**Ours is the series that matches the material.** The vol2 case-study PDFs label
**HCOM 25,138.00**, **February HCOM 25,873.25**, **February LCOM 24,425.25** — our bars reproduce
all three **to the tick**. Since fidelity to the education is the whole objective
([[signal-fidelity-over-edge-revalidation]]), the instructor's charts are ground truth and our
series agrees with them.

**How to apply:** keep `NQ.c.0`. If a chart disagrees with our bars, check the symbol and
back-adjustment setting **before** suspecting the pipeline. Do not "fix" the bars to match an
external chart.

Related trap from the same session: never derive numbers from `.artifacts/research/bars/*.jsonl`
**while `research/build_bars.py` is still running** — the last session in the file is partial and
will give a wrong close. Wait for `[build_bars] DONE`. Rebuild takes ~31 min on the Mac
(41.2M events, 111 daily bars covering 2026-01-02..06-05); `2026-03-20` and `2026-06-05` come out
`quality != complete`.

See [[audit-derived-numbers]], [[case-study-fixture-track]].
