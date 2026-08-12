---
name: pin-at-zero-needs-a-producer
description: A test asserting something never happens proves nothing unless the code can actually produce it; name the producer being observed
metadata:
  type: feedback
---

On 2026-08-12 Phase 7 shipped a test asserting `Outcome.BREAK_EVEN` never
fired. No code path in the module could construct that member, so the
assertion held whatever the engine did. It was written to copy
`tests/test_entry.py` case 18, which pins **D-35**'s `ORDER_VOIDED` at zero —
but that one is a **real** tripwire, because `stoic/entry.py` can construct an
`ORDER_VOIDED` and the zero is an observation about the data.

The dead pin was reported to the user as a safeguard: *"if it ever fires, that
is a decision landing, not drift."* It could never fire.

**Why:** a pin by *absence* looks identical to a pin by *observation* in the
diff, in the test name, and in the report. Only asking *what constructs this?*
separates them. The same audit found a second one beside it — `assert
str(x.isoformat()) != ""` — which is the same failure with no domain content
at all.

**How to apply:** before writing an assertion that a thing never happens, name
the code path that would make it happen. If there is none, the honest move is
to delete the class and put the tripwire on the **premise** instead — Phase 7's
replacement drives the real engine and asserts that TP1 and the break-even
trigger are one frozen number, which is the claim the removed class rested on
and which can genuinely fail. See [[audit-hard-rules-not-in-material]] for the
same shape one level up: machinery that cites a real precedent and still
checks nothing.
