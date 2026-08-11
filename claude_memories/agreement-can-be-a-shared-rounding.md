---
name: agreement-can-be-a-shared-rounding
description: Two derivations agreeing closely can mean both were rounded to the same constant, not that either is confirmed — ask what each one actually recovers
metadata:
  type: feedback
---

When two independent-looking derivations of the same quantity agree, check whether **both were
normalised to the same constant** before calling it corroboration.

`T-B1`'s stop had two readings that agreed to **0.99 points** — §10.10's *P&L ÷ R multiple* against
§5.4.1's PTB extreme — and `docs/evidence/labels/2026-07-31_T1_T2.yaml` called it *"the closest
agreement any §10 fixture gives."* It was not evidence about the stop. `PTBV @ 01:36:09` states the
trader sizes every trade to a **round $1,000 risk**, and §10.10 itself says the lot count is
**floor-rounded** to that unit. So §10.10 recovers **$1,000**, §5.4.1 recovers the real risk
($1,018.08), and the 0.99 points is the lot rounding between them. Both readings are near the same
constant *by construction*; agreement was guaranteed and carried no information.

The tell was available without the quote: `LT` gave **12.25** points on the same two readings, and
`T-A2` gave 4.41 for a third reason again. A method that agrees on some fixtures and not others is
not measuring the same thing on all of them.

**Why:** a close agreement reads as two witnesses. When both derive from a shared constant they are
one witness twice — the `DIA-P` error in numeric form (`docs/AUDIT-2a.md` F-1), and the same shape
as [[plausible-cause-is-not-a-measured-cause]].

**How to apply:** before treating an agreement as corroboration, say in one sentence what **each**
derivation actually recovers. If both answers name the same constant, the agreement measures the
rounding. Then check the fixture where the two **disagree** — that is where the readings are
genuinely independent and where the real question lives. See also [[read-around-the-citation]] and
[[sweep-a-misreading-to-every-instance]].
