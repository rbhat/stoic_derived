---
name: negative-result-over-an-incomplete-range
description: a search that finds nothing proves something about the span searched, not about the world — state the span and check the target could have been inside it
metadata:
  type: feedback
---

**Before reporting that something is absent, state the range actually searched and check the target
could have been inside it.**

Measured twice on 2026-08-09/10, the same mistake both times. `NQ3`'s printed axis values were
scanned against "every 5m bar of `data/historical/NQ_1m.parquet` (2019-06-10 → 2026-06-10)" and the
closest match in seven years was 41 points off. Two conclusions were drawn from that: the charts
must be May–June 2026, and the plotted MAs must not be simple averages of the close. **Both were
wrong.** The chart is a 2026-08-03 session — seven weeks past the end of the data. The same method
over the extended spine matches to **0.08 points**.

The range was stated plainly in the note. Nobody checked whether the answer could live outside it.

**Why:** a negative result carries the shape of its search. "Not found in 2019–2026" is a fact about
2019–2026; converting it into a fact about the method, or into a positive claim about where the
answer must be instead, smuggles in an assumption that the search was exhaustive. The second
conclusion is the more expensive one — it sent the next reader after contract rolls and alternative
input series, away from the one-line fix.

**How to apply:**

- Report absence as *"not present in <span>"*, never as *"does not exist"* or *"the method fails"*.
- Before theorising about why a search failed, ask whether the target could have been outside it.
  That check is usually cheaper than any of the theories.
- A near-miss at the **edge** of a range is a signal the range is the problem. The 41-point best
  fit sat near the end of the data; so did the recurring price band the note used for dating.
- This is the sibling of [[coverage-claims-need-enumeration]]: there, matching counts were mistaken
  for coverage; here, an exhausted search was mistaken for an exhaustive one.

Related: [[audit-hard-rules-not-in-material]], the adjacent rule about filling a silence with a
predicate.
