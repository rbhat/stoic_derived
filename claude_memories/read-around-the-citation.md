---
name: read-around-the-citation
description: A rulebook quote can be cut short of the sentence that undoes it — open the transcript around the timestamp before implementing the rule
metadata:
  type: feedback
---

Before implementing any rule in `docs/RULEBOOK.md`, open its cited source **around** the timestamp —
several lines either side — not just the quoted span. A quote can be accurate and still mislead by
where it was cut.

**Why:** §7.4.3 was carried for weeks as *"the only mechanical statement"* of the no-edge zone —
*"we do not trade these setups in the middle of previous daily high and previous daily low"* — and
`docs/STATE.md` scoped it into L4 on that basis. Reading `CST` around `@ 00:22:22` showed the same
checklist naming **previous daily close** a daily level 25 seconds earlier, and the rule's own second
clause is *"we only trade these setups when we have price traded to our POIs."* PDC sits **inside**
the PDH/PDL range by construction, so the literal *strictly-between-blocks* reading forbids a trade
the same breath licenses. The rule was not mechanical; it became **O-19**. `scripts/verify_citations.py`
could not have caught this — the timestamp resolves, the quote is verbatim, and the defect is the
30 seconds either side.

**How to apply:** treat a citation as a *pointer to a passage*, not as the passage — the same
relationship `CLAUDE.md`'s pointer rule sets up between this file and its sources. Read the
surrounding lines before writing the predicate; if they change the reading, that is a §12 row or a
human decision, never a silent implementation of the quote as written. Pairs with
[[audit-hard-rules-not-in-material]] (never invent a predicate to close a gap) and
[[coverage-claims-need-enumeration]] (a matching count is not coverage) — all three are the same
failure: trusting a derived artifact over the material it was derived from.
